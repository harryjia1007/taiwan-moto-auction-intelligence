from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from ingest import PARSER_VERSION
from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SyncResult
from ingest.public_feed import public_listing_payload
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
        sources = await self._json("GET", f"/rest/v1/sources?adapter_name=eq.{self.source_adapter}&select=id&limit=1")
        if not sources:
            raise RuntimeError(f"Production source registry has no {self.source_adapter} source")
        self.source_id = sources[0]["id"]
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

        normalized = record.model_dump(mode="json")
        payload_json = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        await self._json(
            "POST", "/rest/v1/snapshots?on_conflict=source_record_id,payload_checksum,parser_version",
            headers={**self.headers, "Prefer": "resolution=ignore-duplicates,return=minimal"},
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
            ),
        )
        return True

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

    async def finish(self, result: SyncResult) -> None:
        if not self.source_id or not self.run_id:
            return
        completed_at = datetime.now(UTC)
        try:
            await self._enforce_public_plate_retention(completed_at)
        except Exception as exc:
            result.failed += 1
            result.warnings.append(f"Public plate retention cleanup failed: {exc}")
        status = (
            "FAILED" if result.parsed == 0 and result.failed
            else "PARTIAL" if result.discovered == 0 or result.failed or result.warnings
            else "SUCCEEDED"
        )
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
        if status == "SUCCEEDED":
            source_update.update({"last_successful_at": completed_at.isoformat(), "status": "ACTIVE", "parser_version": PARSER_VERSION})
        elif status == "PARTIAL":
            source_update.update({"status": "PARTIAL", "parser_version": PARSER_VERSION})
        elif status == "FAILED":
            source_update.update({"status": "DEGRADED", "parser_version": PARSER_VERSION})
        await self._json("PATCH", f"/rest/v1/sources?id=eq.{self.source_id}", headers={**self.headers, "Prefer": "return=minimal"}, json=source_update)
