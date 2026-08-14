from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ingest.adapters.base import SourceAdapter, contact_user_agent, enforce_http_status
from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SourceHealth
from ingest.parser import parse_moj_enforcement_detail


class MojEnforcementManualAdapter(SourceAdapter):
    """CAPTCHA-safe detail importer for Administrative Enforcement auctions.

    Discovery URLs must be exported by a human after using the official search.
    This adapter never submits, solves, reads, or reuses CAPTCHA values.
    """

    ORIGIN = "https://www.tpkonsale.moj.gov.tw"
    SEARCH_URL = f"{ORIGIN}/Chattel"
    ALLOWED_HOSTS = {"www.tpkonsale.moj.gov.tw"}
    MAX_BYTES = 25 * 1024 * 1024
    MAX_ATTACHMENTS = 25

    def __init__(
        self,
        manual_items: list[DiscoveredItem] | None = None,
        client: httpx.AsyncClient | None = None,
        request_interval: float = 1.0,
    ) -> None:
        self.manual_items = manual_items or []
        self.client = client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(25),
            headers={"User-Agent": contact_user_agent("0.4")},
        )
        self._owns_client = client is None
        self.request_interval = request_interval
        self._last_request = 0.0
        self._request_lock = asyncio.Lock()

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    def _validate_url(self, url: str, *, detail_only: bool = False) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in self.ALLOWED_HOSTS:
            raise ValueError(f"Blocked non-registered source URL: {url}")
        if detail_only:
            identifiers = parse_qs(parsed.query).get("NO", [])
            if parsed.path != "/Detail/Chattel" or len(identifiers) != 1:
                raise ValueError("Administrative Enforcement manifest must contain official /Detail/Chattel?NO= URLs")

    async def _request(self, url: str) -> httpx.Response:
        self._validate_url(url)
        last_error: Exception | None = None
        for attempt in range(3):
            async with self._request_lock:
                delay = self.request_interval - (time.monotonic() - self._last_request)
                if delay > 0:
                    await asyncio.sleep(delay)
                try:
                    response = await self.client.get(url, headers={"Referer": self.SEARCH_URL})
                    self._last_request = time.monotonic()
                    enforce_http_status(response)
                    self._validate_url(str(response.url))
                    if len(response.content) > self.MAX_BYTES:
                        raise ValueError(f"Artifact exceeds {self.MAX_BYTES} bytes")
                    return response
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
            if attempt < 2:
                await asyncio.sleep(2**attempt)
        assert last_error is not None
        raise last_error

    async def discover(self) -> list[DiscoveredItem]:
        for item in self.manual_items:
            self._validate_url(str(item.official_url), detail_only=True)
        return sorted(self.manual_items, key=lambda item: item.source_record_id)

    @staticmethod
    def _artifact(response: httpx.Response, fetched_at: datetime) -> RawArtifact:
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type == "application/octet-stream" and response.content.startswith(b"%PDF"):
            content_type = "application/pdf"
        allowed = content_type == "text/html" or content_type == "application/pdf" or content_type.startswith("image/")
        if not allowed:
            raise ValueError(f"Unsupported Administrative Enforcement MIME type: {content_type}")
        filename = PurePosixPath(urlparse(str(response.url)).path).name or "moj-enforcement.html"
        return RawArtifact(
            official_url=str(response.url), fetched_at=fetched_at, mime_type=content_type, filename=filename,
            content=response.content, http_status=response.status_code, http_headers=dict(response.headers),
            checksum_sha256=hashlib.sha256(response.content).hexdigest(),
        )

    async def fetch(self, item: DiscoveredItem) -> list[RawArtifact]:
        self._validate_url(str(item.official_url), detail_only=True)
        fetched_at = datetime.now(UTC)
        primary = await self._request(str(item.official_url))
        if "text/html" not in primary.headers.get("content-type", ""):
            raise ValueError("Administrative Enforcement detail returned an unexpected MIME type")
        artifacts = [self._artifact(primary, fetched_at)]
        soup = BeautifulSoup(primary.content, "html.parser")
        urls: list[str] = []
        for node in soup.select("#slider img[src], #carousel img[src], a[href*='/File/Download']"):
            relative = node.get("src") or node.get("href")
            if not relative:
                continue
            url = urljoin(str(primary.url), relative)
            if url not in urls and urlparse(url).hostname in self.ALLOWED_HOSTS:
                urls.append(url)
        for url in urls[: self.MAX_ATTACHMENTS]:
            artifacts.append(self._artifact(await self._request(url), fetched_at))
        return artifacts

    async def parse(self, item: DiscoveredItem, artifacts: list[RawArtifact]) -> ParsedAuctionRecord:
        return parse_moj_enforcement_detail(item, artifacts)

    async def healthcheck(self) -> SourceHealth:
        start = time.monotonic()
        try:
            response = await self._request(self.SEARCH_URL)
            captcha_present = 'name="CAPTCHA"' in response.text and "動產拍賣搜尋" in response.text
            return SourceHealth(
                source="moj_enforcement",
                status="PARTIAL" if captcha_present else "DEGRADED",
                checked_at=datetime.now(UTC),
                response_ms=round((time.monotonic() - start) * 1000),
                message="Official search is online; manual CAPTCHA-safe manifest import is required" if captcha_present else "Expected CAPTCHA search markers were absent",
                warnings=["Automated discovery is intentionally disabled; no CAPTCHA is solved or bypassed"],
            )
        except Exception as exc:
            return SourceHealth(source="moj_enforcement", status="DEGRADED", checked_at=datetime.now(UTC), message=str(exc))
