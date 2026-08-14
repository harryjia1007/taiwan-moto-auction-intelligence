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

from ingest.adapters.base import SourceAdapter, contact_user_agent, enforce_http_status
from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SourceHealth
from ingest.parser import parse_moj_auction_detail


class MojAuctionAdapter(SourceAdapter):
    """Public read-only adapter for the MOJ centralized seized-property portal."""

    ORIGIN = "https://auction.moj.gov.tw"
    LIST_URL = f"{ORIGIN}/1724/1726/searchList"
    ALLOWED_HOSTS = {"auction.moj.gov.tw"}
    MAX_BYTES = 25 * 1024 * 1024
    MAX_PAGES = 10
    PAGE_SIZE = 100
    MAX_ATTACHMENTS = 25
    MOTORCYCLE_TERMS = ("機車", "機器腳踏車", "重機")

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

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in self.ALLOWED_HOSTS:
            raise ValueError(f"Blocked non-registered source URL: {url}")

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
                        self._validate_url(current_url)
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
    def _items(cls, content: bytes) -> list[DiscoveredItem]:
        soup = BeautifulSoup(content, "html.parser")
        found: dict[str, DiscoveredItem] = {}
        for row in soup.select("table.table_list tbody tr"):
            link = row.select_one("td[data-title='標題'] a[href]")
            if not link:
                continue
            title = " ".join(link.stripped_strings).strip()
            if not any(term in title for term in cls.MOTORCYCLE_TERMS) or "電力機車" in title:
                continue
            href = urljoin(cls.ORIGIN, link.get("href", ""))
            parsed = urlparse(href)
            if parsed.hostname not in cls.ALLOWED_HOSTS:
                continue
            post_match = re.search(r"/1724/1726/(\d+)(?:/post)?", parsed.path)
            node_id = parse_qs(parsed.query).get("nodeId", [""])[0]
            media_match = re.search(r"/media/([^/]+)/(.+)", parsed.path)
            record_id = post_match.group(1) if post_match else f"node-{node_id}" if node_id else f"media-{media_match.group(1)}-{PurePosixPath(parsed.path).name}" if media_match else ""
            if not record_id:
                continue
            cells = {cell.get("data-title"): " ".join(cell.stripped_strings).strip() for cell in row.select("td[data-title]")}
            found[record_id] = DiscoveredItem(
                source_record_id=record_id,
                official_url=href,
                title=title,
                discovery_url=cls.LIST_URL,
                metadata={"organization": cells.get("單位", ""), "published_date": cells.get("張貼日", "")},
            )
        return list(found.values())

    async def discover(self) -> list[DiscoveredItem]:
        found: dict[str, DiscoveredItem] = {}
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.LIST_URL}?{urlencode({'Page': page, 'PageSize': self.PAGE_SIZE, 'type': '01'})}"
            response = await self._request(url)
            if "text/html" not in response.headers.get("content-type", ""):
                raise ValueError("MOJ auction list returned an unexpected MIME type")
            items = self._items(response.content)
            for item in items:
                found[item.source_record_id] = item
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
            http_headers=dict(response.headers),
            checksum_sha256=hashlib.sha256(response.content).hexdigest(),
        )

    async def fetch(self, item: DiscoveredItem) -> list[RawArtifact]:
        fetched_at = datetime.now(UTC)
        primary = await self._request(str(item.official_url))
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
