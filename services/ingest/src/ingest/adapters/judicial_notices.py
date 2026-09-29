from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from ingest.adapters.base import (
    SourceAccessDenied,
    SourceAdapter,
    SourceRateLimited,
    contact_user_agent,
    enforce_http_status,
)
from ingest.models import (
    AuctionStatus,
    BidEligibility,
    CarCategory,
    DiscoveredItem,
    EvidenceRef,
    ExtractionMethod,
    FourState,
    ParsedAuctionRecord,
    RawArtifact,
    RegistrationStatus,
    SourceHealth,
    SourceTrust,
    VehicleClass,
    VehicleIdentifier,
    VehicleType,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _integer(value: str | None) -> int | None:
    if not value:
        return None
    units = {"億": 100_000_000, "萬": 10_000, "千": 1_000, "百": 100, "十": 10}
    parts = re.findall(r"([\d,]+)\s*([億萬千百十])", value)
    if parts:
        total = sum(int(number.replace(",", "")) * units[unit] for number, unit in parts)
        suffix = re.search(r"[億萬千百十]\s*([\d,]+)(?!\s*[億萬千百十])", value)
        return total + (int(suffix.group(1).replace(",", "")) if suffix else 0)
    match = re.search(r"([\d,]+)", value)
    return int(match.group(1).replace(",", "")) if match else None


def _roc_datetime(value: str) -> datetime | None:
    slash = re.search(
        r"(?<!\d)(?P<year>\d{2,4})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})"
        r"(?:\s*(?P<period>上午|下午)?\s*(?P<hour>\d{1,2})[:時](?P<minute>\d{1,2})?)?",
        value,
    )
    written = re.search(
        r"(?:中華民國)?\s*(?P<year>\d{2,4})\s*年\s*(?P<month>\d{1,2})\s*月\s*"
        r"(?P<day>\d{1,2})\s*日(?:(?:(?!上午|下午)[^\d]){0,8}(?P<period>上午|下午)?\s*"
        r"(?P<hour>\d{1,2})?\s*時?\s*(?P<minute>\d{1,2})?\s*分?)?",
        value,
    )
    match = slash or written
    if not match:
        return None
    year = int(match.group("year"))
    year = year + 1911 if year < 1911 else year
    hour = int(match.group("hour") or 0)
    period = match.group("period")
    if period == "下午" and hour < 12:
        hour += 12
    if period == "上午" and hour == 12:
        hour = 0
    try:
        return datetime(
            year,
            int(match.group("month")),
            int(match.group("day")),
            hour,
            int(match.group("minute") or 0),
            tzinfo=TAIPEI,
        )
    except ValueError:
        return None


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper().replace("－", "-"))


def _line_value(lines: list[str], labels: tuple[str, ...]) -> tuple[str | None, str | None]:
    for line in lines:
        for label in labels:
            match = re.search(rf"(?:^|[；;。])\s*{re.escape(label)}\s*[：:]\s*([^；;。]+)", line)
            if match:
                return _clean(match.group(1)), line
    return None, None


def _line_matching(lines: list[str], pattern: str) -> str | None:
    compiled = re.compile(pattern, re.IGNORECASE)
    return next((line for line in lines if compiled.search(line)), None)


def _four_state(
    lines: list[str],
    yes_pattern: str,
    no_pattern: str,
) -> tuple[FourState, list[str]]:
    yes_line = _line_matching(lines, yes_pattern)
    no_line = _line_matching(lines, no_pattern)
    if yes_line and no_line:
        return FourState.CONFLICTING, [yes_line, no_line]
    if yes_line:
        return FourState.YES, [yes_line]
    if no_line:
        return FourState.NO, [no_line]
    return FourState.UNKNOWN, []


def _completeness_groups(group_values: dict[str, list[object]]) -> tuple[int, dict[str, int]]:
    unknowns = {
        FourState.UNKNOWN,
        RegistrationStatus.UNKNOWN,
        BidEligibility.UNKNOWN,
        VehicleType.UNKNOWN,
        VehicleClass.UNKNOWN,
    }

    def present(value: object) -> bool:
        if value is None or value == "" or value == []:
            return False
        try:
            return value not in unknowns
        except TypeError:
            return True

    groups = {
        name: round(sum(present(value) for value in values) / len(values) * 100)
        for name, values in group_values.items()
    }
    weights = {
        "identity": 0.2,
        "auction": 0.25,
        "condition": 0.15,
        "registration": 0.2,
        "fees": 0.1,
        "media": 0.1,
    }
    return round(sum(groups[name] * weights[name] for name in weights)), groups


class JudicialPublicNoticesAdapter(SourceAdapter):
    """Bounded vehicle-auction discovery on Judicial Yuan's main notice site.

    This adapter is intentionally independent from the central movable-auction
    application. It never contacts ``aomp109.judicial.gov.tw`` and never
    downloads attachments or images.
    """

    SOURCE = "judicial_notices"
    ORIGIN = "https://www.judicial.gov.tw"
    ROBOTS_URL = f"{ORIGIN}/robots.txt"
    LIST_URL = f"{ORIGIN}/tw/lp-1913-1.html"
    ALLOWED_HOST = "www.judicial.gov.tw"
    LOOKBACK_DAYS = 180
    MAX_HTML_BYTES = 8 * 1024 * 1024
    MAX_ROBOTS_BYTES = 256 * 1024
    MAX_PAGES_PER_QUERY = 3
    MAX_DETAIL_CANDIDATES = 120
    MAX_REQUEST_ATTEMPTS = 3
    SAFE_RESPONSE_HEADERS = frozenset({
        "cache-control",
        "content-length",
        "content-type",
        "etag",
        "last-modified",
        "location",
    })
    SEARCH_QUERIES = (
        "機車",
        "重機",
        "普通重型機車",
        "大型重型機車",
        "汽車",
        "車輛",
        "小客車",
        "小貨車",
        "貨車",
        "轎車",
        "休旅車",
        "廂型車",
    )
    LIST_PATH = re.compile(r"^/tw/lp-1913-1(?:-\d+-\d+)?\.html$")
    DETAIL_PATH = re.compile(r"^/tw/cp-1913-(\d+)-([A-Za-z0-9]+)-1\.html$")
    DOCUMENT_PATH = re.compile(r"^/tw/dl-\d+-[A-Za-z0-9-]+\.html$")
    EXPLICIT_VEHICLE_ASSET_PATTERN = re.compile(
        r"汽機車|機器腳踏車|普通輕型機車|普通重型機車|大型重型機車|大型重機|"
        r"重型機車|電動機車|機車|重機|(?:自用|營業)?(?:小客|大客|小貨|大貨)車|"
        r"客貨兩用車|休旅車|轎車|廂型車|貨車|曳引車|拖車|遊覽車"
    )
    GENERIC_VEHICLE_ASSET_PATTERN = re.compile(
        r"(?:汽車|車輛)[^\n；。]{0,32}(?:拍賣|標售|變賣|應買|車牌|牌照|廠牌|車型|"
        r"引擎|車身|車架|排氣量|汽缸容量|(?:一|乙|貳|\d+)\s*(?:輛|台))|"
        r"(?:拍賣|標售|變賣|應買)[^\n；。]{0,32}(?:汽車|車輛)"
    )
    VEHICLE_IDENTIFIER_PATTERN = re.compile(
        r"(?:車牌|牌照號碼|車號|引擎號碼|車身號碼|車架號碼)\s*[：:]\s*[A-Z0-9-]{4,24}",
        re.IGNORECASE,
    )
    NON_ASSET_CAR_CONTEXT_PATTERN = re.compile(
        r"汽車(?:股份)?有限公司|汽車公司|汽車商行|汽車企業社|汽車工業"
    )
    AUCTION_PATTERN = re.compile(r"拍賣|標售|變賣|應買")
    EMPTY_PATTERN = re.compile(r"目前尚無資料|查無(?:相關|符合條件)?資料|沒有符合條件的資料")

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        request_interval: float = 1.0,
        now: Callable[[], datetime] | None = None,
        search_queries: tuple[str, ...] | None = None,
        max_pages_per_query: int = MAX_PAGES_PER_QUERY,
        max_detail_candidates: int = MAX_DETAIL_CANDIDATES,
        request_timeout_seconds: float = 20.0,
        max_request_attempts: int = MAX_REQUEST_ATTEMPTS,
    ) -> None:
        queries = search_queries or self.SEARCH_QUERIES
        if not queries or len(queries) > 20 or any(not query.strip() or len(query) > 32 for query in queries):
            raise ValueError("Judicial notice search queries must contain 1-20 short non-empty terms")
        if not 1 <= max_pages_per_query <= 5:
            raise ValueError("Judicial notice page bound must be between one and five")
        if not 1 <= max_detail_candidates <= 200:
            raise ValueError("Judicial notice detail bound must be between one and 200")
        if request_interval < 0 or request_timeout_seconds <= 0 or max_request_attempts < 1:
            raise ValueError("Judicial notice request limits must be positive")
        self.user_agent = contact_user_agent("0.6")
        self.client = client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(request_timeout_seconds),
            headers={"User-Agent": self.user_agent},
        )
        self._owns_client = client is None
        self.request_interval = request_interval
        self.request_timeout_seconds = request_timeout_seconds
        self.max_request_attempts = max_request_attempts
        self.search_queries = tuple(query.strip() for query in queries)
        self.max_pages_per_query = max_pages_per_query
        self.max_detail_candidates = max_detail_candidates
        self._now = now or (lambda: datetime.now(TAIPEI))
        self._last_request = 0.0
        self._request_lock = asyncio.Lock()
        self._robots: RobotFileParser | None = None
        self._detail_cache: dict[str, RawArtifact] = {}
        self.discovery_warnings: list[str] = []

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    @classmethod
    def _validate_url(cls, url: str) -> None:
        parsed = urlparse(url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError(f"Blocked malformed Judicial Yuan URL: {url}") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname != cls.ALLOWED_HOST
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
            or parsed.fragment
        ):
            raise ValueError(f"Blocked non-registered Judicial Yuan URL: {url}")
        if parsed.path == "/robots.txt":
            return
        if not cls.LIST_PATH.fullmatch(parsed.path) and not cls.DETAIL_PATH.fullmatch(parsed.path):
            raise ValueError(f"Blocked out-of-scope Judicial Yuan path: {parsed.path}")

    def _require_robots_allowed(self, url: str) -> None:
        self._validate_url(url)
        if self._robots is None:
            raise SourceAccessDenied("Judicial Yuan robots policy was not verified for this run")
        if not self._robots.can_fetch(self.user_agent, url):
            raise SourceAccessDenied(f"Judicial Yuan robots.txt disallows {urlparse(url).path}")

    async def _wait_for_rate_limit(self) -> None:
        delay = self.request_interval - (time.monotonic() - self._last_request)
        if delay > 0:
            await asyncio.sleep(delay)

    async def _request_once(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None,
        referer: str | None,
        maximum_bytes: int,
        policy_check: bool,
    ) -> httpx.Response:
        current_method = method
        current_url = url
        current_data = data
        for _ in range(5):
            self._validate_url(current_url)
            if policy_check:
                self._require_robots_allowed(current_url)
            await self._wait_for_rate_limit()
            headers = {"Referer": referer} if referer else None
            async with self.client.stream(
                current_method,
                current_url,
                data=current_data,
                headers=headers,
                follow_redirects=False,
                timeout=self.request_timeout_seconds,
            ) as streamed:
                self._last_request = time.monotonic()
                if streamed.is_redirect:
                    if not policy_check:
                        raise SourceAccessDenied("Judicial Yuan robots.txt redirected before policy verification")
                    location = streamed.headers.get("location")
                    if not location:
                        raise ValueError("Judicial Yuan redirect omitted its location")
                    current_url = urljoin(str(streamed.url), location)
                    self._require_robots_allowed(current_url)
                    if streamed.status_code in {301, 302, 303}:
                        current_method = "GET"
                        current_data = None
                    continue
                enforce_http_status(streamed)
                content_length = streamed.headers.get("content-length", "").strip()
                if content_length.isdigit() and int(content_length) > maximum_bytes:
                    raise ValueError(f"Judicial Yuan response exceeds {maximum_bytes} bytes")
                body = bytearray()
                async for chunk in streamed.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > maximum_bytes:
                        raise ValueError(f"Judicial Yuan response exceeds {maximum_bytes} bytes")
                return httpx.Response(
                    streamed.status_code,
                    request=streamed.request,
                    headers=streamed.headers,
                    content=bytes(body),
                )
        raise ValueError("Judicial Yuan redirect limit exceeded")

    async def _request(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None = None,
        referer: str | None = None,
        maximum_bytes: int | None = None,
        policy_check: bool = True,
    ) -> httpx.Response:
        maximum = maximum_bytes if maximum_bytes is not None else self.MAX_HTML_BYTES
        if maximum <= 0 or maximum > self.MAX_HTML_BYTES:
            raise ValueError("Judicial Yuan response-size boundary is invalid")
        self._validate_url(url)
        last_error: Exception | None = None
        async with self._request_lock:
            for attempt in range(self.max_request_attempts):
                try:
                    return await self._request_once(
                        method,
                        url,
                        data=data,
                        referer=referer,
                        maximum_bytes=maximum,
                        policy_check=policy_check,
                    )
                except (SourceAccessDenied, SourceRateLimited, ValueError):
                    raise
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code < 500:
                        raise
                    last_error = exc
                except httpx.TransportError as exc:
                    last_error = exc
                if attempt < self.max_request_attempts - 1:
                    await asyncio.sleep(2**attempt)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _content_type(response: httpx.Response) -> str:
        return response.headers.get("content-type", "").split(";", 1)[0].strip().lower()

    @classmethod
    def _require_mime(cls, response: httpx.Response, allowed: set[str], stage: str) -> None:
        content_type = cls._content_type(response)
        if content_type not in allowed:
            raise ValueError(f"Judicial Yuan {stage} returned unsupported MIME type: {content_type}")

    async def _load_robots(self) -> None:
        self._robots = None
        response = await self._request(
            "GET",
            self.ROBOTS_URL,
            maximum_bytes=self.MAX_ROBOTS_BYTES,
            policy_check=False,
        )
        self._require_mime(response, {"text/plain"}, "robots.txt")
        robots_text = response.text
        if not re.search(r"^\s*User-agent\s*:", robots_text, re.IGNORECASE | re.MULTILINE):
            raise SourceAccessDenied("Judicial Yuan robots.txt lacks a User-agent directive")
        parser = RobotFileParser()
        parser.set_url(self.ROBOTS_URL)
        parser.parse(robots_text.splitlines())
        self._robots = parser
        self._require_robots_allowed(self.LIST_URL)

    @classmethod
    def _artifact_headers(cls, response: httpx.Response) -> dict[str, str]:
        return {
            key.lower(): value
            for key, value in response.headers.items()
            if key.lower() in cls.SAFE_RESPONSE_HEADERS
        }

    @classmethod
    def _artifact(cls, response: httpx.Response, filename: str) -> RawArtifact:
        cls._require_mime(response, {"text/html"}, "HTML page")
        return RawArtifact(
            official_url=str(response.url),
            fetched_at=datetime.now(UTC),
            mime_type="text/html",
            filename=filename,
            content=response.content,
            http_status=response.status_code,
            http_headers=cls._artifact_headers(response),
            checksum_sha256=hashlib.sha256(response.content).hexdigest(),
        )

    @classmethod
    def _validate_search_form(cls, content: bytes) -> None:
        soup = BeautifulSoup(content, "html.parser")
        form = soup.select_one("section.lp form.form_grid[method]")
        if not isinstance(form, Tag) or str(form.get("method", "")).lower() != "post":
            raise ValueError("Judicial Yuan notice search form marker changed")
        action = urljoin(cls.LIST_URL, str(form.get("action") or ""))
        if action != cls.LIST_URL:
            raise ValueError("Judicial Yuan notice search form action changed")
        expected = {
            "Action",
            "Q_DMDeptMainID",
            "TBOXDMPostDateS",
            "TBOXDMPostDateE",
            "Q_DMBody",
            "lstoken",
            "BtnSubmit",
        }
        names = {str(node.get("name")) for node in form.select("input[name], select[name]")}
        action_input = form.select_one("input[name='Action']")
        if not expected.issubset(names) or not action_input or action_input.get("value") != "Qeury":
            raise ValueError("Judicial Yuan notice search fields changed")

    @staticmethod
    def _roc_date(value: str) -> datetime | None:
        match = re.search(r"(?<!\d)(\d{2,3})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", value)
        if not match:
            return None
        try:
            return datetime(
                int(match.group(1)) + 1911,
                int(match.group(2)),
                int(match.group(3)),
                tzinfo=TAIPEI,
            )
        except ValueError:
            return None

    @staticmethod
    def _roc_form_date(value: datetime) -> str:
        return f"{value.year - 1911:03d}/{value.month:02d}/{value.day:02d}"

    @classmethod
    def _record_identity(cls, url: str) -> str | None:
        match = cls.DETAIL_PATH.fullmatch(urlparse(url).path)
        return f"{match.group(1)}-{match.group(2).lower()}" if match else None

    def _items_from_search_page(
        self,
        content: bytes,
        discovery_url: str,
        cutoff: datetime,
        now: datetime,
    ) -> tuple[list[DiscoveredItem], str | None]:
        soup = BeautifulSoup(content, "html.parser")
        table = soup.select_one("div.table_list table")
        page_text = _clean(soup.get_text(" ", strip=True))
        explicit_empty = bool(self.EMPTY_PATTERN.search(page_text))
        if table is None:
            if explicit_empty:
                return [], None
            raise ValueError("Judicial Yuan search markup changed: result table and empty marker are absent")
        rows = soup.select("div.table_list table tbody tr")
        if not rows and not explicit_empty:
            raise ValueError("Judicial Yuan search markup changed: empty table lacks an official zero-result marker")

        items: list[DiscoveredItem] = []
        for row in rows:
            link = row.select_one("td[data-title='標題'] a[href]")
            date_cell = row.select_one("td[data-title='張貼日']")
            organization_cell = row.select_one("td[data-title='單位/機關']")
            if not link or not date_cell or not organization_cell:
                raise ValueError("Judicial Yuan search result row marker changed")
            title = _clean(link.get_text(" ", strip=True) or str(link.get("title") or ""))
            published_at = self._roc_date(date_cell.get_text(" ", strip=True))
            if not title or published_at is None:
                raise ValueError("Judicial Yuan search result title/date could not be verified")
            if published_at < cutoff or published_at > now + timedelta(days=1):
                self.discovery_warnings.append(
                    f"Skipped one notice outside the verified {self.LOOKBACK_DAYS}-day publication window"
                )
                continue
            detail_url = urljoin(discovery_url, str(link.get("href") or ""))
            try:
                self._validate_url(detail_url)
            except ValueError:
                self.discovery_warnings.append("Skipped one result whose detail URL left the reviewed cp-1913 path")
                continue
            source_record_id = self._record_identity(detail_url)
            if source_record_id is None:
                self.discovery_warnings.append("Skipped one result whose official notice identity was not recognized")
                continue
            items.append(
                DiscoveredItem(
                    source_record_id=source_record_id,
                    official_url=detail_url,
                    title=title,
                    discovery_url=discovery_url,
                    metadata={
                        "organization": _clean(organization_cell.get_text(" ", strip=True)),
                        "published_date": published_at.date().isoformat(),
                        "discovery_method": "JUDICIAL_MAIN_OTHER_NOTICES",
                    },
                )
            )

        next_link = soup.select_one("ul.page a[title='下一頁'][href]")
        next_url = urljoin(discovery_url, str(next_link.get("href"))) if next_link else None
        if next_url:
            self._validate_url(next_url)
            if not self.LIST_PATH.fullmatch(urlparse(next_url).path):
                raise ValueError("Judicial Yuan next-page URL left the reviewed notice list")
        return items, next_url

    @staticmethod
    def _detail_parts(content: bytes) -> tuple[str, Tag, list[str]]:
        soup = BeautifulSoup(content, "html.parser")
        title_node = soup.select_one("div.content_block h2.pageTitle")
        article = soup.select_one("div.content_block section.cp")
        if not isinstance(title_node, Tag) or not isinstance(article, Tag):
            raise ValueError("Judicial Yuan notice detail markers changed")
        title = _clean(title_node.get_text(" ", strip=True))
        if not title:
            raise ValueError("Judicial Yuan notice detail title is empty")
        lines = [_clean(value) for value in article.stripped_strings if _clean(value)]
        if not lines:
            raise ValueError("Judicial Yuan notice detail body is empty")
        return title, article, lines

    @classmethod
    def _vehicle_semantic_text(cls, value: str) -> str:
        text = cls.NON_ASSET_CAR_CONTEXT_PATTERN.sub("公司", value)
        text = re.sub(r"汽車燃料(?:使用)?費", "燃料費", text)
        return re.sub(r"(?:汽車|機車)?停車位", "停車位", text)

    @classmethod
    def _is_vehicle_auction_detail(cls, title: str, lines: list[str]) -> bool:
        text = _clean(" ".join((title, *lines)))
        text = cls._vehicle_semantic_text(text)
        vehicle_asset = (
            cls.EXPLICIT_VEHICLE_ASSET_PATTERN.search(text)
            or cls.GENERIC_VEHICLE_ASSET_PATTERN.search(text)
            or cls.VEHICLE_IDENTIFIER_PATTERN.search(text)
        )
        return bool(vehicle_asset and cls.AUCTION_PATTERN.search(text))

    @staticmethod
    def _disposal_origin_from_official_text(value: str) -> str:
        if "行政執行" in value:
            return "ADMINISTRATIVE_ENFORCEMENT"
        if re.search(r"強制執行|民事執行|司執|執行事件|應買", value):
            return "JUDICIAL_EXECUTION"
        if re.search(r"報廢|汰換|廢品|廢料", value):
            return "SCRAP_DISPOSAL"
        if re.search(r"公有財產|財物變賣|財產標售|機關標售", value):
            return "PUBLIC_ASSET_DISPOSAL"
        return "UNKNOWN"

    async def _fetch_detail_artifact(self, item: DiscoveredItem) -> RawArtifact:
        cached = self._detail_cache.get(item.source_record_id)
        if cached is not None:
            return cached
        if self._robots is None:
            await self._load_robots()
        self._require_robots_allowed(str(item.official_url))
        response = await self._request(
            "GET",
            str(item.official_url),
            referer=self.LIST_URL,
        )
        artifact = self._artifact(response, f"judicial-notice-{item.source_record_id}.html")
        self._detail_cache[item.source_record_id] = artifact
        return artifact

    async def discover(self) -> list[DiscoveredItem]:
        self.discovery_warnings.clear()
        self._detail_cache.clear()
        await self._load_robots()
        form_response = await self._request("GET", self.LIST_URL, referer=self.ORIGIN)
        self._require_mime(form_response, {"text/html"}, "search form")
        self._validate_search_form(form_response.content)

        now = self._now().astimezone(TAIPEI)
        cutoff = now - timedelta(days=self.LOOKBACK_DAYS)
        candidates: dict[str, DiscoveredItem] = {}
        artifacts_by_record: dict[str, list[RawArtifact]] = {}

        for query in self.search_queries:
            next_url: str | None = self.LIST_URL
            for page in range(1, self.max_pages_per_query + 1):
                if page == 1:
                    response = await self._request(
                        "POST",
                        self.LIST_URL,
                        data={
                            "Action": "Qeury",
                            "Q_DMDeptMainID": "",
                            "TBOXDMPostDateS": self._roc_form_date(cutoff),
                            "TBOXDMPostDateE": self._roc_form_date(now),
                            "Q_DMBody": query,
                            "lstoken": str(secrets.randbelow(10_000_000_000)),
                            "BtnSubmit": "查詢",
                        },
                        referer=self.LIST_URL,
                    )
                else:
                    if next_url is None:
                        break
                    response = await self._request("GET", next_url, referer=self.LIST_URL)
                self._require_mime(response, {"text/html"}, "search results")
                query_key = hashlib.sha256(query.encode()).hexdigest()[:10]
                discovery_artifact = self._artifact(
                    response,
                    f"judicial-notices-search-{query_key}-p{page}.html",
                )
                page_items, next_url = self._items_from_search_page(
                    response.content,
                    str(response.url),
                    cutoff,
                    now,
                )
                for item in page_items:
                    existing = candidates.get(item.source_record_id)
                    if existing is None:
                        item.metadata["query_terms"] = [query]
                        candidates[item.source_record_id] = item
                    elif query not in existing.metadata.get("query_terms", []):
                        existing.metadata.setdefault("query_terms", []).append(query)
                    stored = artifacts_by_record.setdefault(item.source_record_id, [])
                    if all(
                        artifact.checksum_sha256 != discovery_artifact.checksum_sha256
                        for artifact in stored
                    ):
                        stored.append(discovery_artifact)
                if next_url is None:
                    break
                if page == self.max_pages_per_query:
                    self.discovery_warnings.append(
                        f"Query '{query}' reached the {self.max_pages_per_query}-page safety bound; coverage is partial"
                    )

        ordered = sorted(
            candidates.values(),
            key=lambda item: str(item.metadata.get("published_date", "")),
            reverse=True,
        )
        if len(ordered) > self.max_detail_candidates:
            self.discovery_warnings.append(
                f"Candidate details exceeded the {self.max_detail_candidates}-record safety bound; coverage is partial"
            )
            ordered = ordered[: self.max_detail_candidates]

        discovered: list[DiscoveredItem] = []
        changed_markup = 0
        for item in ordered:
            try:
                detail = await self._fetch_detail_artifact(item)
                title, _, lines = self._detail_parts(detail.content)
            except (SourceAccessDenied, SourceRateLimited):
                raise
            except (httpx.HTTPError, ValueError) as exc:
                changed_markup += 1
                self.discovery_warnings.append(
                    f"{item.source_record_id}: detail could not be verified ({type(exc).__name__})"
                )
                continue
            if not self._is_vehicle_auction_detail(title, lines):
                continue
            item.discovery_artifacts = artifacts_by_record.get(item.source_record_id, [])
            discovered.append(item)
        if ordered and changed_markup == len(ordered):
            raise ValueError("No Judicial Yuan candidate detail retained the required official detail markers")
        return discovered

    async def fetch(self, item: DiscoveredItem) -> list[RawArtifact]:
        detail = await self._fetch_detail_artifact(item)
        artifacts = [detail]
        for artifact in item.discovery_artifacts:
            if all(existing.checksum_sha256 != artifact.checksum_sha256 for existing in artifacts):
                artifacts.append(artifact)
        return artifacts

    @classmethod
    def _document_urls(cls, article: Tag) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for link in article.select("a[href]"):
            url = urljoin(cls.ORIGIN, str(link.get("href") or ""))
            try:
                parsed = urlparse(url)
                port = parsed.port
            except ValueError:
                continue
            if (
                parsed.scheme == "https"
                and parsed.hostname == cls.ALLOWED_HOST
                and port in {None, 443}
                and not parsed.query
                and not parsed.fragment
                and cls.DOCUMENT_PATH.fullmatch(parsed.path)
            ):
                pair = (url, _clean(link.get_text(" ", strip=True)) or str(link.get("href")))
                if pair not in found:
                    found.append(pair)
        return found

    @staticmethod
    def _append_evidence(
        evidence: list[EvidenceRef],
        checksum: str,
        field_name: str,
        normalized_value: object,
        source_text: str,
        *,
        trust: SourceTrust = SourceTrust.OFFICIAL_EXPLICIT,
    ) -> None:
        evidence.append(
            EvidenceRef(
                field_name=field_name,
                normalized_value=normalized_value,
                source_text=source_text,
                extraction_method=ExtractionMethod.HTML,
                trust=trust,
                artifact_checksum_sha256=checksum,
            )
        )

    async def parse(
        self,
        item: DiscoveredItem,
        artifacts: list[RawArtifact],
    ) -> ParsedAuctionRecord:
        detail = next(
            (
                artifact
                for artifact in artifacts
                if artifact.mime_type == "text/html"
                and str(artifact.official_url) == str(item.official_url)
                and self.DETAIL_PATH.fullmatch(urlparse(str(artifact.official_url)).path)
            ),
            None,
        )
        if detail is None:
            raise ValueError("Judicial Yuan notice detail HTML is required for parsing")
        title, article, lines = self._detail_parts(detail.content)
        if not self._is_vehicle_auction_detail(title, lines):
            raise ValueError("Judicial Yuan notice is not an explicit vehicle auction")
        checksum = detail.checksum_sha256
        evidence: list[EvidenceRef] = []
        self._append_evidence(evidence, checksum, "official_title", title, title)
        self._append_evidence(evidence, checksum, "title", title, title)

        organization_value, organization_line = _line_value(lines, ("發布單位",))
        if not organization_value or not organization_line:
            raise ValueError("Judicial Yuan notice has no verified publishing organization")
        self._append_evidence(
            evidence,
            checksum,
            "organization",
            organization_value,
            organization_line,
        )
        normalized_text = _clean(" ".join((title, *lines)))
        disposal_origin = self._disposal_origin_from_official_text(normalized_text)
        origin_patterns = {
            "JUDICIAL_EXECUTION": r"強制執行|民事執行|司執|執行事件|應買",
            "ADMINISTRATIVE_ENFORCEMENT": r"行政執行",
            "SCRAP_DISPOSAL": r"報廢|汰換|廢品|廢料",
            "PUBLIC_ASSET_DISPOSAL": r"公有財產|財物變賣|財產標售|機關標售",
        }
        origin_line = _line_matching([title, *lines], origin_patterns.get(disposal_origin, r"$^")) or title
        self._append_evidence(
            evidence,
            checksum,
            "disposal_origin",
            disposal_origin,
            origin_line,
            trust=SourceTrust.OFFICIAL_INFERRED,
        )

        case_value, case_line = _line_value(lines, ("案號", "發文字號"))
        if case_value is None:
            for line in (title, *lines):
                match = re.search(r"\d{2,3}年度(?:司)?執[^\s，,；;。]{0,12}字第?[\w-]+號", line)
                if match:
                    case_value, case_line = match.group(0), line
                    break
        if case_value and case_line:
            self._append_evidence(evidence, checksum, "official_case_number", case_value, case_line)

        auction_line = _line_matching(
            lines,
            r"(?:拍賣|標售|變賣)(?:日期|時間)|投標截止(?:日期|時間)?|開標(?:日期|時間)?",
        )
        auction_at = _roc_datetime(auction_line) if auction_line else None
        status = AuctionStatus.UNKNOWN
        if auction_at and auction_line:
            status = AuctionStatus.SCHEDULED if auction_at > self._now().astimezone(TAIPEI) else AuctionStatus.EXPIRED
            self._append_evidence(evidence, checksum, "ends_at", auction_at.isoformat(), auction_line)
            self._append_evidence(
                evidence,
                checksum,
                "status",
                status.value,
                auction_line,
                trust=SourceTrust.SYSTEM_CALCULATED,
            )

        round_number = None
        round_line = _line_matching([title, *lines], r"第\s*\d+\s*(?:次拍賣|拍)")
        if round_line:
            round_match = re.search(r"第\s*(\d+)\s*(?:次拍賣|拍)", round_line)
            if round_match:
                round_number = int(round_match.group(1))
                self._append_evidence(evidence, checksum, "auction_round", round_number, round_line)

        reserve_value, reserve_line = _line_value(lines, ("拍賣最低價額", "最低價額", "底價"))
        reserve_price = _integer(reserve_value)
        if reserve_price is not None and reserve_line:
            self._append_evidence(evidence, checksum, "reserve_price", reserve_price, reserve_line)
        deposit_value, deposit_line = _line_value(lines, ("保證金", "押標金"))
        deposit = _integer(deposit_value)
        if deposit is not None and deposit_line:
            self._append_evidence(evidence, checksum, "deposit", deposit, deposit_line)

        location, location_line = _line_value(
            lines,
            ("拍賣地點", "標售地點", "車輛所在地", "保管地點", "存放地點"),
        )
        if location and location_line:
            self._append_evidence(evidence, checksum, "location", location, location_line)

        brand, brand_line = _line_value(lines, ("廠牌名稱", "廠牌"))
        model, model_line = _line_value(lines, ("車型", "型號", "型式"))
        displacement_value, displacement_line = _line_value(lines, ("排氣量", "汽缸容量"))
        displacement = _integer(displacement_value)
        manufacture_value, manufacture_line = _line_value(
            lines,
            ("出廠年月", "出廠日期", "出廠年份", "製造年月"),
        )
        manufacture_year = None
        manufacture_month = None
        if manufacture_value:
            manufacture_match = re.search(r"(\d{2,4})(?:\D+(\d{1,2}))?", manufacture_value)
            if manufacture_match:
                manufacture_year = int(manufacture_match.group(1))
                manufacture_year = manufacture_year + 1911 if manufacture_year < 1911 else manufacture_year
                manufacture_month = int(manufacture_match.group(2)) if manufacture_match.group(2) else None
                if manufacture_month is not None and not 1 <= manufacture_month <= 12:
                    manufacture_month = None
        color, color_line = _line_value(lines, ("車色", "顏色"))
        mileage_value, mileage_line = _line_value(lines, ("里程數", "里程"))
        mileage = _integer(mileage_value)
        for field_name, normalized, source_line in (
            ("brand", brand, brand_line),
            ("model", model, model_line),
            ("displacement_cc", displacement, displacement_line),
            ("manufacture_year", manufacture_year, manufacture_line),
            ("manufacture_month", manufacture_month, manufacture_line),
            ("color", color, color_line),
            ("mileage_km", mileage, mileage_line),
        ):
            if normalized is not None and source_line:
                self._append_evidence(evidence, checksum, field_name, normalized, source_line)

        type_text = self._vehicle_semantic_text(normalized_text)
        combined_match = re.search(r"汽(?:車)?(?:、|及|與|和)?機車|汽機車", type_text)
        motorcycle_match = re.search(
            r"普通輕型機車|普通重型機車|大型重型機車|大型重機|電動機車|重型機車|機器腳踏車|機車|重機",
            type_text,
        )
        car_match = re.search(
            r"自用小客車|營業小客車|小客車|大客車|自用小貨車|營業小貨車|小貨車|大貨車|"
            r"客貨兩用車|休旅車|轎車|廂型車|貨車|汽車",
            type_text,
        )
        if combined_match or (motorcycle_match and car_match):
            vehicle_type = VehicleType.MIXED
        elif motorcycle_match:
            vehicle_type = VehicleType.MOTORCYCLE
        elif car_match:
            vehicle_type = VehicleType.CAR
        else:
            vehicle_type = VehicleType.UNKNOWN
        type_lines: list[str] = []
        if combined_match:
            combined_line = _line_matching([title, *lines], re.escape(combined_match.group(0)))
            if combined_line:
                type_lines.append(combined_line)
        else:
            for type_match in (motorcycle_match, car_match):
                if type_match:
                    matched_line = _line_matching([title, *lines], re.escape(type_match.group(0)))
                    if matched_line and matched_line not in type_lines:
                        type_lines.append(matched_line)
        for type_line in type_lines:
            self._append_evidence(evidence, checksum, "vehicle_type", vehicle_type.value, type_line)

        class_patterns = (
            (VehicleClass.ELECTRIC_MOTORCYCLE, r"(?:普通輕型|普通重型|大型重型)?電動機車"),
            (VehicleClass.LARGE_HEAVY, r"大型重型機車|大型重機"),
            (VehicleClass.ORDINARY_HEAVY, r"普通重型機車"),
            (VehicleClass.ORDINARY_LIGHT, r"普通輕型機車"),
            (VehicleClass.HEAVY_UNSPECIFIED, r"重型機車"),
        )
        vehicle_class = VehicleClass.UNKNOWN
        class_line = None
        for candidate, pattern in class_patterns:
            class_line = _line_matching([title, *lines], pattern)
            if class_line:
                vehicle_class = candidate
                break
        if class_line:
            self._append_evidence(evidence, checksum, "vehicle_class", vehicle_class.value, class_line)

        car_patterns = (
            (CarCategory.SUV, r"休旅車|SUV"),
            (CarCategory.VAN, r"廂型車|客貨兩用車"),
            (CarCategory.TRUCK, r"(?:小貨|大貨)車|貨車|曳引車"),
            (CarCategory.BUS, r"大客車|遊覽車"),
            (CarCategory.PASSENGER, r"轎車|(?:自用|營業)?小客車"),
        )
        car_category = CarCategory.UNKNOWN
        car_line = None
        for candidate, pattern in car_patterns:
            car_line = _line_matching([title, *lines], pattern)
            if car_line:
                car_category = candidate
                break
        if car_line:
            self._append_evidence(evidence, checksum, "car_category", car_category.value, car_line)

        identifiers: list[VehicleIdentifier] = []
        for identifier_type, labels in (
            ("PLATE", ("車牌號碼", "牌照號碼", "車牌", "牌照")),
            ("ENGINE", ("引擎號碼", "引擎號", "引擎編號")),
            ("FRAME", ("車身號碼", "車架號碼", "車身號", "車架號")),
        ):
            raw_value, source_line = _line_value(lines, labels)
            if not raw_value or not source_line:
                continue
            values = [
                value
                for value in re.split(r"[、,，；;\s]+", raw_value)
                if _normalize_identifier(value)
            ]
            for value in values:
                identifier = VehicleIdentifier(
                    identifier_type=identifier_type,
                    normalized_value=_normalize_identifier(value),
                    original_value=value,
                )
                if identifier not in identifiers:
                    identifiers.append(identifier)
                    self._append_evidence(
                        evidence,
                        checksum,
                        identifier_type.lower(),
                        identifier.normalized_value,
                        source_line,
                    )

        has_key, has_key_lines = _four_state(
            lines,
            r"(?<!未)(?<!無)附(?:有)?鑰匙|(?<!沒)(?<!無)有鑰匙|鑰匙\s*\d+\s*支",
            r"無鑰匙|未附鑰匙|沒有鑰匙",
        )
        can_start, can_start_lines = _four_state(
            lines,
            r"(?<!不)(?<!無)(?<!未)可發動|發動正常",
            r"無法發動|不能發動|不可發動",
        )
        can_test, can_test_lines = _four_state(
            lines,
            r"(?<!不)(?<!無)(?<!未)可試車|(?<!不)得試車",
            r"不得試車|不可試車|不能試車",
        )
        for field_name, state, source_lines in (
            ("has_key", has_key, has_key_lines),
            ("can_start", can_start, can_start_lines),
            ("can_test", can_test, can_test_lines),
        ):
            for source_line in source_lines:
                self._append_evidence(evidence, checksum, field_name, state.value, source_line)

        eligibility = BidEligibility.UNKNOWN
        eligibility_line = _line_matching(lines, r"限.*(?:回收|廢棄物).*(?:業者|機構)")
        if eligibility_line:
            eligibility = BidEligibility.LICENSED_RECYCLER_ONLY
        else:
            eligibility_line = _line_matching(lines, r"一般民眾.*(?:投標|參加)|任何人均可參加|公開投標")
            if eligibility_line:
                eligibility = BidEligibility.PUBLIC
        if eligibility_line:
            self._append_evidence(evidence, checksum, "eligibility", eligibility.value, eligibility_line)

        registration_status = RegistrationStatus.UNKNOWN
        registration_patterns = (
            (RegistrationStatus.SCRAP_ONLY, r"僅供報廢|限報廢|報廢車"),
            (RegistrationStatus.CANNOT_RELICENSE, r"不得重新領牌|不得領牌"),
            (RegistrationStatus.DEREGISTERED, r"已報廢|牌照(?:已)?註銷"),
            (RegistrationStatus.INSPECTION_REQUIRED, r"須經檢驗|應經檢驗"),
            (RegistrationStatus.RE_REGISTRATION_REQUIRED, r"須重新領牌|應重新領牌"),
            (RegistrationStatus.NORMAL_TRANSFER, r"可辦理過戶|得辦理過戶"),
        )
        registration_line = None
        for candidate, pattern in registration_patterns:
            registration_line = _line_matching(lines, pattern)
            if registration_line:
                registration_status = candidate
                break
        if registration_line:
            self._append_evidence(
                evidence,
                checksum,
                "registration_status",
                registration_status.value,
                registration_line,
            )

        condition_summary, condition_line = _line_value(
            lines,
            ("車輛狀況", "物品狀況", "車況", "現況"),
        )
        if condition_summary and condition_line:
            self._append_evidence(
                evidence,
                checksum,
                "condition_summary",
                condition_summary,
                condition_line,
            )
            self._append_evidence(
                evidence,
                checksum,
                "description",
                condition_summary,
                condition_line,
            )

        fee_notes = [
            line
            for line in lines
            if re.search(r"規費|稅費|拖吊費|保管費|燃料費|牌照稅", line)
        ][:8]
        for fee_line in fee_notes:
            self._append_evidence(evidence, checksum, "fee_notes", fee_line, fee_line)

        lot_size = 1
        lot_line = _line_matching([title, *lines], r"共\s*\d+\s*(?:輛|台)|\d+\s*(?:輛|台)")
        if lot_line:
            lot_match = re.search(r"(?:共\s*)?(\d+)\s*(?:輛|台)", lot_line)
            if lot_match and int(lot_match.group(1)) > 0:
                lot_size = int(lot_match.group(1))
                self._append_evidence(evidence, checksum, "lot_size", lot_size, lot_line)
                self._append_evidence(
                    evidence,
                    checksum,
                    "bulk_lot",
                    lot_size > 1,
                    lot_line,
                    trust=SourceTrust.SYSTEM_CALCULATED,
                )

        document_urls = self._document_urls(article)
        for url, label in document_urls:
            self._append_evidence(evidence, checksum, "official_attachment_url", url, label)

        completeness, groups = _completeness_groups({
            "identity": [vehicle_type, vehicle_class, brand, model, displacement, identifiers],
            "auction": [organization_value, status, auction_at, reserve_price, round_number],
            "condition": [has_key, can_start, can_test, condition_summary],
            "registration": [eligibility, registration_status],
            "fees": [deposit, fee_notes],
            "media": [document_urls],
        })
        return ParsedAuctionRecord(
            source_record_id=item.source_record_id,
            official_url=item.official_url,
            official_title=title,
            official_case_number=case_value,
            organization=organization_value,
            disposal_origin=disposal_origin,
            status=status,
            auction_round=round_number,
            ends_at=auction_at,
            reserve_price=reserve_price,
            deposit=deposit,
            fee_notes=fee_notes,
            title=title,
            lot_size=lot_size,
            bulk_lot=lot_size > 1,
            eligibility=eligibility,
            location=location,
            description=condition_summary,
            brand=brand,
            model=model,
            manufacture_year=manufacture_year,
            manufacture_month=manufacture_month,
            displacement_cc=displacement,
            vehicle_type=vehicle_type,
            vehicle_class=vehicle_class,
            car_category=car_category,
            color=color,
            mileage_km=mileage,
            has_key=has_key,
            can_start=can_start,
            can_test=can_test,
            registration_status=registration_status,
            condition_summary=condition_summary,
            identifiers=identifiers,
            photo_urls=[],
            evidence=evidence,
            completeness=completeness,
            completeness_groups=groups,
        )

    async def healthcheck(self) -> SourceHealth:
        start = time.monotonic()
        try:
            await self._load_robots()
            response = await self._request("GET", self.LIST_URL, referer=self.ORIGIN)
            self._require_mime(response, {"text/html"}, "healthcheck")
            self._validate_search_form(response.content)
            return SourceHealth(
                source=self.SOURCE,
                status="ACTIVE",
                checked_at=datetime.now(UTC),
                response_ms=round((time.monotonic() - start) * 1000),
                message="司法院主站其他司法公告的 robots 與搜尋表單均可安全讀取",
            )
        except Exception as exc:
            return SourceHealth(
                source=self.SOURCE,
                status="DEGRADED",
                checked_at=datetime.now(UTC),
                response_ms=round((time.monotonic() - start) * 1000),
                message=str(exc),
            )
