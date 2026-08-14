from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import typer

from ingest.adapters import JudicialMovableAdapter, MojAuctionAdapter, MojEnforcementManualAdapter, PccAssetSaleAdapter, ShwooAdapter
from ingest.adapters.base import SourceAdapter
from ingest import PARSER_VERSION
from ingest.models import DiscoveredItem, SyncResult
from ingest.repository import DatabaseRepository
from ingest.public_publisher import SupabasePublicPublisher
from ingest.storage import LocalArtifactStorage, SupabaseArtifactStorage
from ingest.source_policy import AccessDecision, policy_for, require_live_access

app = typer.Typer(no_args_is_help=True, help="Read-only official motorcycle auction ingestion")


def exception_message(exc: Exception) -> str:
    """Keep run warnings useful even for exceptions with an empty string form."""
    return str(exc).strip() or exc.__class__.__name__


def load_enforcement_manifest(path: Path) -> list[DiscoveredItem]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise typer.BadParameter("Administrative Enforcement manifest must be a JSON array")
    items: list[DiscoveredItem] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise typer.BadParameter(f"Manifest row {index + 1} must be an object")
        official_url = str(row.get("official_url") or "")
        parsed = urlparse(official_url)
        no_values = parse_qs(parsed.query).get("NO", [])
        if parsed.scheme != "https" or parsed.hostname != "www.tpkonsale.moj.gov.tw" or parsed.path != "/Detail/Chattel" or len(no_values) != 1:
            raise typer.BadParameter(f"Manifest row {index + 1} must use an official /Detail/Chattel?NO= URL")
        title = str(row.get("title") or "").strip()
        if not title:
            raise typer.BadParameter(f"Manifest row {index + 1} requires the official motorcycle title/summary")
        metadata = {key: row[key] for key in ("organization", "auction_round") if row.get(key) not in (None, "")}
        items.append(DiscoveredItem(
            source_record_id=no_values[0], official_url=official_url, title=title,
            discovery_url=MojEnforcementManualAdapter.SEARCH_URL, metadata=metadata,
        ))
    return items


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
    if source == "moj_auction":
        return MojAuctionAdapter(request_interval=float(os.getenv("MOJ_AUCTION_REQUEST_INTERVAL_SECONDS", "1")))
    if source == "moj_enforcement":
        items = load_enforcement_manifest(manifest) if manifest else []
        return MojEnforcementManualAdapter(items, request_interval=float(os.getenv("MOJ_ENFORCEMENT_REQUEST_INTERVAL_SECONDS", "1")))
    raise typer.BadParameter("Implemented sources are: shwoo, pcc, judicial, moj_auction, moj_enforcement")


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
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    storage = SupabaseArtifactStorage(supabase_url, service_key, os.getenv("RAW_ARTIFACT_BUCKET", "raw-artifacts")) if supabase_url and service_key else LocalArtifactStorage()
    repository = DatabaseRepository(database_url, storage, source)
    if source == "moj_enforcement" and manifest is None:
        raise typer.BadParameter("moj_enforcement sync requires --manifest exported after a human completes the official CAPTCHA search")
    if source == "judicial" and manifest is None:
        raise typer.BadParameter("judicial sync requires --manifest containing human-reviewed official PDF links")
    adapter = adapter_for(source, manifest)
    result = SyncResult(source=source, discovered=0, fetched=0, parsed=0, changed=0, failed=0)
    run_id = repository.start_run()
    try:
        items = await adapter.discover()
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
            except Exception as exc:
                result.failed += 1
                result.warnings.append(f"{item.source_record_id}: {exception_message(exc)}")
        if result.fetched and (result.parsed / result.fetched) < 0.9:
            result.warnings.append("Parse success rate fell below 90%")
    finally:
        await adapter.close()
        repository.finish_run(run_id, result)
    typer.echo(result.model_dump_json(indent=2))


async def run_publish_public_shwoo(limit: int | None) -> None:
    require_live_access("shwoo")
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    adapter = adapter_for("shwoo")
    publisher = SupabasePublicPublisher(supabase_url, service_key, os.getenv("RAW_ARTIFACT_BUCKET", "raw-artifacts"))
    result = SyncResult(source="shwoo", discovered=0, fetched=0, parsed=0, changed=0, failed=0)
    await publisher.start()
    try:
        items = await adapter.discover()
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
            except Exception as exc:
                result.failed += 1
                result.warnings.append(f"{item.source_record_id}: {exception_message(exc)}")
        if result.fetched and result.parsed / result.fetched < 0.9:
            result.warnings.append("Parse success rate fell below 90%")
    finally:
        await adapter.close()
        await publisher.finish(result)
        await publisher.close()
    typer.echo(result.model_dump_json(indent=2))


async def run_reprocess(source: str, from_parser_version: str | None, limit: int | None) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for reprocessing; run the local Supabase stack first")
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    storage = SupabaseArtifactStorage(supabase_url, service_key, os.getenv("RAW_ARTIFACT_BUCKET", "raw-artifacts")) if supabase_url and service_key else LocalArtifactStorage()
    repository = DatabaseRepository(database_url, storage, source)
    adapter = adapter_for(source)
    run_id = repository.start_run()
    result = SyncResult(source=source, discovered=0, fetched=0, parsed=0, changed=0, failed=0)
    try:
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
        await adapter.close()
        repository.finish_run(run_id, result)
    typer.echo(f"Reprocessed with parser {PARSER_VERSION}")
    typer.echo(result.model_dump_json(indent=2))


async def run_retention(source: str, execute: bool) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for retention review")
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    storage = SupabaseArtifactStorage(supabase_url, service_key, os.getenv("RAW_ARTIFACT_BUCKET", "raw-artifacts")) if supabase_url and service_key else LocalArtifactStorage()
    rows = await DatabaseRepository(database_url, storage, source).purge_expired_artifacts(execute=execute)
    typer.echo(json.dumps({
        "source": source,
        "mode": "execute" if execute else "dry-run",
        "count": len(rows),
        "artifact_ids": [str(row["id"]) for row in rows],
    }, indent=2))


@app.command()
def healthcheck(source: str = typer.Option("shwoo")) -> None:
    asyncio.run(run_healthcheck(source))


@app.command()
def sync(
    source: str = typer.Option("shwoo"),
    limit: int | None = typer.Option(None, min=1),
    manifest: Path | None = typer.Option(None, exists=True, dir_okay=False, help="Human-exported Administrative Enforcement detail URL manifest"),
) -> None:
    asyncio.run(run_sync(source, limit, manifest))


@app.command("publish-public-shwoo")
def publish_public_shwoo(limit: int | None = typer.Option(None, min=1)) -> None:
    """Publish the sanitized live Shwoo feed and preserve private raw artifacts."""
    asyncio.run(run_publish_public_shwoo(limit))


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
