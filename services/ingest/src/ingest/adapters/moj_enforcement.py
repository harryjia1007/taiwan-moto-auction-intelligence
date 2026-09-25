from __future__ import annotations

import asyncio
import hashlib
import re
import time
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.robotparser import RobotFileParser
from uuid import UUID

import httpx
from bs4 import BeautifulSoup

from ingest.adapters.base import (
    SourceAccessDenied,
    SourceAdapter,
    SourceRateLimited,
    contact_user_agent,
    enforce_http_status,
)
from ingest.models import DiscoveredItem, EvidenceRef, ParsedAuctionRecord, RawArtifact, SourceHealth
from ingest.parser import parse_moj_enforcement_detail


class MojEnforcementExportedIndexParser:
    """Convert a human-saved official result page into validated detail items.

    This parser has no HTTP client and cannot issue a request. The central search
    form requires CAPTCHA, so production discovery remains human-assisted. Only
    same-host HTTPS detail UUIDs and safe official PDF links contained in the
    saved HTML are retained.
    """

    ORIGIN = "https://www.tpkonsale.moj.gov.tw"
    HOST = "www.tpkonsale.moj.gov.tw"
    SEARCH_URL = f"{ORIGIN}/Chattel"
    DETAIL_PATH = "/Detail/Chattel"
    DOWNLOAD_PATH = "/File/Download"
    MAX_EXPORT_BYTES = 8 * 1024 * 1024
    MAX_RECORDS = 250
    _UUID_PATTERN = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    _ROUND_VALUES = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }

    @classmethod
    def _uuid_value(cls, value: str) -> str:
        candidate = value.strip().lower()
        if not cls._UUID_PATTERN.fullmatch(candidate):
            raise ValueError("Administrative Enforcement NO must be an official UUID")
        return str(UUID(candidate))

    @classmethod
    def validate_url(cls, url: str, *, kind: str) -> str:
        parsed = urlparse(url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError(f"Blocked malformed Administrative Enforcement URL: {url}") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname != cls.HOST
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
            or parsed.fragment
        ):
            raise ValueError(f"Blocked non-official Administrative Enforcement URL: {url}")

        query = parse_qs(parsed.query, keep_blank_values=True)
        if kind == "detail":
            if parsed.path != cls.DETAIL_PATH or set(query) != {"NO"} or len(query["NO"]) != 1:
                raise ValueError("Administrative Enforcement detail URL must contain only NO")
            return cls._uuid_value(query["NO"][0])
        if kind == "attachment":
            if parsed.path != cls.DOWNLOAD_PATH:
                raise ValueError("Administrative Enforcement attachment path is not approved")
            if not {"PATH", "NAME"}.issubset(query) or not set(query).issubset({"PATH", "NAME", "DOWNLOAD"}):
                raise ValueError("Administrative Enforcement attachment URL has unapproved fields")
            if any(len(values) != 1 for values in query.values()):
                raise ValueError("Administrative Enforcement attachment URL has duplicate fields")
            attachment_record_id = cls._uuid_value(query["PATH"][0])
            filename = query["NAME"][0]
            if (
                not filename.lower().endswith(".pdf")
                or "/" in filename
                or "\\" in filename
                or (query.get("DOWNLOAD") and not query["DOWNLOAD"][0].lower().endswith(".pdf"))
            ):
                raise ValueError("Administrative Enforcement attachment must be an official PDF")
            return attachment_record_id
        raise ValueError(f"Unknown Administrative Enforcement URL kind: {kind}")

    @staticmethod
    def _cell_text(row: object, label_prefix: str) -> str:
        cell = row.find("td", attrs={"data-label": re.compile(rf"^{re.escape(label_prefix)}")})
        return " ".join(cell.stripped_strings).strip() if cell else ""

    @classmethod
    def _round_number(cls, value: str) -> int | None:
        digit = re.search(r"第\s*(\d+)\s*拍", value)
        if digit:
            return int(digit.group(1))
        chinese = re.search(r"第\s*([一二三四五六七八九十])\s*拍", value)
        return cls._ROUND_VALUES.get(chinese.group(1)) if chinese else None

    @staticmethod
    def _organization(value: str) -> str:
        match = re.search(r"[（(]\s*([^／/)]+)分署", value)
        branch = (match.group(1) if match else "").replace("台", "臺").strip()
        return f"法務部行政執行署{branch}分署" if branch else "法務部行政執行署（分署未確認）"

    @classmethod
    def parse(cls, content: bytes) -> tuple[list[DiscoveredItem], list[str]]:
        if len(content) > cls.MAX_EXPORT_BYTES:
            raise ValueError(f"Exported Administrative Enforcement HTML exceeds {cls.MAX_EXPORT_BYTES} bytes")
        soup = BeautifulSoup(content, "html.parser")
        if "各分署動產拍賣公告" not in soup.get_text(" ", strip=True):
            raise ValueError("Exported Administrative Enforcement index markers changed")

        index_artifact = RawArtifact(
            official_url=cls.SEARCH_URL,
            fetched_at=datetime.now(UTC),
            mime_type="text/html",
            filename="moj-enforcement-exported-index.html",
            content=content,
            checksum_sha256=hashlib.sha256(content).hexdigest(),
        )

        warnings: list[str] = []
        current_page_node = soup.select_one("input[name='PAGINATION_PAGE_NO']")
        current_page = (current_page_node.get("value", "").strip() if current_page_node else "")
        referenced_pages = sorted({
            int(match.group(1))
            for node in soup.select("a[onclick]")
            if (match := re.search(r"\breQuery\(\s*(\d+)\s*\)", node.get("onclick", "")))
            and int(match.group(1)) > 0
        })
        additional_pages = [page for page in referenced_pages if str(page) != current_page]
        if additional_pages:
            warnings.append(
                "Exported HTML references additional result pages "
                f"{additional_pages}; save and import every page to avoid incomplete coverage"
            )
        items: dict[str, DiscoveredItem] = {}
        for row in soup.select("tbody tr"):
            detail_node = row.select_one("a[href*='/Detail/Chattel?NO=']")
            if not detail_node or not detail_node.get("href"):
                continue
            try:
                official_url = urljoin(cls.ORIGIN, detail_node["href"])
                source_record_id = cls.validate_url(official_url, kind="detail")
            except ValueError as exc:
                warnings.append(f"Skipped unsafe Administrative Enforcement detail link: {exc}")
                continue

            category_text = cls._cell_text(row, "種類")
            if category_text != "汽機車":
                warnings.append(f"{source_record_id}: skipped row with unexpected official category {category_text!r}")
                continue
            case_branch = cls._cell_text(row, "案號")
            auction_text = cls._cell_text(row, "拍賣日時")
            explanation_cell = row.find("td", attrs={"data-label": re.compile(r"^說明")})
            explanation = " ".join(explanation_cell.stripped_strings).strip() if explanation_cell else ""
            case_match = re.search(r"\b\d{10,16}\b", case_branch)
            attachment_urls: list[str] = []
            if explanation_cell:
                for link in explanation_cell.select("a[href]"):
                    candidate = urljoin(cls.ORIGIN, link["href"])
                    try:
                        attachment_record_id = cls.validate_url(candidate, kind="attachment")
                        if attachment_record_id != source_record_id:
                            raise ValueError("Administrative Enforcement attachment PATH did not match its detail UUID")
                    except ValueError as exc:
                        warnings.append(f"{source_record_id}: skipped unsafe attachment link: {exc}")
                        continue
                    attachment_urls.append(candidate)
            title = explanation[:180] or f"汽機車拍賣案件 {case_match.group(0) if case_match else source_record_id}"
            item = DiscoveredItem(
                source_record_id=source_record_id,
                official_url=official_url,
                discovery_url=cls.SEARCH_URL,
                title=title,
                metadata={
                    "organization": cls._organization(case_branch),
                    "auction_round": cls._round_number(auction_text),
                    "official_case_number": case_match.group(0) if case_match else None,
                    "case_branch_text": case_branch,
                    "auction_at_text": auction_text,
                    "vehicle_category_bucket": category_text,
                    "index_explanation_text": explanation,
                    "index_provenance": "MANUAL_OFFICIAL_HTML_EXPORT",
                    "official_attachment_urls": list(dict.fromkeys(attachment_urls)),
                    "index_official_attachment_urls": list(dict.fromkeys(attachment_urls)),
                },
                discovery_artifacts=[index_artifact],
            )
            if source_record_id in items:
                warnings.append(f"{source_record_id}: duplicate detail UUID in exported HTML was ignored")
            else:
                items[source_record_id] = item
            if len(items) >= cls.MAX_RECORDS:
                warnings.append(f"Export parser reached the bounded {cls.MAX_RECORDS}-record limit")
                break
        if not items:
            warnings.append("Exported page contained zero validated in-progress vehicle detail links")
        return sorted(items.values(), key=lambda item: item.source_record_id), warnings


class MojEnforcementManualAdapter(SourceAdapter):
    """CAPTCHA-safe importer for human-reviewed official detail URLs.

    Discovery is entirely offline. Before any detail download, each run reads
    the official robots policy. Redirects, PDFs, and images are never followed.
    """

    ORIGIN = MojEnforcementExportedIndexParser.ORIGIN
    SEARCH_URL = MojEnforcementExportedIndexParser.SEARCH_URL
    ROBOTS_URL = f"{ORIGIN}/robots.txt"
    ALLOWED_HOSTS = {MojEnforcementExportedIndexParser.HOST}
    MAX_HTML_BYTES = 8 * 1024 * 1024
    MAX_ROBOTS_BYTES = 256 * 1024
    MAX_ATTACHMENTS = 25
    MAX_REQUEST_ATTEMPTS = 3
    SAFE_RESPONSE_HEADERS = frozenset({
        "cache-control",
        "content-disposition",
        "content-length",
        "content-type",
        "etag",
        "last-modified",
    })

    def __init__(
        self,
        manual_items: list[DiscoveredItem] | None = None,
        client: httpx.AsyncClient | None = None,
        request_interval: float = 1.0,
    ) -> None:
        if request_interval < 0:
            raise ValueError("Administrative Enforcement request interval cannot be negative")
        self.manual_items = manual_items or []
        self.user_agent = contact_user_agent("0.6")
        self.client = client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(25),
            headers={"User-Agent": self.user_agent},
        )
        self._owns_client = client is None
        self.request_interval = request_interval
        self._last_request = 0.0
        self._request_lock = asyncio.Lock()
        self._robots: RobotFileParser | None = None
        self._manifest_warnings = list(dict.fromkeys(
            str(warning).strip()
            for item in self.manual_items
            for warning in item.metadata.get("manifest_warnings", [])
            if str(warning).strip()
        ))
        self.discovery_warnings: list[str] = list(self._manifest_warnings)

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    @classmethod
    def _validate_url(cls, url: str, *, kind: str) -> None:
        if kind == "robots":
            parsed = urlparse(url)
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError(f"Blocked malformed source URL: {url}") from exc
            if (
                parsed.scheme != "https"
                or parsed.hostname not in cls.ALLOWED_HOSTS
                or parsed.path != "/robots.txt"
                or parsed.query
                or parsed.fragment
                or parsed.username is not None
                or parsed.password is not None
                or port not in {None, 443}
            ):
                raise ValueError(f"Blocked non-official Administrative Enforcement robots URL: {url}")
            return
        MojEnforcementExportedIndexParser.validate_url(url, kind=kind)

    def _require_robots_allowed(self, url: str) -> None:
        if self._robots is None:
            raise SourceAccessDenied("No verified Administrative Enforcement robots policy is loaded for this run")
        path = urlparse(url).path.lower()
        if path.endswith((".jpg", ".gif")) or not self._robots.can_fetch(self.user_agent, url):
            raise SourceAccessDenied(f"Administrative Enforcement robots.txt disallows {path}")

    @staticmethod
    def _mime(response: httpx.Response) -> str:
        return response.headers.get("content-type", "").split(";", 1)[0].strip().lower()

    @classmethod
    def _validate_response(cls, response: httpx.Response, *, kind: str) -> None:
        mime = cls._mime(response)
        if kind == "robots":
            allowed = {"text/plain"}
        elif kind == "detail":
            allowed = {"text/html", "application/xhtml+xml"}
        else:
            raise ValueError(f"Administrative Enforcement {kind} is link-only and must not be requested")
        if mime not in allowed:
            raise ValueError(f"Unsupported Administrative Enforcement {kind} MIME type: {mime or 'missing'}")

    async def _request(self, url: str, *, kind: str, referer: str | None = None) -> httpx.Response:
        self._validate_url(url, kind=kind)
        if kind != "robots":
            self._require_robots_allowed(url)
        if kind not in {"robots", "detail"}:
            raise SourceAccessDenied("Administrative Enforcement PDF attachments are link-only")
        maximum = self.MAX_ROBOTS_BYTES if kind == "robots" else self.MAX_HTML_BYTES
        last_error: Exception | None = None
        for attempt in range(self.MAX_REQUEST_ATTEMPTS):
            async with self._request_lock:
                delay = self.request_interval - (time.monotonic() - self._last_request)
                if delay > 0:
                    await asyncio.sleep(delay)
                try:
                    headers = {"Referer": referer} if referer else None
                    async with self.client.stream(
                        "GET",
                        url,
                        headers=headers,
                        follow_redirects=False,
                    ) as streamed:
                        self._last_request = time.monotonic()
                        if streamed.is_redirect:
                            raise SourceAccessDenied("Administrative Enforcement import never follows redirects")
                        enforce_http_status(streamed)
                        content_length = streamed.headers.get("content-length", "").strip()
                        if content_length.isdigit() and int(content_length) > maximum:
                            raise ValueError(f"Administrative Enforcement {kind} exceeds {maximum} bytes")
                        body = bytearray()
                        async for chunk in streamed.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > maximum:
                                raise ValueError(f"Administrative Enforcement {kind} exceeds {maximum} bytes")
                        response = httpx.Response(
                            streamed.status_code,
                            request=streamed.request,
                            headers=streamed.headers,
                            content=bytes(body),
                        )
                    self._validate_url(str(response.url), kind=kind)
                    self._validate_response(response, kind=kind)
                    return response
                except (SourceAccessDenied, SourceRateLimited, ValueError):
                    raise
                except httpx.HTTPError as exc:
                    last_error = exc
            if attempt < self.MAX_REQUEST_ATTEMPTS - 1:
                await asyncio.sleep(2**attempt)
        assert last_error is not None
        raise last_error

    async def _preflight(self) -> None:
        self._robots = None
        response = await self._request(self.ROBOTS_URL, kind="robots")
        if not re.search(r"^\s*User-agent\s*:", response.text, re.IGNORECASE | re.MULTILINE):
            raise SourceAccessDenied("Administrative Enforcement robots.txt lacks a User-agent directive")
        parser = RobotFileParser()
        parser.set_url(self.ROBOTS_URL)
        parser.parse(response.text.splitlines())
        self._robots = parser

    async def discover(self) -> list[DiscoveredItem]:
        self.discovery_warnings = list(self._manifest_warnings)
        await self._preflight()
        for item in self.manual_items:
            self._validate_url(str(item.official_url), kind="detail")
            self._require_robots_allowed(str(item.official_url))
        return sorted(self.manual_items, key=lambda item: item.source_record_id)

    @classmethod
    def _artifact(cls, response: httpx.Response, fetched_at: datetime) -> RawArtifact:
        content_type = cls._mime(response)
        filename = PurePosixPath(urlparse(str(response.url)).path).name or "moj-enforcement.html"
        headers = {
            key.lower(): value
            for key, value in response.headers.items()
            if key.lower() in cls.SAFE_RESPONSE_HEADERS
        }
        return RawArtifact(
            official_url=str(response.url),
            fetched_at=fetched_at,
            mime_type=content_type,
            filename=filename,
            content=response.content,
            http_status=response.status_code,
            http_headers=headers,
            checksum_sha256=hashlib.sha256(response.content).hexdigest(),
        )

    async def fetch(self, item: DiscoveredItem) -> list[RawArtifact]:
        self._validate_url(str(item.official_url), kind="detail")
        self._require_robots_allowed(str(item.official_url))
        fetched_at = datetime.now(UTC)
        primary = await self._request(str(item.official_url), kind="detail", referer=self.SEARCH_URL)
        artifacts = [self._artifact(primary, fetched_at), *item.discovery_artifacts]
        soup = BeautifulSoup(primary.content, "html.parser")
        index_urls = [str(value) for value in item.metadata.get("index_official_attachment_urls", [])]
        detail_urls: list[str] = []
        for node in soup.select("a[href*='/File/Download']"):
            if node.get("href"):
                detail_urls.append(urljoin(str(primary.url), node["href"]))

        safe_by_origin: dict[str, list[str]] = {"index": [], "detail": []}
        for origin, urls in (("index", index_urls), ("detail", detail_urls)):
            for url in list(dict.fromkeys(urls))[: self.MAX_ATTACHMENTS]:
                try:
                    attachment_record_id = MojEnforcementExportedIndexParser.validate_url(url, kind="attachment")
                    if attachment_record_id != item.source_record_id:
                        raise ValueError("Administrative Enforcement attachment PATH did not match its detail UUID")
                    safe_by_origin[origin].append(url)
                except ValueError as exc:
                    self.discovery_warnings.append(f"{item.source_record_id}: skipped unsafe official attachment link: {exc}")
        item.metadata["index_official_attachment_urls"] = safe_by_origin["index"]
        item.metadata["detail_official_attachment_urls"] = safe_by_origin["detail"]
        item.metadata["official_attachment_urls"] = list(dict.fromkeys(
            [*safe_by_origin["index"], *safe_by_origin["detail"]]
        ))
        return artifacts

    async def parse(self, item: DiscoveredItem, artifacts: list[RawArtifact]) -> ParsedAuctionRecord:
        record = parse_moj_enforcement_detail(item, artifacts)
        existing = {
            str(evidence.normalized_value)
            for evidence in record.evidence
            if evidence.field_name == "official_attachment_url"
        }
        for url in item.metadata.get("official_attachment_urls", []):
            candidate = str(url)
            if candidate in existing:
                continue
            detail_artifact = next(
                (artifact for artifact in artifacts if str(artifact.official_url) == str(item.official_url)),
                None,
            )
            index_artifact = next(
                (
                    artifact
                    for artifact in artifacts
                    if str(artifact.official_url) == self.SEARCH_URL
                    and artifact.mime_type == "text/html"
                ),
                None,
            )
            artifact = (
                detail_artifact
                if candidate in item.metadata.get("detail_official_attachment_urls", [])
                else index_artifact
            )
            if artifact is None:
                self.discovery_warnings.append(
                    f"{item.source_record_id}: omitted attachment evidence without its exact HTML artifact"
                )
                continue
            record.evidence.append(EvidenceRef(
                field_name="official_attachment_url",
                normalized_value=candidate,
                source_text="官方拍賣公告附件",
                extraction_method="HTML",
                trust="OFFICIAL_EXPLICIT",
                artifact_checksum_sha256=artifact.checksum_sha256,
            ))
        return record

    async def healthcheck(self) -> SourceHealth:
        return SourceHealth(
            source="moj_enforcement",
            status="PARTIAL",
            checked_at=datetime.now(UTC),
            message="Human-reviewed detail manifest or offline exported result HTML is required",
            warnings=["Central Query is REVIEW_REQUIRED; no CAPTCHA or direct result query is used"],
        )
