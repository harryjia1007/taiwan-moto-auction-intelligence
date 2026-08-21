from __future__ import annotations

import asyncio
import hashlib
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ingest.adapters.base import SourceAdapter, contact_user_agent, enforce_http_status
from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SourceHealth
from ingest.parser import parse_pcc_detail


class PccAssetSaleAdapter(SourceAdapter):
    """Read nationwide public asset-sale notices from PCC's official open-data feed."""

    BASE_URL = "https://web.pcc.gov.tw"
    OPEN_DATA_URL = f"{BASE_URL}/opas/aspam/public/downloadOpenData"
    SEARCH_URL = f"{BASE_URL}/opas/aspam/public/readAspam"
    DATASET_URL = "https://data.gov.tw/dataset/7263"
    ALLOWED_HOSTS = {"web.pcc.gov.tw"}
    VEHICLE_TERMS = ("汽車", "機車", "車輛")
    RAILWAY_LOCOMOTIVE_TERMS = ("鐵路機車", "電力機車", "柴油機車", "蒸汽機車")
    MAX_BYTES = 25 * 1024 * 1024
    DETAIL_ROUTES = {
        "formViewNew": "/opas/aspam/public/readOneAspamDetailOld",
        "formViewOld": "/opas/aspam/public/readOneAspamDetailNew",
        "formViewNormal": "/opas/aspam/public/readOneAspamDetail",
    }
    FEED_MIME_TYPES = {"application/octet-stream", "application/xml", "text/xml"}

    def __init__(self, client: httpx.AsyncClient | None = None, request_interval: float = 1.0) -> None:
        self.client = client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(20),
            headers={"User-Agent": contact_user_agent("0.5")},
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
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError(f"Blocked malformed source URL: {url}") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self.ALLOWED_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
        ):
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
                    current_url = url
                    request_kwargs = dict(kwargs)
                    request_kwargs.pop("follow_redirects", None)
                    for _ in range(5):
                        response = await self.client.request(
                            method,
                            current_url,
                            follow_redirects=False,
                            **request_kwargs,
                        )
                        self._last_request = time.monotonic()
                        if not response.is_redirect:
                            break
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("PCC redirect response did not include a location")
                        current_url = urljoin(str(response.url), location)
                        self._validate_url(current_url)
                        request_kwargs.pop("params", None)
                    else:
                        raise ValueError("PCC redirect limit exceeded")
                    enforce_http_status(response)
                    self._validate_url(str(response.url))
                    if len(response.content) > self.MAX_BYTES:
                        raise ValueError(f"Artifact exceeds {self.MAX_BYTES} bytes")
                    return response
                except ValueError:
                    raise
                except httpx.HTTPError as exc:
                    last_error = exc
            if attempt < 2:
                await asyncio.sleep(2**attempt)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _clean(value: str | None) -> str:
        return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "").replace("⾞", "車")).strip()

    @classmethod
    def _is_vehicle_title(cls, title: str) -> bool:
        normalized = cls._clean(title)
        if any(term in normalized for term in cls.RAILWAY_LOCOMOTIVE_TERMS):
            return False
        return any(term in normalized for term in cls.VEHICLE_TERMS)

    @staticmethod
    def _normalized_date(value: str | None) -> str:
        raw = re.sub(r"\D", "", value or "")
        if len(raw) == 8:
            return raw
        match = re.fullmatch(r"(\d{2,3})/(\d{1,2})/(\d{1,2})", (value or "").strip())
        if not match:
            return raw
        year, month, day = map(int, match.groups())
        return f"{year + 1911:04d}{month:02d}{day:02d}"

    @classmethod
    def _source_record_id(cls, organization: str, case_number: str, announcement_count: str) -> str:
        identity = "\0".join(cls._clean(value) for value in (organization, case_number, announcement_count))
        return f"open-data-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"

    @classmethod
    def _open_data_items(cls, xml: bytes, discovery_url: str) -> list[DiscoveredItem]:
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise ValueError("PCC open-data XML is malformed") from exc
        if cls._clean(root.tag) != "財物變賣公告名單":
            raise ValueError(f"Unexpected PCC open-data root: {root.tag}")

        feed_updated_at = cls._clean(root.attrib.get("更新時間"))
        found: dict[str, DiscoveredItem] = {}
        for row in root.findall("財物變賣公告"):
            fields = {cls._clean(child.tag): cls._clean(child.text) for child in row}
            organization = fields.get("機關名稱", "")
            case_number = fields.get("標案案號", "")
            announcement_count = fields.get("公告次數", "")
            title = fields.get("財物名稱", "")
            announcement_date = fields.get("公告日期", "")
            if not all((organization, case_number, announcement_count, title, announcement_date)):
                continue
            if not cls._is_vehicle_title(title):
                continue
            source_record_id = cls._source_record_id(organization, case_number, announcement_count)
            found[source_record_id] = DiscoveredItem(
                source_record_id=source_record_id,
                # The feed proves discovery. fetch() replaces this with the exact
                # official detail URL after matching all five published fields.
                official_url=discovery_url,
                title=title,
                discovery_url=discovery_url,
                metadata={
                    "organization": organization,
                    "case_number": case_number,
                    "announcement_count": announcement_count,
                    "announcement_date": announcement_date,
                    "feed_updated_at": feed_updated_at,
                },
            )
        return list(found.values())

    @classmethod
    def _detail_items(cls, html: bytes, discovery_url: str) -> list[DiscoveredItem]:
        soup = BeautifulSoup(html, "html.parser")
        found: dict[str, DiscoveredItem] = {}
        for row in soup.select("tr"):
            cells = [cls._clean(cell.get_text(" ", strip=True)) for cell in row.select("td")]
            option = row.select_one("select option[value*='formView']")
            if len(cells) < 6 or not option:
                continue
            match = re.search(r"(formView(?:New|Old|Normal))\((\d+),", option.get("value", ""))
            if not match:
                continue
            function_name, primary_key = match.groups()
            organization, case_number, announcement_count, title, announcement_date = cells[1:6]
            if not cls._is_vehicle_title(title):
                continue
            route = cls.DETAIL_ROUTES[function_name]
            found[primary_key] = DiscoveredItem(
                source_record_id=primary_key,
                official_url=f"{cls.BASE_URL}{route}?pk={primary_key}",
                title=title,
                discovery_url=discovery_url,
                metadata={
                    "organization": organization,
                    "case_number": case_number,
                    "announcement_count": announcement_count,
                    "announcement_date": announcement_date,
                },
            )
        return list(found.values())

    @classmethod
    def _matches_open_data_item(cls, candidate: DiscoveredItem, item: DiscoveredItem) -> bool:
        for key in ("organization", "case_number", "announcement_count"):
            if cls._clean(str(candidate.metadata.get(key) or "")) != cls._clean(str(item.metadata.get(key) or "")):
                return False
        return (
            cls._clean(candidate.title) == cls._clean(item.title)
            and cls._normalized_date(str(candidate.metadata.get("announcement_date") or ""))
            == cls._normalized_date(str(item.metadata.get("announcement_date") or ""))
        )

    @classmethod
    def _validate_open_data_response(cls, response: httpx.Response) -> None:
        mime_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if mime_type not in cls.FEED_MIME_TYPES:
            raise ValueError(f"Unexpected PCC open-data MIME type: {mime_type or 'missing'}")
        if not response.content.lstrip().startswith(b"<?xml"):
            raise ValueError("PCC open-data response is not XML")

    async def discover(self) -> list[DiscoveredItem]:
        response = await self._request("GET", self.OPEN_DATA_URL)
        self._validate_open_data_response(response)
        return self._open_data_items(response.content, str(response.url))

    async def _resolve_detail(self, item: DiscoveredItem) -> DiscoveredItem:
        response = await self._request(
            "GET",
            self.SEARCH_URL,
            params={
                "searchTenderCaseNo": str(item.metadata.get("case_number") or ""),
                "searchOrgName": str(item.metadata.get("organization") or ""),
                "pageModel.rowsPerPage": "100",
            },
        )
        matches = [
            candidate
            for candidate in self._detail_items(response.content, str(response.url))
            if self._matches_open_data_item(candidate, item)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one PCC detail match for {item.source_record_id}; found {len(matches)}"
            )
        return matches[0]

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
        detail = await self._resolve_detail(item)
        item.official_url = detail.official_url
        item.metadata["pcc_detail_record_id"] = detail.source_record_id
        return [self._artifact(await self._request("GET", str(detail.official_url)))]

    async def parse(self, item: DiscoveredItem, artifacts: list[RawArtifact]) -> ParsedAuctionRecord:
        html = next((artifact for artifact in artifacts if artifact.mime_type == "text/html"), None)
        if not html:
            raise ValueError("No HTML artifact was fetched")
        return parse_pcc_detail(item, html)

    async def healthcheck(self) -> SourceHealth:
        started = time.monotonic()
        try:
            response = await self._request("GET", self.OPEN_DATA_URL)
            self._validate_open_data_response(response)
            root = ET.fromstring(response.content)
            published = len(root.findall("財物變賣公告"))
            vehicles = len(self._open_data_items(response.content, str(response.url)))
            healthy = published > 0
            return SourceHealth(
                source="pcc", status="ACTIVE" if healthy else "DEGRADED",
                checked_at=datetime.now(UTC), response_ms=round((time.monotonic() - started) * 1000),
                message=f"Official PCC open-data feed contains {published} notices; {vehicles} match vehicle terms",
                warnings=[] if healthy else ["Official feed unexpectedly contains zero notices"],
            )
        except Exception as exc:
            return SourceHealth(
                source="pcc", status="DEGRADED", checked_at=datetime.now(UTC),
                response_ms=round((time.monotonic() - started) * 1000),
                message="Official PCC open-data feed is unavailable", warnings=[str(exc)],
            )
