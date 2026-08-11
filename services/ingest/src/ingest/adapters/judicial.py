from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from datetime import UTC, datetime
from urllib.parse import urlencode, urlparse

import httpx
from bs4 import BeautifulSoup

from ingest.adapters.base import SourceAdapter
from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SourceHealth
from ingest.parser import parse_judicial_record


class JudicialMovableAdapter(SourceAdapter):
    """Read all 22 district courts through the Judicial Yuan central search."""

    ORIGIN = "https://aomp109.judicial.gov.tw"
    BASE_URL = f"{ORIGIN}/judbp/wkw/WHD1A02"
    INDEX_URL = f"{BASE_URL}.htm"
    SEARCH_FORM_URL = f"{BASE_URL}/V1.htm"
    RESULT_FORM_URL = f"{BASE_URL}/V2.htm"
    QUERY_URL = f"{BASE_URL}/QUERY.htm"
    PDF_URL = f"{BASE_URL}/DO_VIEWPDF.htm"
    ALLOWED_HOSTS = {"aomp109.judicial.gov.tw"}
    KEYWORDS = ("機車", "機器腳踏車", "電動機車")
    MAX_BYTES = 25 * 1024 * 1024
    PAGE_SIZE = 100
    MAX_PAGES_PER_KEYWORD = 10

    def __init__(self, client: httpx.AsyncClient | None = None, request_interval: float = 1.0) -> None:
        self.client = client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(25),
            headers={"User-Agent": "TaiwanMotoAuctionIntelligence/0.3 (+personal read-only research)"},
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

    async def _form_fields(self) -> dict[str, str]:
        await self._request("GET", self.SEARCH_FORM_URL)
        response = await self._request("GET", self.RESULT_FORM_URL)
        if "text/html" not in response.headers.get("content-type", ""):
            raise ValueError("Judicial result form returned an unexpected MIME type")
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.select_one("form#infoForm")
        if not form:
            raise ValueError("Judicial result form no longer contains infoForm")
        return {
            node.get("name"): node.get("value", "")
            for node in form.select("input[name]")
            if node.get("name")
        }

    async def _query(self, base_fields: dict[str, str], keyword: str, page: int) -> dict[str, object]:
        fields = {
            **base_fields,
            "crtnm": "全部",
            "proptype": "C54",
            "saletype": "1",
            "keyword": "",
            "ttitle": keyword,
            "sorted_column": "A.CRMYY, A.CRMID, A.CRMNO, A.SALENO, A.ROWID",
            "sorted_type": "ASC",
            "pageNum": str(page),
            "pageSize": str(self.PAGE_SIZE),
        }
        response = await self._request(
            "POST",
            self.QUERY_URL,
            data=fields,
            headers={"Referer": self.RESULT_FORM_URL, "Origin": self.ORIGIN},
        )
        if "json" not in response.headers.get("content-type", ""):
            raise ValueError("Judicial query returned an unexpected MIME type")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Judicial query returned an unexpected structure")
        return payload

    @staticmethod
    def _rows(payload: dict[str, object]) -> list[dict[str, object]]:
        rows = payload.get("data") or payload.get("rows") or payload.get("result") or []
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    @staticmethod
    def _total(payload: dict[str, object], fallback: int) -> int:
        for key in ("total", "recordsTotal", "totalCount", "count"):
            value = payload.get(key)
            try:
                return int(str(value))
            except (TypeError, ValueError):
                continue
        return fallback

    async def discover(self) -> list[DiscoveredItem]:
        base_fields = await self._form_fields()
        found: dict[str, DiscoveredItem] = {}
        for keyword in self.KEYWORDS:
            first = await self._query(base_fields, keyword, 1)
            first_rows = self._rows(first)
            total = self._total(first, len(first_rows))
            pages = min(self.MAX_PAGES_PER_KEYWORD, max(1, math.ceil(total / self.PAGE_SIZE)))
            payloads = [first]
            for page in range(2, pages + 1):
                payloads.append(await self._query(base_fields, keyword, page))
            for payload in payloads:
                for row in self._rows(payload):
                    title = str(row.get("ttitle") or "").strip()
                    if not title or "電力機車" in title:
                        continue
                    row_id = str(row.get("rowid") or "").strip()
                    filename = str(row.get("filenm") or "").strip()
                    if not row_id or not filename:
                        continue
                    pdf_url = f"{self.PDF_URL}?{urlencode({'filenm': filename})}"
                    found[row_id] = DiscoveredItem(
                        source_record_id=row_id,
                        official_url=pdf_url,
                        title=title,
                        discovery_url=self.INDEX_URL,
                        metadata=row,
                    )
        return sorted(found.values(), key=lambda item: item.source_record_id)

    async def fetch(self, item: DiscoveredItem) -> list[RawArtifact]:
        if not item.metadata:
            raise ValueError("Judicial discovery metadata is required for live fetching")
        fetched_at = datetime.now(UTC)
        record_content = json.dumps(item.metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        record_artifact = RawArtifact(
            official_url=item.official_url,
            fetched_at=fetched_at,
            mime_type="application/json",
            filename=f"judicial-{item.source_record_id}.json",
            content=record_content,
            http_headers={"x-artifact-provenance": "official-query-result-row"},
            checksum_sha256=hashlib.sha256(record_content).hexdigest(),
        )
        response = await self._request("GET", str(item.official_url), headers={"Referer": self.RESULT_FORM_URL})
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/pdf" or not response.content.startswith(b"%PDF"):
            raise ValueError("Judicial announcement returned an invalid PDF")
        pdf_artifact = RawArtifact(
            official_url=item.official_url,
            fetched_at=fetched_at,
            mime_type="application/pdf",
            filename=f"judicial-{item.source_record_id}.pdf",
            content=response.content,
            http_status=response.status_code,
            http_headers=dict(response.headers),
            checksum_sha256=hashlib.sha256(response.content).hexdigest(),
        )
        return [record_artifact, pdf_artifact]

    async def parse(self, item: DiscoveredItem, artifacts: list[RawArtifact]) -> ParsedAuctionRecord:
        structured = next((artifact for artifact in artifacts if artifact.mime_type == "application/json"), None)
        if not structured:
            raise ValueError("Judicial structured result artifact is missing")
        return parse_judicial_record(item, structured)

    async def healthcheck(self) -> SourceHealth:
        started = time.monotonic()
        try:
            fields = await self._form_fields()
            healthy = bool(fields.get("_csrf") or fields.get("token"))
            return SourceHealth(
                source="judicial",
                status="ACTIVE" if healthy else "DEGRADED",
                checked_at=datetime.now(UTC),
                response_ms=round((time.monotonic() - started) * 1000),
                message="Judicial Yuan nationwide movable-property search is readable" if healthy else "Judicial search token was not found",
                warnings=[] if healthy else ["Expected Judicial Yuan query form token was not found"],
            )
        except Exception as exc:
            return SourceHealth(
                source="judicial",
                status="DEGRADED",
                checked_at=datetime.now(UTC),
                response_ms=round((time.monotonic() - started) * 1000),
                message="Judicial Yuan movable-property search is unavailable",
                warnings=[str(exc)],
            )
