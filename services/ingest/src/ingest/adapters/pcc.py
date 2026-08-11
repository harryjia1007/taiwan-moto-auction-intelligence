from __future__ import annotations

import asyncio
import hashlib
import re
import time
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ingest.adapters.base import SourceAdapter
from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SourceHealth
from ingest.parser import parse_pcc_detail


class PccAssetSaleAdapter(SourceAdapter):
    """Read nationwide public asset-sale notices from Government e-Procurement."""

    BASE_URL = "https://web.pcc.gov.tw"
    SEARCH_URL = f"{BASE_URL}/opas/aspam/public/readAspam"
    INDEX_URL = f"{BASE_URL}/opas/aspam/public/indexAspam"
    ALLOWED_HOSTS = {"web.pcc.gov.tw"}
    KEYWORDS = ("機車", "汽機車", "電動機車", "重型機車")
    MAX_BYTES = 25 * 1024 * 1024
    MAX_PAGES_PER_KEYWORD = 20
    DETAIL_ROUTES = {
        "formViewNew": "/opas/aspam/public/readOneAspamDetailOld",
        "formViewOld": "/opas/aspam/public/readOneAspamDetailNew",
        "formViewNormal": "/opas/aspam/public/readOneAspamDetail",
    }

    def __init__(self, client: httpx.AsyncClient | None = None, request_interval: float = 1.0) -> None:
        self.client = client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(20),
            headers={"User-Agent": "TaiwanMotoAuctionIntelligence/0.2 (+personal read-only research)"},
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

    async def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        self._validate_url(url)
        last_error: Exception | None = None
        for attempt in range(3):
            async with self._request_lock:
                delay = self.request_interval - (time.monotonic() - self._last_request)
                if delay > 0:
                    await asyncio.sleep(delay)
                try:
                    response = await self.client.request(method, url, **kwargs)
                    self._last_request = time.monotonic()
                    response.raise_for_status()
                    if len(response.content) > self.MAX_BYTES:
                        raise ValueError(f"Artifact exceeds {self.MAX_BYTES} bytes")
                    return response
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
            if attempt < 2:
                await asyncio.sleep(2**attempt)
        assert last_error is not None
        raise last_error

    @classmethod
    def _detail_items(cls, html: bytes, discovery_url: str) -> list[DiscoveredItem]:
        soup = BeautifulSoup(html, "html.parser")
        found: dict[str, DiscoveredItem] = {}
        for row in soup.select("tr"):
            cells = [re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip() for cell in row.select("td")]
            option = row.select_one("select option[value*='formView']")
            if len(cells) < 6 or not option:
                continue
            match = re.search(r"(formView(?:New|Old|Normal))\((\d+),", option.get("value", ""))
            if not match:
                continue
            function_name, primary_key = match.groups()
            title = cells[4]
            normalized_title = title.replace("⾞", "車")
            if not any(keyword in normalized_title for keyword in cls.KEYWORDS):
                continue
            if "電力機車" in normalized_title and "汽機車" not in normalized_title:
                continue
            route = cls.DETAIL_ROUTES[function_name]
            found[primary_key] = DiscoveredItem(
                source_record_id=primary_key,
                official_url=f"{cls.BASE_URL}{route}?pk={primary_key}",
                title=title,
                discovery_url=discovery_url,
            )
        return list(found.values())

    @staticmethod
    def _page_urls(html: bytes, current_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        urls: set[str] = set()
        for link in soup.select("a[href*='/opas/aspam/public/readAspam']"):
            url = urljoin(current_url, link.get("href", ""))
            query = parse_qs(urlparse(url).query)
            if any(key.endswith("-p") for key in query):
                urls.add(url)
        return sorted(urls)

    async def discover(self) -> list[DiscoveredItem]:
        discovered: dict[str, DiscoveredItem] = {}
        for keyword in self.KEYWORDS:
            first = await self._request(
                "GET", self.SEARCH_URL,
                params={"searchAssetsName": keyword, "pageModel.rowsPerPage": "100"},
            )
            pages = [str(first.url), *self._page_urls(first.content, str(first.url))]
            seen_pages: set[str] = set()
            for page_url in pages[: self.MAX_PAGES_PER_KEYWORD]:
                if page_url in seen_pages:
                    continue
                seen_pages.add(page_url)
                response = first if page_url == str(first.url) else await self._request("GET", page_url)
                for item in self._detail_items(response.content, str(response.url)):
                    discovered[item.source_record_id] = item
        return list(discovered.values())

    @staticmethod
    def _artifact(response: httpx.Response) -> RawArtifact:
        mime_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0].lower()
        if mime_type != "text/html":
            raise ValueError(f"Unexpected MIME type: {mime_type}")
        return RawArtifact(
            official_url=str(response.url), fetched_at=datetime.now(UTC), mime_type=mime_type,
            filename=PurePosixPath(urlparse(str(response.url)).path).name or None,
            content=response.content, http_status=response.status_code,
            http_headers={key: value for key, value in response.headers.items() if key.lower() in {"etag", "last-modified", "content-type", "content-length"}},
            checksum_sha256=hashlib.sha256(response.content).hexdigest(),
        )

    async def fetch(self, item: DiscoveredItem) -> list[RawArtifact]:
        return [self._artifact(await self._request("GET", str(item.official_url)))]

    async def parse(self, item: DiscoveredItem, artifacts: list[RawArtifact]) -> ParsedAuctionRecord:
        html = next((artifact for artifact in artifacts if artifact.mime_type == "text/html"), None)
        if not html:
            raise ValueError("No HTML artifact was fetched")
        return parse_pcc_detail(item, html)

    async def healthcheck(self) -> SourceHealth:
        started = time.monotonic()
        try:
            response = await self._request("GET", self.INDEX_URL)
            healthy = "財物變賣查詢" in response.text and "searchAssetsName" in response.text
            return SourceHealth(
                source="pcc", status="ACTIVE" if healthy else "DEGRADED",
                checked_at=datetime.now(UTC), response_ms=round((time.monotonic() - started) * 1000),
                message="Public nationwide asset-sale search is readable" if healthy else "Public search structure changed",
                warnings=[] if healthy else ["Expected PCC asset-sale form was not found"],
            )
        except Exception as exc:
            return SourceHealth(
                source="pcc", status="DEGRADED", checked_at=datetime.now(UTC),
                response_ms=round((time.monotonic() - started) * 1000),
                message="Public PCC asset-sale search is unavailable", warnings=[str(exc)],
            )
