from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from ingest.adapters.base import SourceAccessDenied, SourceAdapter
from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SourceHealth
from ingest.official_documents import validated_official_document_url
from ingest.parser import parse_judicial_record


class JudicialMovableAdapter(SourceAdapter):
    """Import human-reviewed official links without contacting ``aomp109``."""

    ORIGIN = "https://aomp109.judicial.gov.tw"
    BASE_URL = f"{ORIGIN}/judbp/wkw/WHD1A02"
    INDEX_URL = f"{BASE_URL}.htm"
    PDF_URL = f"{BASE_URL}/DO_VIEWPDF.htm"
    ALLOWED_HOSTS = {"aomp109.judicial.gov.tw"}

    def __init__(
        self,
        manual_items: list[DiscoveredItem] | None = None,
        client: httpx.AsyncClient | None = None,
        request_interval: float = 1.0,
    ) -> None:
        self.manual_items = manual_items or []
        # Kept only for backwards-compatible dependency injection. No method in
        # this adapter performs an HTTP request; the caller retains ownership.
        self.client = client
        self.request_interval = request_interval

    async def close(self) -> None:
        return None

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self.ALLOWED_HOSTS
            or validated_official_document_url("judicial", url) is None
        ):
            raise ValueError(f"Blocked non-registered source URL: {url}")

    async def discover(self) -> list[DiscoveredItem]:
        if self.manual_items:
            for item in self.manual_items:
                self._validate_url(str(item.official_url))
            return sorted(self.manual_items, key=lambda item: item.source_record_id)
        raise SourceAccessDenied(
            "Judicial central movable-auction discovery is disabled; "
            "provide a human-reviewed official-link manifest"
        )

    async def fetch(self, item: DiscoveredItem) -> list[RawArtifact]:
        if not self.manual_items or all(
            candidate.source_record_id != item.source_record_id
            for candidate in self.manual_items
        ):
            raise SourceAccessDenied(
                "Judicial central artifacts require a human-reviewed manifest item"
            )
        self._validate_url(str(item.official_url))
        if not item.metadata:
            raise ValueError("Judicial manifest metadata is required for offline importing")
        fetched_at = datetime.now(UTC)
        record_content = json.dumps(item.metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        record_artifact = RawArtifact(
            official_url=item.official_url,
            fetched_at=fetched_at,
            mime_type="application/json",
            filename=f"judicial-{item.source_record_id}.json",
            content=record_content,
            http_headers={"x-artifact-provenance": "human-reviewed-manifest-row"},
            checksum_sha256=hashlib.sha256(record_content).hexdigest(),
        )
        # The complete document remains on the publisher's site. The importer
        # records only the reviewed official URL and transcribed structured row.
        return [record_artifact]

    async def parse(self, item: DiscoveredItem, artifacts: list[RawArtifact]) -> ParsedAuctionRecord:
        structured = next((artifact for artifact in artifacts if artifact.mime_type == "application/json"), None)
        if not structured:
            raise ValueError("Judicial structured result artifact is missing")
        return parse_judicial_record(item, structured)

    async def healthcheck(self) -> SourceHealth:
        return SourceHealth(
            source="judicial",
            status="DEGRADED",
            checked_at=datetime.now(UTC),
            response_ms=0,
            message="司法院中央動產拍賣僅允許人工核對官方連結後離線匯入",
            warnings=["本程式不對 aomp109 執行自動搜尋或下載"],
        )
