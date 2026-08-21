from __future__ import annotations

import asyncio
import hashlib
import re
import time
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from ingest.adapters.base import SourceAdapter, contact_user_agent, enforce_http_status
from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SourceHealth
from ingest.parser import parse_moj_auction_detail


class MojExternalDetailBlocked(ValueError):
    """A central MOJ record points outside the reviewed collection boundary."""

    def __init__(self, target_url: str) -> None:
        self.target_url = target_url
        super().__init__(f"Blocked non-registered source URL: {target_url}")


class MojAuctionAdapter(SourceAdapter):
    """Public read-only adapter for the MOJ centralized seized-property portal."""

    ORIGIN = "https://auction.moj.gov.tw"
    LIST_URL = f"{ORIGIN}/1724/1726/searchList"
    ALLOWED_HOSTS = {"auction.moj.gov.tw"}
    MAX_BYTES = 25 * 1024 * 1024
    MAX_PAGES = 10
    PAGE_SIZE = 100
    MAX_ATTACHMENTS = 25
    ARTIFACT_HEADER_ALLOWLIST = frozenset({
        "cache-control",
        "content-length",
        "content-type",
        "etag",
        "last-modified",
        "location",
    })
    TABLE_ROW_PATTERN = re.compile(rb"<tr\b[^>]*>.*?</tr\s*>", re.IGNORECASE | re.DOTALL)
    PARTIAL_FAILURE_KEY = "ingest_partial_failure"
    VEHICLE_TERMS = (
        "機車", "機器腳踏車", "重機", "汽車", "小客車", "大客車",
        "小貨車", "大貨車", "客貨兩用車", "休旅車", "轎車", "廂型車", "貨車",
    )

    def __init__(self, client: httpx.AsyncClient | None = None, request_interval: float = 1.0) -> None:
        self.client = client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(25),
            headers={"User-Agent": contact_user_agent("0.4")},
        )
        self._owns_client = client is None
        self.request_interval = request_interval
        self._last_request = 0.0
        self._request_lock = asyncio.Lock()
        self._central_summary_artifacts: dict[str, RawArtifact] = {}

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError(f"Blocked non-registered source URL: {url}") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self.ALLOWED_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
        ):
            raise ValueError(f"Blocked non-registered source URL: {url}")

    @classmethod
    def _artifact_headers(cls, response: httpx.Response) -> dict[str, str]:
        """Retain reproducibility metadata without persisting cookies or credentials."""
        return {
            name.lower(): value
            for name, value in response.headers.items()
            if name.lower() in cls.ARTIFACT_HEADER_ALLOWLIST
        }

    async def _request(self, url: str) -> httpx.Response:
        self._validate_url(url)
        last_error: Exception | None = None
        for attempt in range(3):
            async with self._request_lock:
                delay = self.request_interval - (time.monotonic() - self._last_request)
                if delay > 0:
                    await asyncio.sleep(delay)
                try:
                    current_url = url
                    for _ in range(6):
                        response = await self.client.get(
                            current_url,
                            headers={"Referer": self.LIST_URL},
                            follow_redirects=False,
                        )
                        self._last_request = time.monotonic()
                        if not response.is_redirect:
                            break
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("MOJ redirect response did not include a location")
                        current_url = urljoin(str(response.url), location)
                        try:
                            self._validate_url(current_url)
                        except ValueError as exc:
                            # Do not contact an agency site merely because the
                            # central portal redirects there. Each host needs a
                            # separately reviewed access policy.
                            raise MojExternalDetailBlocked(current_url) from exc
                    else:
                        raise ValueError("MOJ redirect limit exceeded")
                    enforce_http_status(response)
                    self._validate_url(str(response.url))
                    if len(response.content) > self.MAX_BYTES:
                        raise ValueError(f"Artifact exceeds {self.MAX_BYTES} bytes")
                    return response
                except ValueError:
                    # Policy, MIME-size, and redirect validation failures are
                    # deterministic; retrying them only repeats unsafe input.
                    raise
                except httpx.HTTPError as exc:
                    last_error = exc
            if attempt < 2:
                await asyncio.sleep(2**attempt)
        assert last_error is not None
        raise last_error

    @classmethod
    def _item_from_row(cls, row: Tag) -> DiscoveredItem | None:
        link = row.select_one("td[data-title='標題'] a[href]")
        if not link:
            return None
        title = " ".join(link.stripped_strings).strip()
        if not any(term in title for term in cls.VEHICLE_TERMS) or "電力機車" in title:
            return None
        href = urljoin(cls.ORIGIN, link.get("href", ""))
        parsed = urlparse(href)
        if parsed.hostname not in cls.ALLOWED_HOSTS:
            return None
        post_match = re.search(r"/1724/1726/(\d+)(?:/post)?", parsed.path)
        node_id = parse_qs(parsed.query).get("nodeId", [""])[0]
        media_match = re.search(r"/media/([^/]+)/(.+)", parsed.path)
        record_id = post_match.group(1) if post_match else f"node-{node_id}" if node_id else f"media-{media_match.group(1)}-{PurePosixPath(parsed.path).name}" if media_match else ""
        if not record_id:
            return None
        cells = {cell.get("data-title"): " ".join(cell.stripped_strings).strip() for cell in row.select("td[data-title]")}
        return DiscoveredItem(
            source_record_id=record_id,
            official_url=href,
            title=title,
            discovery_url=cls.LIST_URL,
            metadata={"organization": cells.get("單位", ""), "published_date": cells.get("張貼日", "")},
        )

    @classmethod
    def _items(cls, content: bytes) -> list[DiscoveredItem]:
        soup = BeautifulSoup(content, "html.parser")
        found: dict[str, DiscoveredItem] = {}
        for row in soup.select("table.table_list tbody tr"):
            item = cls._item_from_row(row)
            if item:
                found[item.source_record_id] = item
        return list(found.values())

    @classmethod
    def _exact_vehicle_rows(cls, content: bytes) -> dict[str, bytes]:
        """Retain the exact central-list row bytes for a safe summary fallback."""
        rows: dict[str, bytes] = {}
        for match in cls.TABLE_ROW_PATTERN.finditer(content):
            raw_row = match.group(0)
            row = BeautifulSoup(raw_row, "html.parser").find("tr")
            if not isinstance(row, Tag):
                continue
            item = cls._item_from_row(row)
            if item:
                rows[item.source_record_id] = raw_row
        return rows

    @staticmethod
    def _central_summary_artifact(
        response: httpx.Response,
        item: DiscoveredItem,
        row_content: bytes,
        fetched_at: datetime,
    ) -> RawArtifact:
        """Build a per-record artifact from an exact byte slice of the official list response."""
        return RawArtifact(
            official_url=str(response.url),
            fetched_at=fetched_at,
            mime_type="text/html",
            filename=f"moj-auction-list-row-{item.source_record_id}.html",
            content=row_content,
            http_status=response.status_code,
            http_headers=MojAuctionAdapter._artifact_headers(response),
            checksum_sha256=hashlib.sha256(row_content).hexdigest(),
        )

    async def discover(self) -> list[DiscoveredItem]:
        self._central_summary_artifacts.clear()
        found: dict[str, DiscoveredItem] = {}
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.LIST_URL}?{urlencode({'Page': page, 'PageSize': self.PAGE_SIZE, 'type': '01'})}"
            response = await self._request(url)
            if "text/html" not in response.headers.get("content-type", ""):
                raise ValueError("MOJ auction list returned an unexpected MIME type")
            items = self._items(response.content)
            exact_rows = self._exact_vehicle_rows(response.content)
            fetched_at = datetime.now(UTC)
            for item in items:
                found[item.source_record_id] = item
                raw_row = exact_rows.get(item.source_record_id)
                if raw_row:
                    self._central_summary_artifacts[item.source_record_id] = self._central_summary_artifact(
                        response, item, raw_row, fetched_at
                    )
            soup = BeautifulSoup(response.content, "html.parser")
            if not soup.select_one(f"ul.page a[href*='Page={page + 1}']"):
                break
        return sorted(found.values(), key=lambda item: item.source_record_id)

    @staticmethod
    def _artifact(response: httpx.Response, fetched_at: datetime) -> RawArtifact:
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type == "application/octet-stream" and response.content.startswith(b"%PDF"):
            content_type = "application/pdf"
        allowed = content_type in {"text/html", "application/pdf", "application/zip", "application/x-zip-compressed"} or content_type.startswith("image/")
        if not allowed:
            raise ValueError(f"Unsupported MOJ artifact MIME type: {content_type}")
        filename = PurePosixPath(urlparse(str(response.url)).path).name or "moj-auction.html"
        return RawArtifact(
            official_url=str(response.url),
            fetched_at=fetched_at,
            mime_type=content_type,
            filename=filename,
            content=response.content,
            http_status=response.status_code,
            http_headers=MojAuctionAdapter._artifact_headers(response),
            checksum_sha256=hashlib.sha256(response.content).hexdigest(),
        )

    async def fetch(self, item: DiscoveredItem) -> list[RawArtifact]:
        fetched_at = datetime.now(UTC)
        try:
            primary = await self._request(str(item.official_url))
        except MojExternalDetailBlocked as exc:
            summary = self._central_summary_artifacts.get(item.source_record_id)
            if not summary:
                # Changed list markup must fail explicitly rather than create a
                # record whose official evidence cannot be reproduced.
                raise
            item.metadata[self.PARTIAL_FAILURE_KEY] = (
                "Central MOJ list summary retained; external agency detail was not contacted because its host "
                f"has no reviewed automated-access policy: {exc.target_url}"
            )
            return [summary]
        artifacts = [self._artifact(primary, fetched_at)]
        if artifacts[0].mime_type != "text/html":
            return artifacts
        soup = BeautifulSoup(primary.content, "html.parser")
        urls: list[str] = []
        for link in soup.select("div.file_download a[href], section.cp img[src], .cp_slider img[src]"):
            relative = link.get("href") or link.get("src")
            if not relative:
                continue
            url = urljoin(str(primary.url), relative)
            if url not in urls and urlparse(url).hostname in self.ALLOWED_HOSTS:
                urls.append(url)
        for url in urls[: self.MAX_ATTACHMENTS]:
            artifacts.append(self._artifact(await self._request(url), fetched_at))
        return artifacts

    async def parse(self, item: DiscoveredItem, artifacts: list[RawArtifact]) -> ParsedAuctionRecord:
        return parse_moj_auction_detail(item, artifacts)

    async def healthcheck(self) -> SourceHealth:
        start = time.monotonic()
        try:
            response = await self._request(f"{self.LIST_URL}?Page=1&PageSize=30&type=01")
            ok = "查扣物查詢" in response.text and "汽、機車類" in response.text
            return SourceHealth(
                source="moj_auction",
                status="ACTIVE" if ok else "DEGRADED",
                checked_at=datetime.now(UTC),
                response_ms=round((time.monotonic() - start) * 1000),
                message="MOJ centralized seized-property list is readable" if ok else "Expected MOJ list markers were absent",
            )
        except Exception as exc:
            return SourceHealth(source="moj_auction", status="DEGRADED", checked_at=datetime.now(UTC), message=str(exc))
