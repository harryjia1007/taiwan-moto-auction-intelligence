from __future__ import annotations

import asyncio
import hashlib
import re
import time
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ingest.adapters.base import SourceAdapter, contact_user_agent, enforce_http_status
from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SourceHealth
from ingest.parser import parse_shwoo_detail


class ShwooAdapter(SourceAdapter):
    BASE_URL = "https://shwoo.gov.taipei"
    BROWSE_URL = f"{BASE_URL}/shwoo/browse/browse00/"
    RESULTS_URL = f"{BASE_URL}/shwoo/newproduct/newproduct00/bidresult"
    ALLOWED_HOSTS = {"shwoo.gov.taipei"}
    KEYWORDS = (
        "機車", "機器腳踏車", "普通輕型機車", "普通重型機車",
        "大型重型機車", "重型機車", "重機", "電動機車", "汽機車",
    )
    MAX_BYTES = 25 * 1024 * 1024
    ALLOWED_MIME = ("text/html", "image/jpeg", "image/png", "image/webp")

    def __init__(self, client: httpx.AsyncClient | None = None, request_interval: float = 1.0) -> None:
        self.client = client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(20),
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
                    enforce_http_status(response)
                    if len(response.content) > self.MAX_BYTES:
                        raise ValueError(f"Artifact exceeds {self.MAX_BYTES} bytes")
                    return response
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _detail_items(html: bytes, discovery_url: str, recycler_only: bool, result_record: bool = False) -> list[DiscoveredItem]:
        soup = BeautifulSoup(html, "html.parser")
        found: dict[str, DiscoveredItem] = {}
        for link in soup.select("a[href]"):
            href = link.get("href", "")
            match = re.search(r"AUID=(\d+)", href)
            if not match:
                continue
            auid = match.group(1)
            title = " ".join(link.stripped_strings).strip()
            if result_record:
                row = link.find_parent("tr")
                cells = row.select("td") if row else []
                if len(cells) > 5:
                    title = " ".join(cells[5].stripped_strings).strip()
            if not title:
                image = link.find("img")
                title = image.get("alt", "") if image else ""
            if not title:
                continue
            found[auid] = DiscoveredItem(
                source_record_id=auid,
                official_url=f"{ShwooAdapter.BASE_URL}/shwoo/newproduct/newproduct00/product?AUID={auid}",
                title=title,
                discovery_url=discovery_url,
                recycler_only=recycler_only,
                result_record=result_record,
            )
        return list(found.values())

    async def discover(self) -> list[DiscoveredItem]:
        landing = await self._request("GET", self.BROWSE_URL)
        soup = BeautifulSoup(landing.content, "html.parser")
        form = soup.select_one("form#autionId") or soup.find("form")
        if not form or not form.get("action"):
            raise RuntimeError("The public Shwoo discovery form is unavailable")
        action = urljoin(str(landing.url), form["action"])
        discovered: dict[str, DiscoveredItem] = {}
        for recycler_only in (False, True):
            for keyword in self.KEYWORDS:
                response = await self._request("POST", action, data={
                    "showPage": "1", "showType": "", "q_keyword": keyword,
                    "q_autioncode": "", "q_county_query": "", "q_order": "BidEndDate_desc",
                    "q_unit1value4C": "", "isRecyclerRadio": "Y" if recycler_only else "N",
                    "onlyTodayChecked": "",
                })
                for item in self._detail_items(response.content, str(response.url), recycler_only):
                    discovered[item.source_record_id] = item

        # Completed outcomes are server rendered after a public form POST. Querying the
        # keyword variants avoids treating unrelated rows on the default result page as motorcycles.
        try:
            await self._request("GET", self.RESULTS_URL)
            for keyword in self.KEYWORDS:
                result_page = await self._request("POST", self.RESULTS_URL, data={
                    "q_keyword": keyword,
                    "q_autioncode": "",
                    "q_bidenddate": "",
                    "q_paystatus": "",
                    "q_county_query": "",
                    "showPage": "1",
                })
                for item in self._detail_items(result_page.content, str(result_page.url), False, True):
                    if any(candidate in item.title for candidate in self.KEYWORDS):
                        discovered.setdefault(item.source_record_id, item)
        except httpx.HTTPError:
            pass
        return list(discovered.values())

    @staticmethod
    def _artifact(response: httpx.Response, official_url: str | None = None) -> RawArtifact:
        mime_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0].lower()
        if not mime_type.startswith(ShwooAdapter.ALLOWED_MIME):
            raise ValueError(f"Unexpected MIME type: {mime_type}")
        filename = PurePosixPath(urlparse(str(response.url)).path).name or None
        return RawArtifact(
            # Preserve the URL found in the official HTML. Image endpoints may redirect;
            # repository matching must still connect the parsed photo to its cached bytes.
            official_url=official_url or str(response.url), fetched_at=datetime.now(UTC), mime_type=mime_type,
            filename=filename, content=response.content, http_status=response.status_code,
            http_headers={key: value for key, value in response.headers.items() if key.lower() in {"etag", "last-modified", "content-type", "content-length"}},
            checksum_sha256=hashlib.sha256(response.content).hexdigest(),
        )

    async def fetch(self, item: DiscoveredItem) -> list[RawArtifact]:
        detail = await self._request("GET", str(item.official_url))
        artifacts = [self._artifact(detail, str(item.official_url))]
        soup = BeautifulSoup(detail.content, "html.parser")
        image_urls: list[str] = []
        for node in soup.select("a[href*='imageResize'], img[src*='/image?']"):
            relative = node.get("href") or node.get("src")
            if relative:
                url = urljoin(str(detail.url), relative)
                if url not in image_urls:
                    image_urls.append(url)
        for url in image_urls[:12]:
            try:
                artifacts.append(self._artifact(await self._request("GET", url), url))
            except (httpx.HTTPError, ValueError):
                continue
        return artifacts

    async def parse(self, item: DiscoveredItem, artifacts: list[RawArtifact]) -> ParsedAuctionRecord:
        html = next((artifact for artifact in artifacts if artifact.mime_type == "text/html"), None)
        if not html:
            raise ValueError("No HTML artifact was fetched")
        return parse_shwoo_detail(item, html)

    async def healthcheck(self) -> SourceHealth:
        start = time.monotonic()
        try:
            response = await self._request("GET", self.BROWSE_URL)
            text = response.text
            healthy = "物品瀏覽" in text and "autionId" in text
            return SourceHealth(
                source="shwoo", status="ACTIVE" if healthy else "DEGRADED",
                checked_at=datetime.now(UTC), response_ms=round((time.monotonic() - start) * 1000),
                message="Public discovery form is readable" if healthy else "Public page structure changed",
                warnings=[] if healthy else ["Expected discovery form was not found"],
            )
        except Exception as exc:
            return SourceHealth(
                source="shwoo", status="DEGRADED", checked_at=datetime.now(UTC),
                response_ms=round((time.monotonic() - start) * 1000),
                message="Public discovery page is unavailable", warnings=[str(exc)],
            )
