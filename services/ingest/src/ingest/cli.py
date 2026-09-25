from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import typer

from ingest.adapters import (
    CustomsAuctionAdapter,
    JudicialMovableAdapter,
    JudicialPublicNoticesAdapter,
    MojAuctionAdapter,
    MojEnforcementCmsAdapter,
    MojEnforcementExportedIndexParser,
    MojEnforcementManualAdapter,
    PccAssetSaleAdapter,
    ShwooAdapter,
)
from ingest.adapters.base import SourceAccessDenied, SourceAdapter, SourceRateLimited
from ingest import PARSER_VERSION
from ingest.data_gov_catalog import (
    DataGovCatalogError,
    github_warning_lines,
    taipei_catalog_cutoff,
    watch_official_catalog,
)
from ingest.models import DiscoveredItem, RawArtifact, SyncResult
from ingest.repository import DatabaseRepository
from ingest.public_publisher import SupabasePublicPublisher
from ingest.storage import LocalArtifactStorage, SupabaseArtifactStorage
from ingest.source_policy import AccessDecision, policy_for, require_live_access

app = typer.Typer(no_args_is_help=True, help="Read-only official car and motorcycle auction ingestion")

PUBLIC_AUTOMATED_SOURCES = {
    "shwoo": "臺北惜物網",
    "moj_auction": "法務部查扣物集中拍賣",
    "pcc": "政府電子採購網財物變賣",
    "customs": "財政部關務署四關標售",
    "moj_enforcement_cms": "行政執行署各分署公告",
    "judicial_notices": "司法院其他司法公告（車輛拍賣補充）",
}
PARTIAL_FAILURE_KEY = "ingest_partial_failure"


def supabase_backend_key() -> str | None:
    """Prefer Supabase's current secret key while retaining legacy compatibility."""
    return os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def exception_message(exc: Exception) -> str:
    """Keep run warnings useful even for exceptions with an empty string form."""
    return str(exc).strip() or exc.__class__.__name__


def record_partial_item(result: SyncResult, item: DiscoveredItem) -> None:
    """Expose a safely retained summary as a partial detail failure in run health."""
    warning = str(item.metadata.get(PARTIAL_FAILURE_KEY) or "").strip()
    if not warning:
        return
    result.failed += 1
    result.warnings.append(f"{item.source_record_id}: {warning}")


def record_discovery_warnings(result: SyncResult, adapter: SourceAdapter) -> None:
    """Retain partial branch/list coverage instead of presenting it as zero new cases."""
    warnings = getattr(adapter, "discovery_warnings", None)
    if warnings is None:
        warnings = getattr(adapter, "_discovery_warnings", [])
    normalized = [str(warning).strip() for warning in warnings if str(warning).strip()]
    if not normalized:
        return
    result.warnings.extend(warning for warning in normalized if warning not in result.warnings)


def emit_safe_discovery_diagnostics(source: str, warnings: list[str]) -> None:
    """Expose failed source stages without leaking URL queries into CI logs."""
    for warning in warnings[:20]:
        no_urls = re.sub(r"https?://\S+", "[official URL omitted]", warning)
        one_line = re.sub(r"[\x00-\x1f\x7f]+", " ", no_urls).strip()[:400]
        if one_line:
            typer.echo(f"{source} discovery warning: {one_line}", err=True)


def load_enforcement_manifest(path: Path) -> list[DiscoveredItem]:
    if path.is_dir() or path.suffix.lower() in {".html", ".htm"}:
        export_paths = (
            sorted(candidate for candidate in path.iterdir() if candidate.suffix.lower() in {".html", ".htm"})
            if path.is_dir()
            else [path]
        )
        if not export_paths:
            raise typer.BadParameter("Administrative Enforcement export directory contains no HTML files")
        merged: dict[str, DiscoveredItem] = {}
        manifest_warnings: list[str] = []
        for export_path in export_paths:
            items, warnings = MojEnforcementExportedIndexParser.parse(export_path.read_bytes())
            for warning in warnings:
                qualified_warning = f"{export_path.name}: {warning}"
                manifest_warnings.append(qualified_warning)
                typer.echo(qualified_warning, err=True)
            for item in items:
                merged.setdefault(item.source_record_id, item)
        if not merged:
            raise typer.BadParameter("Administrative Enforcement exported HTML contained no validated vehicle details")
        for item in merged.values():
            item.metadata["manifest_warnings"] = list(dict.fromkeys(manifest_warnings))
        return sorted(merged.values(), key=lambda item: item.source_record_id)

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise typer.BadParameter("Administrative Enforcement manifest must be a JSON array")
    items: list[DiscoveredItem] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise typer.BadParameter(f"Manifest row {index + 1} must be an object")
        official_url = str(row.get("official_url") or "")
        try:
            source_record_id = MojEnforcementExportedIndexParser.validate_url(official_url, kind="detail")
        except ValueError as exc:
            raise typer.BadParameter(f"Manifest row {index + 1} must use a safe official /Detail/Chattel?NO= URL: {exc}") from exc
        if not source_record_id:
            raise typer.BadParameter(f"Manifest row {index + 1} must use an official /Detail/Chattel?NO= URL")
        title = str(row.get("title") or "").strip()
        if not title:
            raise typer.BadParameter(f"Manifest row {index + 1} requires the official vehicle title/summary")
        items.append(DiscoveredItem(
            source_record_id=source_record_id, official_url=official_url, title=title,
            discovery_url=MojEnforcementManualAdapter.SEARCH_URL,
            metadata={"manifest_provenance": "HUMAN_VALIDATED_DETAIL_URL_ONLY"},
        ))
    return items


async def load_moj_enforcement_reprocessable(
    repository: DatabaseRepository,
    from_parser_version: str | None,
    limit: int | None,
) -> tuple[list[tuple[DiscoveredItem, list[RawArtifact]]], list[str]]:
    """Rebuild records from the exact many-to-many artifact use graph.

    A checksum-addressed exported index can be shared by many records, so the
    first owner in ``raw_artifacts.source_record_id`` is not an association.
    Reprocessing only restores artifacts explicitly linked through
    ``source_record_artifacts`` and never guesses from titles, dates or cases.
    """
    version_clause = """
      and exists (
        select 1
        from source_record_artifacts version_link
        join raw_artifacts version_artifact on version_artifact.id=version_link.artifact_id
        where version_link.source_record_id=sr.id
          and version_artifact.official_url=sr.official_url
          and version_artifact.mime_type in ('text/html','application/xhtml+xml')
          and version_artifact.parser_version=%s
      )
    """ if from_parser_version else ""
    limit_clause = "limit %s" if limit is not None else ""
    parameters: list[object] = [repository.source_id]
    if from_parser_version:
        parameters.append(from_parser_version)
    if limit is not None:
        parameters.append(limit)
    with repository._connect() as conn, conn.cursor() as cur:  # noqa: SLF001 - exact DB association is repository state
        cur.execute(
            f"""
            with selected_records as (
              select sr.id,sr.source_record_id,sr.official_url,sr.original_title
              from source_records sr
              where sr.source_id=%s
                {version_clause}
              order by sr.source_record_id
              {limit_clause}
            )
            select sr.id as source_record_uuid,sr.source_record_id,sr.official_url,
                   sr.original_title,ra.id as artifact_id,
                   ra.official_url as artifact_url,ra.fetched_at,ra.http_status,
                   ra.http_headers,ra.mime_type,ra.filename,ra.checksum_sha256,
                   ra.storage_path,ra.parser_version,link.artifact_role,
                   link.sort_order,link.last_sync_run_id,link.last_seen_at
            from selected_records sr
            join source_record_artifacts link on link.source_record_id=sr.id
            join raw_artifacts ra on ra.id=link.artifact_id
            left join artifact_tombstones tombstone on tombstone.artifact_id=ra.id
            where tombstone.id is null
            order by sr.source_record_id,
                     case
                       when ra.official_url=sr.official_url
                        and ra.mime_type in ('text/html','application/xhtml+xml') then 0
                       when ra.official_url=%s then 1
                       else 2
                     end,
                     link.last_seen_at desc,link.sort_order,ra.fetched_at desc,ra.id
            """,
            tuple([*parameters, MojEnforcementManualAdapter.SEARCH_URL]),
        )
        linked_rows = [dict(row) for row in cur.fetchall()]

    queued: list[tuple[DiscoveredItem, list[RawArtifact]]] = []
    warnings: list[str] = []

    async def stored_artifact(row: dict[str, object]) -> RawArtifact | None:
        record_id = str(row.get("source_record_id") or "unknown")
        try:
            content = await repository.storage.get(str(row["storage_path"]))
        except Exception as exc:
            warnings.append(
                f"{record_id}: linked stored artifact could not be loaded "
                f"({exception_message(exc)}); artifact omitted"
            )
            return None
        expected = str(row["checksum_sha256"])
        if hashlib.sha256(content).hexdigest() != expected:
            warnings.append(
                f"{record_id}: linked stored artifact checksum mismatch; artifact omitted"
            )
            return None
        raw_headers = row.get("http_headers")
        if isinstance(raw_headers, dict):
            http_headers = {str(key): str(value) for key, value in raw_headers.items()}
        elif isinstance(raw_headers, str):
            try:
                decoded_headers = json.loads(raw_headers)
            except json.JSONDecodeError:
                decoded_headers = {}
            http_headers = (
                {str(key): str(value) for key, value in decoded_headers.items()}
                if isinstance(decoded_headers, dict)
                else {}
            )
        else:
            http_headers = {}
        return RawArtifact(
            official_url=str(row["artifact_url"]),
            fetched_at=row["fetched_at"],
            mime_type=str(row["mime_type"]),
            filename=str(row["filename"]) if row.get("filename") is not None else None,
            content=content,
            http_status=int(row.get("http_status") or 200),
            http_headers=http_headers,
            checksum_sha256=expected,
        )

    grouped_rows: dict[str, list[dict[str, object]]] = {}
    for row in linked_rows:
        grouped_rows.setdefault(str(row["source_record_uuid"]), []).append(row)

    for record_rows in grouped_rows.values():
        record_row = record_rows[0]
        record_id = str(record_row["source_record_id"])
        detail_row = next((
            row
            for row in record_rows
            if str(row["mime_type"]) in {"text/html", "application/xhtml+xml"}
            and str(row["artifact_url"]) == str(row["official_url"])
            and (
                from_parser_version is None
                or str(row.get("parser_version") or "") == from_parser_version
            )
        ), None)
        if detail_row is None:
            warnings.append(
                f"{record_id}: no exact linked detail HTML matched the requested parser version; reprocess skipped"
            )
            continue
        anchor_run_id = detail_row.get("last_sync_run_id")
        if anchor_run_id is not None:
            # A relation is updated for every artifact actually used by a save.
            # Matching the detail's latest run prevents stale historical photos
            # or old index exports from being reintroduced as current support.
            record_rows = [
                row for row in record_rows
                if row.get("last_sync_run_id") == anchor_run_id
            ]
        loaded_artifacts: list[RawArtifact] = []
        seen_artifact_ids: set[str] = set()
        for artifact_row in record_rows:
            artifact_id = str(artifact_row["artifact_id"])
            if artifact_id in seen_artifact_ids:
                continue
            seen_artifact_ids.add(artifact_id)
            artifact = await stored_artifact(artifact_row)
            if artifact is not None:
                loaded_artifacts.append(artifact)

        detail_artifact = next((
            artifact
            for artifact in loaded_artifacts
            if artifact.mime_type in {"text/html", "application/xhtml+xml"}
            and artifact.checksum_sha256 == str(detail_row["checksum_sha256"])
        ), None)
        if detail_artifact is None:
            warnings.append(
                f"{record_id}: no intact linked detail HTML was available; reprocess skipped"
            )
            continue

        artifacts = [
            detail_artifact,
            *(artifact for artifact in loaded_artifacts if artifact is not detail_artifact),
        ]
        item: DiscoveredItem | None = None
        index_candidates = [
            artifact
            for artifact in artifacts
            if artifact.mime_type == "text/html"
            and str(artifact.official_url) == MojEnforcementManualAdapter.SEARCH_URL
        ]
        for index_artifact in index_candidates:
            try:
                parsed_items, parse_warnings = MojEnforcementExportedIndexParser.parse(index_artifact.content)
            except ValueError as exc:
                warnings.append(
                    f"{record_id}: linked exported index could not be parsed "
                    f"({exception_message(exc)}); trying another exact link"
                )
                continue
            warnings.extend(
                f"{record_id}: reprocess index warning: {warning}"
                for warning in parse_warnings
            )
            item = next((
                candidate for candidate in parsed_items
                if candidate.source_record_id == record_id
            ), None)
            if item is not None:
                item.discovery_artifacts = [index_artifact]
                break
            warnings.append(
                f"{record_id}: linked exported index does not contain this record; trying another exact link"
            )
        if item is None:
            item = DiscoveredItem(
                source_record_id=record_id,
                official_url=str(record_row["official_url"]),
                title=str(record_row.get("original_title") or record_id),
                discovery_url=MojEnforcementManualAdapter.SEARCH_URL,
                metadata={"reprocess_provenance": "EXACT_STORED_DETAIL_ONLY"},
            )
        queued.append((item, artifacts))
    return queued, list(dict.fromkeys(warnings))


def load_judicial_manifest(path: Path) -> list[DiscoveredItem]:
    """Load human-reviewed official PDF links without querying the blocked search form."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise typer.BadParameter("Judicial manifest must be a JSON array")
    items: list[DiscoveredItem] = []
    required = ("crtnm", "crm", "saledate", "saleno", "ttitle")
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise typer.BadParameter(f"Manifest row {index + 1} must be an object")
        official_url = str(row.get("official_url") or "")
        parsed = urlparse(official_url)
        filenames = parse_qs(parsed.query).get("filenm", [])
        if (
            parsed.scheme != "https"
            or parsed.hostname != "aomp109.judicial.gov.tw"
            or parsed.path != "/judbp/wkw/WHD1A02/DO_VIEWPDF.htm"
            or len(filenames) != 1
            or not filenames[0].lower().endswith(".pdf")
        ):
            raise typer.BadParameter(f"Manifest row {index + 1} must use an official Judicial Yuan DO_VIEWPDF URL")
        missing = [key for key in required if not str(row.get(key) or "").strip()]
        if missing:
            raise typer.BadParameter(f"Manifest row {index + 1} is missing official fields: {', '.join(missing)}")
        source_record_id = str(row.get("source_record_id") or "").strip()
        if not source_record_id:
            source_record_id = f"manual-{hashlib.sha256(filenames[0].encode()).hexdigest()[:24]}"
        metadata = {key: value for key, value in row.items() if key not in {"official_url", "source_record_id"}}
        metadata.setdefault("rowid", source_record_id)
        metadata.setdefault("filenm", filenames[0])
        items.append(DiscoveredItem(
            source_record_id=source_record_id,
            official_url=official_url,
            title=str(row["ttitle"]).strip(),
            discovery_url=JudicialMovableAdapter.INDEX_URL,
            metadata=metadata,
        ))
    return items


def adapter_for(source: str, manifest: Path | None = None) -> SourceAdapter:
    if source == "shwoo":
        return ShwooAdapter(request_interval=float(os.getenv("SHWOO_REQUEST_INTERVAL_SECONDS", "1")))
    if source == "pcc":
        return PccAssetSaleAdapter(request_interval=float(os.getenv("PCC_REQUEST_INTERVAL_SECONDS", "1")))
    if source == "judicial":
        items = load_judicial_manifest(manifest) if manifest else []
        return JudicialMovableAdapter(items, request_interval=float(os.getenv("JUDICIAL_REQUEST_INTERVAL_SECONDS", "1")))
    if source == "judicial_notices":
        return JudicialPublicNoticesAdapter(
            request_interval=float(os.getenv("JUDICIAL_NOTICES_REQUEST_INTERVAL_SECONDS", "1")),
            request_timeout_seconds=float(os.getenv("JUDICIAL_NOTICES_REQUEST_TIMEOUT_SECONDS", "20")),
            max_request_attempts=int(os.getenv("JUDICIAL_NOTICES_MAX_REQUEST_ATTEMPTS", "3")),
        )
    if source == "moj_auction":
        return MojAuctionAdapter(request_interval=float(os.getenv("MOJ_AUCTION_REQUEST_INTERVAL_SECONDS", "1")))
    if source == "moj_enforcement":
        items = load_enforcement_manifest(manifest) if manifest else []
        return MojEnforcementManualAdapter(items, request_interval=float(os.getenv("MOJ_ENFORCEMENT_REQUEST_INTERVAL_SECONDS", "1")))
    if source == "customs":
        return CustomsAuctionAdapter(request_interval=float(os.getenv("CUSTOMS_REQUEST_INTERVAL_SECONDS", "1")))
    if source == "moj_enforcement_cms":
        return MojEnforcementCmsAdapter(
            request_interval=float(os.getenv("MOJ_ENFORCEMENT_CMS_REQUEST_INTERVAL_SECONDS", "1")),
            request_timeout_seconds=float(os.getenv("MOJ_ENFORCEMENT_CMS_REQUEST_TIMEOUT_SECONDS", "12")),
            max_request_attempts=int(os.getenv("MOJ_ENFORCEMENT_CMS_MAX_REQUEST_ATTEMPTS", "2")),
            branch_deadline_seconds=float(os.getenv("MOJ_ENFORCEMENT_CMS_BRANCH_DEADLINE_SECONDS", "45")),
        )
    raise typer.BadParameter(
        "Implemented sources are: shwoo, pcc, judicial, judicial_notices, moj_auction, "
        "moj_enforcement, moj_enforcement_cms, customs"
    )


async def run_healthcheck(source: str) -> None:
    policy = policy_for(source)
    if policy.decision != AccessDecision.ALLOW:
        typer.echo(json.dumps({
            "source": source,
            "status": "DISABLED" if policy.decision == AccessDecision.DISABLED else "DEGRADED",
            "checked_at": f"{policy.checked_on.isoformat()}T00:00:00+00:00",
            "response_ms": None,
            "message": f"Live access policy: {policy.decision}",
            "warnings": [policy.reason],
        }, ensure_ascii=False, indent=2))
        return
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required before a live healthcheck so the persisted source-access policy can be verified"
        )
    DatabaseRepository(
        database_url,
        LocalArtifactStorage(),
        source,
    ).require_access({AccessDecision.ALLOW})
    adapter = adapter_for(source)
    try:
        typer.echo((await adapter.healthcheck()).model_dump_json(indent=2))
    finally:
        await adapter.close()


async def run_sync(source: str, limit: int | None, manifest: Path | None = None) -> None:
    human_manifest = source in {"judicial", "moj_enforcement"} and manifest is not None
    require_live_access(source, human_manifest=human_manifest)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for sync; run the local Supabase stack first")
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = supabase_backend_key()
    storage = SupabaseArtifactStorage(supabase_url, service_key, os.getenv("RAW_ARTIFACT_BUCKET", "raw-artifacts")) if supabase_url and service_key else LocalArtifactStorage()
    repository = DatabaseRepository(database_url, storage, source)
    if source == "moj_enforcement" and manifest is None:
        raise typer.BadParameter("moj_enforcement sync requires --manifest exported after a human completes the official CAPTCHA search")
    if source == "judicial" and manifest is None:
        raise typer.BadParameter("judicial sync requires --manifest containing human-reviewed official PDF links")
    repository.require_access(
        {AccessDecision.MANUAL_ONLY} if human_manifest else {AccessDecision.ALLOW}
    )
    adapter = adapter_for(source, manifest)
    result = SyncResult(source=source, discovered=0, fetched=0, parsed=0, changed=0, failed=0)
    run_id = repository.start_run()
    try:
        try:
            items = await adapter.discover()
        except Exception as exc:
            record_discovery_warnings(result, adapter)
            result.failed += 1
            result.warnings.append(f"Discovery failed: {exception_message(exc)}")
            emit_safe_discovery_diagnostics(source, result.warnings)
            raise
        record_discovery_warnings(result, adapter)
        if limit is not None:
            items = items[:limit]
        result.discovered = len(items)
        if not items:
            result.warnings.append("Discovery returned zero records; prior data was preserved")
        for item in items:
            try:
                artifacts = await adapter.fetch(item)
                result.fetched += 1
                record = await adapter.parse(item, artifacts)
                if await repository.save(run_id, item, artifacts, record):
                    result.changed += 1
                result.parsed += 1
                record_partial_item(result, item)
            except (SourceAccessDenied, SourceRateLimited) as exc:
                result.failed += 1
                result.warnings.append(
                    f"{item.source_record_id}: source access stopped for this run: {exception_message(exc)}"
                )
                break
            except Exception as exc:
                result.failed += 1
                result.warnings.append(f"{item.source_record_id}: {exception_message(exc)}")
        record_discovery_warnings(result, adapter)
        if result.fetched and (result.parsed / result.fetched) < 0.9:
            result.warnings.append("Parse success rate fell below 90%")
    finally:
        try:
            await adapter.close()
        finally:
            repository.finish_run(run_id, result)
    typer.echo(result.model_dump_json(indent=2))


async def run_publish_public(source: str, limit: int | None) -> None:
    if source not in PUBLIC_AUTOMATED_SOURCES:
        raise typer.BadParameter(
            "Automated public publishing is limited to reviewed ALLOW sources: "
            + ", ".join(PUBLIC_AUTOMATED_SOURCES)
        )
    require_live_access(source)
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = supabase_backend_key()
    if not supabase_url or not service_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY (or legacy SUPABASE_SERVICE_ROLE_KEY) are required")
    publisher = SupabasePublicPublisher(
        supabase_url,
        service_key,
        os.getenv("RAW_ARTIFACT_BUCKET", "raw-artifacts"),
        source_adapter=source,
        source_name=PUBLIC_AUTOMATED_SOURCES[source],
    )
    result = SyncResult(source=source, discovered=0, fetched=0, parsed=0, changed=0, failed=0)
    try:
        adapter = adapter_for(source)
    except Exception:
        await publisher.close()
        raise
    try:
        await publisher.start()
    except Exception:
        try:
            await adapter.close()
        finally:
            await publisher.close()
        raise
    try:
        try:
            items = await adapter.discover()
        except Exception as exc:
            record_discovery_warnings(result, adapter)
            result.failed += 1
            result.warnings.append(f"Discovery failed: {exception_message(exc)}")
            emit_safe_discovery_diagnostics(source, result.warnings)
            raise
        record_discovery_warnings(result, adapter)
        if limit is not None:
            items = items[:limit]
        result.discovered = len(items)
        if not items:
            result.warnings.append("Discovery returned zero records; prior public data was preserved")
        for item in items:
            try:
                artifacts = await adapter.fetch(item)
                result.fetched += 1
                record = await adapter.parse(item, artifacts)
                if await publisher.publish(item, artifacts, record):
                    result.changed += 1
                result.parsed += 1
                record_partial_item(result, item)
            except (SourceAccessDenied, SourceRateLimited) as exc:
                result.failed += 1
                result.warnings.append(
                    f"{item.source_record_id}: source access stopped for this run: {exception_message(exc)}"
                )
                break
            except Exception as exc:
                result.failed += 1
                result.warnings.append(f"{item.source_record_id}: {exception_message(exc)}")
        record_discovery_warnings(result, adapter)
        if result.fetched and result.parsed / result.fetched < 0.9:
            result.warnings.append("Parse success rate fell below 90%")
    finally:
        try:
            await adapter.close()
        finally:
            try:
                await publisher.finish(result)
            finally:
                await publisher.close()
    typer.echo(result.model_dump_json(indent=2))
    if result.discovered == 0 or result.failed or result.warnings:
        # The publisher has already preserved prior rows and recorded the
        # partial/failed run. Return nonzero so GitHub Actions cannot display a
        # green check for missing coverage, parser errors, or health-write
        # failures.
        raise typer.Exit(code=1)


async def run_reprocess(source: str, from_parser_version: str | None, limit: int | None) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for reprocessing; run the local Supabase stack first")
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = supabase_backend_key()
    storage = SupabaseArtifactStorage(supabase_url, service_key, os.getenv("RAW_ARTIFACT_BUCKET", "raw-artifacts")) if supabase_url and service_key else LocalArtifactStorage()
    repository = DatabaseRepository(database_url, storage, source)
    adapter = adapter_for(source)
    run_id = repository.start_run()
    result = SyncResult(source=source, discovered=0, fetched=0, parsed=0, changed=0, failed=0)
    try:
        if source == "moj_enforcement":
            queued, reconstruction_warnings = await load_moj_enforcement_reprocessable(
                repository,
                from_parser_version,
                limit,
            )
            result.warnings.extend(reconstruction_warnings)
        else:
            queued = await repository.load_reprocessable(from_parser_version, limit)
        result.discovered = len(queued)
        for item, artifacts in queued:
            try:
                record = await adapter.parse(item, artifacts)
                result.fetched += 1
                if await repository.save(run_id, item, artifacts, record):
                    result.changed += 1
                result.parsed += 1
            except Exception as exc:
                result.failed += 1
                result.warnings.append(f"{item.source_record_id}: {exception_message(exc)}")
        if not queued:
            result.warnings.append("No matching raw parse artifacts were available for reprocessing")
    finally:
        try:
            await adapter.close()
        finally:
            repository.finish_run(run_id, result)
    typer.echo(f"Reprocessed with parser {PARSER_VERSION}")
    typer.echo(result.model_dump_json(indent=2))


async def run_retention(source: str, execute: bool) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for retention review")
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = supabase_backend_key()
    storage = SupabaseArtifactStorage(supabase_url, service_key, os.getenv("RAW_ARTIFACT_BUCKET", "raw-artifacts")) if supabase_url and service_key else LocalArtifactStorage()
    rows = await DatabaseRepository(database_url, storage, source).purge_expired_artifacts(execute=execute)
    typer.echo(json.dumps({
        "source": source,
        "mode": "execute" if execute else "dry-run",
        "count": len(rows),
        "artifact_ids": [str(row["id"]) for row in rows],
    }, indent=2))


async def run_data_catalog_watch(lookback_days: int) -> None:
    """Check official open-data metadata without importing unreviewed datasets."""
    try:
        result = await watch_official_catalog(
            published_after=taipei_catalog_cutoff(lookback_days=lookback_days),
        )
    except DataGovCatalogError as exc:
        typer.echo(
            json.dumps({"status": "error", "message": exception_message(exc)}, ensure_ascii=False),
            err=True,
        )
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    if os.getenv("GITHUB_ACTIONS") == "true":
        for warning in github_warning_lines(result.candidates):
            typer.echo(warning, err=True)


@app.command()
def healthcheck(source: str = typer.Option("shwoo")) -> None:
    asyncio.run(run_healthcheck(source))


@app.command()
def sync(
    source: str = typer.Option("shwoo"),
    limit: int | None = typer.Option(None, min=1),
    manifest: Path | None = typer.Option(
        None,
        exists=True,
        file_okay=True,
        dir_okay=True,
        help="Human-exported detail JSON, one saved result HTML page, or a directory containing every result page",
    ),
) -> None:
    asyncio.run(run_sync(source, limit, manifest))


@app.command("publish-public-shwoo")
def publish_public_shwoo(limit: int | None = typer.Option(None, min=1)) -> None:
    """Backward-compatible Shwoo publisher alias."""
    asyncio.run(run_publish_public("shwoo", limit))


@app.command("publish-public")
def publish_public(
    source: str = typer.Option(..., help="Reviewed automated source key"),
    limit: int | None = typer.Option(None, min=1),
) -> None:
    """Preserve private artifacts and publish a sanitized official-source feed."""
    asyncio.run(run_publish_public(source, limit))


@app.command()
def reprocess(
    source: str = typer.Option("shwoo"),
    from_parser_version: str | None = typer.Option(None, help="Only raw artifacts first parsed by this version"),
    limit: int | None = typer.Option(None, min=1),
) -> None:
    """Re-run the current parser against checksum-addressed stored artifacts without live fetches."""
    asyncio.run(run_reprocess(source, from_parser_version, limit))


@app.command()
def retention(
    source: str = typer.Option("shwoo"),
    execute: bool = typer.Option(False, "--execute", help="Delete expired bytes and append tombstone records"),
) -> None:
    """Preview expired artifacts; deletion requires the explicit --execute flag."""
    asyncio.run(run_retention(source, execute))


@app.command("watch-data-catalog")
def watch_data_catalog(
    lookback_days: int = typer.Option(14, min=1, max=90),
) -> None:
    """Watch data.gov.tw metadata for new official vehicle-auction datasets."""
    asyncio.run(run_data_catalog_watch(lookback_days))
