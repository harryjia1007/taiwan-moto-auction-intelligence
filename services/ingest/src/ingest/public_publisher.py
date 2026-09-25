from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from ingest import PARSER_VERSION
from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SyncResult
from ingest.official_documents import official_document_urls
from ingest.public_feed import public_listing_payload
from ingest.repository import validate_artifact_evidence
from ingest.source_policy import AccessDecision, SourceAccessBlocked
from ingest.storage import SupabaseArtifactStorage


class SupabasePublicPublisher:
    """Publish a sanitized live feed while preserving private source artifacts.

    This path uses the Supabase service-role REST API, so a hosted scheduler does
    not need a direct PostgreSQL password. The service key stays server-only.
    """

    def __init__(
        self,
        url: str,
        service_role_key: str,
        bucket: str = "raw-artifacts",
        *,
        source_adapter: str = "shwoo",
        source_name: str = "臺北惜物網",
    ) -> None:
        self.url = url.rstrip("/")
        self.headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(base_url=self.url, headers=self.headers, timeout=30)
        self.storage = SupabaseArtifactStorage(self.url, service_role_key, bucket)
        self.source_adapter = source_adapter
        self.source_name = source_name
        self.source_id: str | None = None
        self.run_id: str | None = None

    async def close(self) -> None:
        await self.client.aclose()

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self.client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"Supabase publisher request failed: {method} {path.split('?', 1)[0]} HTTP {response.status_code}")
        if not response.content:
            return None
        return response.json()

    async def start(self) -> str:
        encoded_adapter = quote(self.source_adapter, safe="")
        sources = await self._json(
            "GET",
            f"/rest/v1/sources?adapter_name=eq.{encoded_adapter}&select=id&limit=2",
        )
        if not isinstance(sources, list) or len(sources) != 1 or not isinstance(sources[0], dict):
            raise RuntimeError(
                f"Production source registry does not have exactly one {self.source_adapter} source"
            )
        source_id = sources[0].get("id")
        if not source_id:
            raise RuntimeError(f"Production source registry has no valid id for {self.source_adapter}")
        encoded_source_id = quote(str(source_id), safe="")
        policies = await self._json(
            "GET",
            "/rest/v1/source_access_policies"
            f"?source_id=eq.{encoded_source_id}&select=decision&limit=2",
        )
        if not isinstance(policies, list) or len(policies) != 1 or not isinstance(policies[0], dict):
            raise SourceAccessBlocked(
                f"Production source-access registry has no unique policy for {self.source_adapter}; "
                "public discovery was blocked"
            )
        decision = str(policies[0].get("decision") or "")
        if decision != AccessDecision.ALLOW:
            raise SourceAccessBlocked(
                f"Production source-access policy for {self.source_adapter} is "
                f"{decision or 'UNKNOWN'}, not ALLOW; public discovery was blocked"
            )
        self.source_id = str(source_id)
        runs = await self._json(
            "POST", "/rest/v1/sync_runs",
            headers={**self.headers, "Prefer": "return=representation"},
            json={"source_id": self.source_id, "status": "RUNNING", "parser_version": PARSER_VERSION},
        )
        self.run_id = runs[0]["id"]
        return self.run_id

    async def publish(self, item: DiscoveredItem, artifacts: list[RawArtifact], record: ParsedAuctionRecord) -> bool:
        if not self.source_id or not self.run_id:
            raise RuntimeError("Publisher run has not started")
        # Hosted publishing must enforce the same checksum/evidence boundary as
        # direct PostgreSQL persistence before any REST or Storage write occurs.
        validate_artifact_evidence(artifacts, record.evidence)
        checksum_filter = ",".join(artifact.checksum_sha256 for artifact in artifacts)
        known_artifacts = await self._json(
            "GET",
            "/rest/v1/raw_artifacts"
            f"?checksum_sha256=in.({checksum_filter})&select=id&limit={len(artifacts)}",
        )
        known_ids = [str(row.get("id")) for row in (known_artifacts or []) if isinstance(row, dict) and row.get("id")]
        if known_ids:
            tombstones = await self._json(
                "GET",
                "/rest/v1/artifact_tombstones"
                f"?artifact_id=in.({','.join(known_ids)})&select=artifact_id&limit=1",
            )
            if tombstones:
                raise ValueError(
                    "A previously purged artifact checksum was fetched again; "
                    "storage restoration requires an explicit audited artifact generation"
                )
        source_rows = await self._json(
            "POST", "/rest/v1/source_records?on_conflict=source_id,source_record_id",
            headers={**self.headers, "Prefer": "resolution=merge-duplicates,return=representation"},
            json={
                "source_id": self.source_id, "source_record_id": item.source_record_id,
                "official_url": str(item.official_url), "original_title": item.title,
                "last_seen_at": datetime.now(UTC).isoformat(), "active": True,
                "last_content_checksum": artifacts[0].checksum_sha256,
            },
        )
        source_record_uuid = source_rows[0]["id"]
        artifact_ids: list[str] = []
        for artifact in artifacts:
            storage_path = await self.storage.put(artifact)
            rows = await self._json(
                "GET", f"/rest/v1/raw_artifacts?checksum_sha256=eq.{artifact.checksum_sha256}&storage_path=eq.{quote(storage_path, safe='')}&select=id&limit=1",
            )
            if not rows:
                rows = await self._json(
                    "POST", "/rest/v1/raw_artifacts",
                    headers={**self.headers, "Prefer": "return=representation"},
                    json={
                        "source_record_id": source_record_uuid, "sync_run_id": self.run_id,
                        "official_url": str(artifact.official_url), "fetched_at": artifact.fetched_at.isoformat(),
                        "http_status": artifact.http_status, "http_headers": artifact.http_headers,
                        "mime_type": artifact.mime_type, "filename": artifact.filename,
                        "checksum_sha256": artifact.checksum_sha256, "content_length": len(artifact.content),
                        "storage_path": storage_path, "extraction_status": "PARSED", "parser_version": PARSER_VERSION,
                        "retention_until": (max(artifact.fetched_at, record.ends_at or artifact.fetched_at) + timedelta(days=365)).isoformat(),
                    },
                )
            artifact_ids.append(rows[0]["id"])

        for order, artifact_id in enumerate(artifact_ids):
            link_path = (
                "/rest/v1/source_record_artifacts"
                f"?source_record_id=eq.{quote(str(source_record_uuid), safe='')}"
                f"&artifact_id=eq.{quote(str(artifact_id), safe='')}"
            )
            await self._json(
                "POST",
                "/rest/v1/source_record_artifacts?on_conflict=source_record_id,artifact_id",
                headers={**self.headers, "Prefer": "resolution=ignore-duplicates,return=minimal"},
                json={
                    "source_record_id": source_record_uuid,
                    "artifact_id": artifact_id,
                    "first_sync_run_id": self.run_id,
                    "last_sync_run_id": self.run_id,
                    "artifact_role": "PRIMARY" if order == 0 else "SUPPORTING",
                    "sort_order": order,
                    "last_seen_at": datetime.now(UTC).isoformat(),
                },
            )
            # Keep the original first-seen run immutable on repeat syncs while
            # advancing the last-seen audit marker. A merge upsert would
            # silently rewrite first_sync_run_id on every scheduled run.
            await self._json(
                "PATCH",
                link_path,
                headers={**self.headers, "Prefer": "return=minimal"},
                json={
                    "last_sync_run_id": self.run_id,
                    "last_seen_at": datetime.now(UTC).isoformat(),
                },
            )

        cached_documents = {
            str(artifact.official_url): artifact_id
            for artifact, artifact_id in zip(artifacts, artifact_ids, strict=True)
            if artifact.mime_type == "application/pdf"
        }
        for official_url in official_document_urls(
            record,
            self.source_adapter,
            artifact_urls=cached_documents,
        ):
            cached_artifact_id = cached_documents.get(official_url)
            document = {
                "source_record_id": source_record_uuid,
                "title": (
                    f"{record.title}－官方拍賣公告"
                    if cached_artifact_id is not None
                    else f"{record.title}－官方完整全文"
                ),
                "document_type": (
                    "OFFICIAL_AUCTION_NOTICE"
                    if cached_artifact_id is not None
                    else "OFFICIAL_LINK_ONLY"
                ),
                "official_url": official_url,
            }
            if cached_artifact_id is not None:
                document["artifact_id"] = cached_artifact_id
            await self._json(
                "POST",
                "/rest/v1/documents?on_conflict=source_record_id,official_url",
                headers={
                    **self.headers,
                    "Prefer": (
                        "resolution=merge-duplicates,return=minimal"
                        if cached_artifact_id is not None
                        else "resolution=ignore-duplicates,return=minimal"
                    ),
                },
                json=document,
            )

        normalized = record.model_dump(mode="json")
        payload_json = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        snapshot_rows = await self._json(
            "POST", "/rest/v1/snapshots?on_conflict=source_record_id,payload_checksum,parser_version",
            headers={**self.headers, "Prefer": "resolution=ignore-duplicates,return=representation"},
            json={
                "source_record_id": source_record_uuid, "artifact_id": artifact_ids[0],
                "normalized_payload": normalized,
                "payload_checksum": hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
                "parser_version": PARSER_VERSION,
            },
        )
        await self._json(
            "POST", "/rest/v1/public_live_motorcycle_listings?on_conflict=id",
            headers={**self.headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
            json=public_listing_payload(
                record,
                source_adapter=self.source_adapter,
                source_name=self.source_name,
                artifact_document_urls=tuple(cached_documents),
            ),
        )
        # Match the direct PostgreSQL repository: a record is "changed" only
        # when this parser version creates a new immutable normalized snapshot.
        # Routine re-fetches still refresh last-seen/public sync timestamps but
        # do not inflate source-health change metrics.
        return bool(snapshot_rows)

    async def _enforce_public_plate_retention(self, now: datetime | None = None) -> None:
        reference_time = now or datetime.now(UTC)
        if reference_time.tzinfo is None:
            raise ValueError("Public plate retention requires an aware UTC reference time")
        cutoff = (reference_time.astimezone(UTC) - timedelta(days=30)).isoformat()
        encoded_cutoff = quote(cutoff, safe="")
        await self._json(
            "PATCH",
            "/rest/v1/public_live_motorcycle_listings"
            f"?plate_number=not.is.null&or=(ends_at.is.null,ends_at.lt.{encoded_cutoff})",
            headers={**self.headers, "Prefer": "return=minimal"},
            json={"plate_number": None},
        )

    async def _enforce_public_photo_rights(self) -> None:
        """Remove every anonymous photo until a source-specific reuse grant exists."""
        await self._json(
            "PATCH",
            "/rest/v1/public_live_motorcycle_listings?id=not.is.null",
            headers={**self.headers, "Prefer": "return=minimal"},
            json={"photo_urls": []},
        )

    def _public_health_payload(
        self,
        result: SyncResult,
        *,
        completed_at: datetime,
        status: str,
        access_decision: AccessDecision | None,
    ) -> dict[str, Any]:
        parse_success_rate = (
            round((result.parsed / result.fetched) * 100, 2)
            if result.fetched
            else None
        )
        warning_codes: list[str] = []
        if result.discovered == 0:
            warning_codes.append("ZERO_DISCOVERY")
        if status == "FAILED":
            warning_codes.append("RUN_FAILED")
        if parse_success_rate is not None and parse_success_rate < 90:
            warning_codes.append("PARSE_BELOW_90")
        if access_decision != AccessDecision.ALLOW:
            warning_codes.append("POLICY_BLOCKED")
        if status == "PARTIAL":
            warning_codes.append("PARTIAL_COVERAGE")

        source_status = (
            "DISABLED" if access_decision == AccessDecision.DISABLED
            else "PARTIAL" if access_decision == AccessDecision.MANUAL_ONLY
            else "DEGRADED" if access_decision != AccessDecision.ALLOW or status == "FAILED"
            else "PARTIAL" if status == "PARTIAL"
            else "ACTIVE"
        )
        payload: dict[str, Any] = {
            "source_adapter": self.source_adapter,
            "source_name": self.source_name,
            "status": source_status,
            "last_run_status": status,
            "last_attempted_at": completed_at.isoformat(),
            "discovered_count": result.discovered,
            "fetched_count": result.fetched,
            "parsed_count": result.parsed,
            "changed_count": result.changed,
            "failed_count": result.failed,
            "parse_success_rate": parse_success_rate,
            "warning_codes": list(dict.fromkeys(warning_codes)),
            "stale_after_hours": 72 if self.source_adapter in {"pcc", "customs"} else 36,
            "updated_at": completed_at.isoformat(),
        }
        if status == "SUCCEEDED" and access_decision == AccessDecision.ALLOW:
            payload["last_successful_at"] = completed_at.isoformat()
        return payload

    async def finish(self, result: SyncResult) -> None:
        if not self.source_id or not self.run_id:
            return
        completed_at = datetime.now(UTC)
        try:
            await self._enforce_public_plate_retention(completed_at)
        except Exception as exc:
            result.failed += 1
            result.warnings.append(f"Public plate retention cleanup failed: {exc}")
        try:
            await self._enforce_public_photo_rights()
        except Exception as exc:
            result.failed += 1
            result.warnings.append(f"Public photo-rights cleanup failed: {exc}")
        access_decision: AccessDecision | None = None
        try:
            encoded_source_id = quote(self.source_id, safe="")
            policies = await self._json(
                "GET",
                "/rest/v1/source_access_policies"
                f"?source_id=eq.{encoded_source_id}&select=decision&limit=2",
            )
            if isinstance(policies, list) and len(policies) == 1 and isinstance(policies[0], dict):
                access_decision = AccessDecision(str(policies[0].get("decision") or ""))
        except Exception:
            access_decision = None
        if access_decision != AccessDecision.ALLOW:
            warning = (
                "Production source-access policy changed during the run; "
                "source promotion was blocked"
            )
            if warning not in result.warnings:
                result.warnings.append(warning)
            try:
                encoded_adapter = quote(self.source_adapter, safe="")
                await self._json(
                    "PATCH",
                    "/rest/v1/public_live_motorcycle_listings"
                    f"?source_adapter=eq.{encoded_adapter}&active=eq.true",
                    headers={**self.headers, "Prefer": "return=minimal"},
                    json={"active": False},
                )
            except Exception as exc:
                result.failed += 1
                message = str(exc).strip() or exc.__class__.__name__
                result.warnings.append(f"Policy-change public deactivation failed: {message}")
        status = (
            "FAILED" if result.parsed == 0 and result.failed
            else "PARTIAL" if result.discovered == 0 or result.failed or result.warnings
            else "SUCCEEDED"
        )
        try:
            await self._json(
                "POST",
                "/rest/v1/public_source_health?on_conflict=source_adapter",
                headers={**self.headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
                json=self._public_health_payload(
                    result,
                    completed_at=completed_at,
                    status=status,
                    access_decision=access_decision,
                ),
            )
        except Exception as exc:
            result.failed += 1
            result.warnings.append(f"Sanitized public source-health publication failed: {exc}")
            status = "PARTIAL" if result.parsed else "FAILED"
        await self._json(
            "PATCH", f"/rest/v1/sync_runs?id=eq.{self.run_id}",
            headers={**self.headers, "Prefer": "return=minimal"},
            json={
                "completed_at": completed_at.isoformat(), "status": status,
                "discovered_count": result.discovered, "fetched_count": result.fetched,
                "parsed_count": result.parsed, "changed_count": result.changed,
                "failed_count": result.failed, "warnings": result.warnings,
            },
        )
        source_update: dict[str, Any] = {"last_attempted_at": completed_at.isoformat()}
        if access_decision == AccessDecision.DISABLED:
            source_update.update({"status": "DISABLED", "parser_version": PARSER_VERSION})
        elif access_decision == AccessDecision.MANUAL_ONLY:
            source_update.update({"status": "PARTIAL", "parser_version": PARSER_VERSION})
        elif access_decision != AccessDecision.ALLOW:
            source_update.update({"status": "DEGRADED", "parser_version": PARSER_VERSION})
        elif status == "SUCCEEDED":
            source_update.update({"last_successful_at": completed_at.isoformat(), "status": "ACTIVE", "parser_version": PARSER_VERSION})
        elif status == "PARTIAL":
            source_update.update({"status": "PARTIAL", "parser_version": PARSER_VERSION})
        elif status == "FAILED":
            source_update.update({"status": "DEGRADED", "parser_version": PARSER_VERSION})
        await self._json("PATCH", f"/rest/v1/sources?id=eq.{self.source_id}", headers={**self.headers, "Prefer": "return=minimal"}, json=source_update)
