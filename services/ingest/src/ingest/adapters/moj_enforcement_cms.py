from __future__ import annotations

import asyncio
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

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
    DiscoveredItem,
    EvidenceRef,
    FourState,
    ParsedAuctionRecord,
    ParsedVehicleUnit,
    RawArtifact,
    RegistrationStatus,
    SourceHealth,
    VehicleIdentifier,
    VehicleType,
)
from ingest.parser import (
    TAIPEI,
    _completeness_groups,
    _explicit_fact_sentence,
    _label_value,
    _plate_values_for_type,
    _redact_personal_data,
    _vehicle_identity,
    car_category_from_official_text,
    clean,
    integer,
    motorcycle_class_from_official_text,
    normalize_identifier,
    official_datetime,
    vehicle_type_from_official_text,
)


@dataclass(frozen=True)
class EnforcementBranch:
    code: str
    organization: str

    @property
    def host(self) -> str:
        return f"www.{self.code}.moj.gov.tw"

    @property
    def origin(self) -> str:
        return f"https://{self.host}"


ENFORCEMENT_BRANCHES = (
    EnforcementBranch("tpy", "法務部行政執行署臺北分署"),
    EnforcementBranch("sly", "法務部行政執行署士林分署"),
    EnforcementBranch("pcy", "法務部行政執行署新北分署"),
    EnforcementBranch("tyy", "法務部行政執行署桃園分署"),
    EnforcementBranch("scy", "法務部行政執行署新竹分署"),
    EnforcementBranch("tcy", "法務部行政執行署臺中分署"),
    EnforcementBranch("chy", "法務部行政執行署彰化分署"),
    EnforcementBranch("cyy", "法務部行政執行署嘉義分署"),
    EnforcementBranch("tny", "法務部行政執行署臺南分署"),
    EnforcementBranch("ksy", "法務部行政執行署高雄分署"),
    EnforcementBranch("pty", "法務部行政執行署屏東分署"),
    EnforcementBranch("hly", "法務部行政執行署花蓮分署"),
    EnforcementBranch("ily", "法務部行政執行署宜蘭分署"),
)


class MojEnforcementCmsAdapter(SourceAdapter):
    """Bounded discovery on the 13 public Administrative Enforcement CMS sites.

    This is deliberately separate from the CAPTCHA-gated centralized search. It
    reads only each branch's published robots file, declared sitemap, homepage,
    announcement lists, and matching official HTML detail pages.
    """

    LOOKBACK_DAYS = 90
    MAX_LISTS_PER_BRANCH = 2
    MAX_LIST_PAGES = 2
    PAGE_SIZE = 30
    MAX_BYTES = 25 * 1024 * 1024
    MAX_SITEMAP_BYTES = 8 * 1024 * 1024
    MAX_ATTACHMENTS = 10
    SAFE_ARTIFACT_RESPONSE_HEADERS = frozenset({
        "cache-control",
        "content-disposition",
        "content-length",
        "content-type",
        "etag",
        "last-modified",
    })
    VEHICLE_PATTERN = re.compile(
        r"汽機車|汽車|機車|機器腳踏車|大型重機|重型機車|重機|車輛|"
        r"小客車|大客車|客貨兩用車|休旅車|轎車|廂型車|小貨車|大貨車|貨車|"
        r"曳引車|半拖車|拖車|遊覽車"
    )
    AUCTION_PATTERN = re.compile(r"拍賣|變賣|標售|應買")
    LIST_LABELS = ("動產拍賣公告", "拍賣品消息", "電子公布欄", "最新消息")

    def __init__(
        self,
        branches: tuple[EnforcementBranch, ...] = ENFORCEMENT_BRANCHES,
        client: httpx.AsyncClient | None = None,
        request_interval: float = 1.0,
        now: Callable[[], datetime] | None = None,
        request_timeout_seconds: float = 12.0,
        max_request_attempts: int = 2,
        branch_deadline_seconds: float = 45.0,
    ) -> None:
        if request_timeout_seconds <= 0 or branch_deadline_seconds <= 0:
            raise ValueError("CMS request and branch deadlines must be positive")
        if max_request_attempts < 1:
            raise ValueError("CMS request attempts must be at least one")
        self.branches = branches
        self.allowed_hosts = {branch.host for branch in branches}
        self.user_agent = contact_user_agent("0.5")
        self.client = client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(request_timeout_seconds),
            headers={"User-Agent": self.user_agent},
        )
        self._owns_client = client is None
        self.request_interval = request_interval
        self.request_timeout_seconds = request_timeout_seconds
        self.max_request_attempts = max_request_attempts
        self.branch_deadline_seconds = branch_deadline_seconds
        self._last_request = 0.0
        self._request_lock = asyncio.Lock()
        self._now = now or (lambda: datetime.now(TAIPEI))
        self.discovery_warnings: list[str] = []
        self._robots_by_host: dict[str, RobotFileParser] = {}

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    def _validate_url(self, url: str, *, expected_host: str | None = None) -> None:
        parsed = urlparse(url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError(f"Blocked malformed source URL: {url}") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self.allowed_hosts
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
        ):
            raise ValueError(f"Blocked non-registered source URL: {url}")
        if expected_host and parsed.hostname != expected_host:
            raise ValueError(f"Blocked cross-branch redirect: {url}")

    async def _request(self, url: str, *, expected_host: str, referer: str | None = None) -> httpx.Response:
        self._validate_url(url, expected_host=expected_host)
        last_error: Exception | None = None
        for attempt in range(self.max_request_attempts):
            async with self._request_lock:
                delay = self.request_interval - (time.monotonic() - self._last_request)
                if delay > 0:
                    await asyncio.sleep(delay)
                try:
                    current_url = url
                    for _ in range(5):
                        headers = {"Referer": referer} if referer else None
                        response = await self.client.get(
                            current_url,
                            headers=headers,
                            follow_redirects=False,
                            timeout=self.request_timeout_seconds,
                        )
                        self._last_request = time.monotonic()
                        if not response.is_redirect:
                            break
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("CMS redirect response did not include a location")
                        current_url = urljoin(str(response.url), location)
                        self._validate_url(current_url, expected_host=expected_host)
                    else:
                        raise ValueError("CMS redirect limit exceeded")
                    enforce_http_status(response)
                    self._validate_url(str(response.url), expected_host=expected_host)
                    if len(response.content) > self.MAX_BYTES:
                        raise ValueError(f"Artifact exceeds {self.MAX_BYTES} bytes")
                    return response
                except (SourceAccessDenied, SourceRateLimited, ValueError):
                    raise
                except httpx.HTTPError as exc:
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
            raise ValueError(f"Administrative Enforcement {stage} returned unsupported MIME type: {content_type}")

    @staticmethod
    def _sitemap_from_robots(robots_text: str, branch: EnforcementBranch) -> str:
        matches = re.findall(r"^\s*Sitemap\s*:\s*(\S+)\s*$", robots_text, re.IGNORECASE | re.MULTILINE)
        for raw_url in matches:
            url = urljoin(f"{branch.origin}/robots.txt", raw_url)
            parsed = urlparse(url)
            if parsed.scheme == "https" and parsed.hostname == branch.host:
                return url
        raise ValueError(f"{branch.code}: robots.txt did not declare a same-host HTTPS sitemap")

    def _require_robots_allowed(self, branch: EnforcementBranch, url: str) -> None:
        self._validate_url(url, expected_host=branch.host)
        parser = self._robots_by_host.get(branch.host)
        if parser is None:
            raise SourceAccessDenied(f"{branch.code}: no verified robots policy is loaded for this run")
        if not parser.can_fetch(self.user_agent, url):
            raise SourceAccessDenied(f"{branch.code}: robots.txt disallows {urlparse(url).path}")

    def _check_robots(self, robots_text: str, branch: EnforcementBranch, urls: list[str]) -> str:
        parser = RobotFileParser()
        parser.set_url(f"{branch.origin}/robots.txt")
        parser.parse(robots_text.splitlines())
        self._robots_by_host[branch.host] = parser
        for url in urls:
            self._require_robots_allowed(branch, url)
        return self._sitemap_from_robots(robots_text, branch)

    @staticmethod
    def _validate_sitemap(content: bytes, branch: EnforcementBranch) -> None:
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise ValueError(f"{branch.code}: invalid sitemap XML") from exc
        locations = [clean(node.text) for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "loc"]
        if not any(urlparse(url).scheme == "https" and urlparse(url).hostname == branch.host for url in locations):
            raise ValueError(f"{branch.code}: sitemap contains no same-host HTTPS locations")

    @classmethod
    def _list_priority(cls, label: str) -> int | None:
        if "不動產拍賣" in label and "動產拍賣" not in label.replace("不動產拍賣", ""):
            return None
        for index, marker in enumerate(cls.LIST_LABELS):
            if marker in label:
                return index
        return None

    def _announcement_lists(self, content: bytes, branch: EnforcementBranch) -> list[str]:
        soup = BeautifulSoup(content, "html.parser")
        ranked: list[tuple[int, int, str]] = []
        for position, node in enumerate(soup.select("a[href]")):
            label = clean(f"{node.get('title', '')} {node.get_text(' ', strip=True)}")
            priority = self._list_priority(label)
            if priority is None:
                continue
            url = urljoin(branch.origin, str(node.get("href") or ""))
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname != branch.host:
                continue
            if parsed.path.startswith("/umbraco/surface/") or "/post" in parsed.path:
                continue
            path = parsed.path.removesuffix("Lpsimplelist")
            canonical = urlunsplit(("https", branch.host, path, "", ""))
            ranked.append((priority, position, canonical))
        found: list[str] = []
        for _, _, url in sorted(ranked):
            if url not in found:
                found.append(url)
            if len(found) >= self.MAX_LISTS_PER_BRANCH:
                break
        return found

    @staticmethod
    def _roc_date(value: str) -> datetime | None:
        match = re.search(r"(?P<year>\d{2,3})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})", value)
        if not match:
            return None
        try:
            return datetime(
                int(match.group("year")) + 1911,
                int(match.group("month")),
                int(match.group("day")),
                tzinfo=TAIPEI,
            )
        except ValueError:
            return None

    @classmethod
    def _is_vehicle_auction_title(cls, title: str) -> bool:
        normalized = clean(title)
        return bool(cls.VEHICLE_PATTERN.search(normalized) and cls.AUCTION_PATTERN.search(normalized))

    @staticmethod
    def _page_url(list_url: str, page: int, page_size: int) -> str:
        parsed = urlsplit(list_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update({"Page": str(page), "PageSize": str(page_size), "type": "01"})
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))

    def _items_from_list(
        self,
        content: bytes,
        branch: EnforcementBranch,
        discovery_url: str,
        cutoff: datetime,
    ) -> tuple[list[DiscoveredItem], list[datetime], bool]:
        soup = BeautifulSoup(content, "html.parser")
        items: list[DiscoveredItem] = []
        dates: list[datetime] = []
        for row in soup.select("table.table_list tbody tr"):
            link = row.select_one("td[data-title='標題'] a[href]")
            date_cell = row.select_one("td[data-title*='日期'], td.date")
            if not link or not date_cell:
                continue
            published_at = self._roc_date(date_cell.get_text(" ", strip=True))
            if not published_at:
                self.discovery_warnings.append(
                    f"{branch.code}: skipped one CMS row whose publication date was not an ROC date"
                )
                continue
            dates.append(published_at)
            title = clean(link.get_text(" ", strip=True) or str(link.get("title") or ""))
            if published_at < cutoff or not self._is_vehicle_auction_title(title):
                continue
            official_url = urljoin(discovery_url, str(link.get("href") or ""))
            parsed = urlparse(official_url)
            if parsed.scheme != "https" or parsed.hostname != branch.host or not parsed.path.endswith("/post"):
                self.discovery_warnings.append(f"{branch.code}: skipped a vehicle row without a same-host HTML post")
                continue
            try:
                self._require_robots_allowed(branch, official_url)
            except SourceAccessDenied as exc:
                self.discovery_warnings.append(f"{branch.code}: skipped a robots-disallowed detail: {exc}")
                continue
            content_match = re.search(r"/(\d+)/post/?$", parsed.path)
            record_key = content_match.group(1) if content_match else hashlib.sha256(official_url.encode()).hexdigest()[:24]
            items.append(DiscoveredItem(
                source_record_id=f"{branch.code}-{record_key}",
                official_url=official_url,
                title=title,
                discovery_url=discovery_url,
                metadata={
                    "organization": branch.organization,
                    "branch_code": branch.code,
                    "published_at": published_at.isoformat(),
                    "discovery_method": "BRANCH_CMS_ANNOUNCEMENT_LIST",
                },
            ))
        has_next = bool(soup.select_one("ul.page a[title='下一頁']"))
        return items, dates, has_next

    async def _preflight(self, branch: EnforcementBranch) -> tuple[str, bytes]:
        robots_url = f"{branch.origin}/robots.txt"
        robots = await self._request(robots_url, expected_host=branch.host)
        self._require_mime(robots, {"text/plain", "text/html"}, "robots")
        sitemap_url = self._check_robots(robots.text, branch, [branch.origin + "/"])
        self._require_robots_allowed(branch, sitemap_url)
        sitemap = await self._request(sitemap_url, expected_host=branch.host, referer=robots_url)
        self._require_mime(sitemap, {"application/xml", "text/xml", "text/html"}, "sitemap")
        if len(sitemap.content) > self.MAX_SITEMAP_BYTES:
            raise ValueError(f"{branch.code}: sitemap exceeds {self.MAX_SITEMAP_BYTES} bytes")
        self._validate_sitemap(sitemap.content, branch)
        homepage = await self._request(branch.origin + "/", expected_host=branch.host, referer=sitemap_url)
        self._require_mime(homepage, {"text/html"}, "homepage")
        self._check_robots(robots.text, branch, [sitemap_url, str(homepage.url)])
        return robots.text, homepage.content

    async def _discover_branch(self, branch: EnforcementBranch, cutoff: datetime) -> list[DiscoveredItem]:
        robots_text, homepage = await self._preflight(branch)
        lists = self._announcement_lists(homepage, branch)
        if not lists:
            raise ValueError(f"{branch.code}: no same-host announcement list was published on the homepage")
        found: dict[str, DiscoveredItem] = {}
        checked_lists = 0
        for list_url in lists:
            try:
                self._check_robots(robots_text, branch, [list_url])
                for page in range(1, self.MAX_LIST_PAGES + 1):
                    page_url = self._page_url(list_url, page, self.PAGE_SIZE)
                    self._check_robots(robots_text, branch, [page_url])
                    response = await self._request(page_url, expected_host=branch.host, referer=branch.origin + "/")
                    self._require_mime(response, {"text/html"}, "announcement list")
                    items, dates, has_next = self._items_from_list(response.content, branch, list_url, cutoff)
                    for item in items:
                        found[item.source_record_id] = item
                    checked_lists += page == 1
                    if (dates and min(dates) < cutoff) or not has_next:
                        break
            except Exception as exc:
                self.discovery_warnings.append(f"{branch.code}: announcement list failed closed: {exc}")
        if not checked_lists:
            raise ValueError(f"{branch.code}: no announcement list could be checked")
        return list(found.values())

    async def discover(self) -> list[DiscoveredItem]:
        self.discovery_warnings = []
        self._robots_by_host.clear()
        now = self._now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=TAIPEI)
        cutoff = now.astimezone(TAIPEI) - timedelta(days=self.LOOKBACK_DAYS)
        found: dict[str, DiscoveredItem] = {}
        branches_checked = 0
        for branch in self.branches:
            try:
                async with asyncio.timeout(self.branch_deadline_seconds):
                    branch_items = await self._discover_branch(branch, cutoff)
                for item in branch_items:
                    found[item.source_record_id] = item
                branches_checked += 1
            except TimeoutError:
                self.discovery_warnings.append(
                    f"{branch.code}: branch discovery exceeded {self.branch_deadline_seconds:g} seconds"
                )
            except Exception as exc:
                self.discovery_warnings.append(f"{branch.code}: branch discovery failed closed: {exc}")
        if not branches_checked:
            raise RuntimeError("No Administrative Enforcement branch CMS could be checked safely")
        return sorted(found.values(), key=lambda item: item.source_record_id)

    @classmethod
    def _artifact(cls, response: httpx.Response, fetched_at: datetime) -> RawArtifact:
        content_type = cls._content_type(response)
        if content_type == "application/octet-stream" and response.content.startswith(b"%PDF"):
            content_type = "application/pdf"
        if content_type not in {"text/html", "application/pdf"}:
            raise ValueError(f"Unsupported Administrative Enforcement CMS MIME type: {content_type}")
        filename = unquote(PurePosixPath(urlparse(str(response.url)).path).name) or "enforcement-cms.html"
        return RawArtifact(
            official_url=str(response.url),
            fetched_at=fetched_at,
            mime_type=content_type,
            filename=filename,
            content=response.content,
            http_status=response.status_code,
            http_headers={
                name.lower(): value
                for name, value in response.headers.items()
                if name.lower() in cls.SAFE_ARTIFACT_RESPONSE_HEADERS
            },
            checksum_sha256=hashlib.sha256(response.content).hexdigest(),
        )

    async def fetch(self, item: DiscoveredItem) -> list[RawArtifact]:
        official_url = str(item.official_url)
        host = urlparse(official_url).hostname or ""
        branch = next((candidate for candidate in self.branches if candidate.host == host), None)
        if branch is None:
            raise ValueError("Administrative Enforcement CMS item does not belong to a registered branch")
        self._validate_url(official_url, expected_host=host)
        self._require_robots_allowed(branch, official_url)
        if not urlparse(official_url).path.endswith("/post"):
            raise ValueError("Administrative Enforcement CMS items must use an official HTML post URL")
        fetched_at = datetime.now(UTC)
        primary = await self._request(official_url, expected_host=host, referer=str(item.discovery_url))
        self._require_mime(primary, {"text/html"}, "detail")
        artifacts = [self._artifact(primary, fetched_at)]
        soup = BeautifulSoup(primary.content, "html.parser")
        attachment_urls: list[str] = []
        for node in soup.select(".file_download a[href]"):
            url = urljoin(str(primary.url), str(node.get("href") or ""))
            parsed = urlparse(url)
            label = clean(f"{node.get('title', '')} {node.get_text(' ', strip=True)}").lower()
            is_pdf = parsed.path.lower().endswith(".pdf") or ".pdf" in label
            if parsed.scheme != "https" or parsed.hostname != host or not is_pdf:
                continue
            if url not in attachment_urls:
                attachment_urls.append(url)
        attachment_urls = attachment_urls[: self.MAX_ATTACHMENTS]
        item.metadata["official_attachment_urls"] = attachment_urls
        blocked_attachments: list[str] = []
        for url in attachment_urls:
            try:
                self._require_robots_allowed(branch, url)
            except SourceAccessDenied:
                blocked_attachments.append(url)
                continue
            response = await self._request(url, expected_host=host, referer=official_url)
            artifacts.append(self._artifact(response, fetched_at))
        if blocked_attachments:
            warning = f"{branch.code}: robots.txt blocked {len(blocked_attachments)} official PDF attachment(s); links only"
            self.discovery_warnings.append(warning)
            item.metadata["ingest_partial_failure"] = warning
        return artifacts

    async def parse(self, item: DiscoveredItem, artifacts: list[RawArtifact]) -> ParsedAuctionRecord:
        html = next((artifact for artifact in artifacts if artifact.mime_type == "text/html"), None)
        if not html:
            raise ValueError("Administrative Enforcement CMS detail HTML is missing")
        soup = BeautifulSoup(html.content, "html.parser")
        title_node = soup.select_one("meta[name='ContentTitle'], meta[name='DC.Title']")
        title = clean(str(title_node.get("content") or "")) if title_node else ""
        if not title:
            heading = soup.select_one("h2.title")
            title = clean(heading.get_text(" ", strip=True) if heading else item.title)
        body_node = soup.select_one("section.cp")
        body = clean(body_node.get_text(" ", strip=True) if body_node else "")
        combined = _redact_personal_data(f"{title} {body}")
        if not self._is_vehicle_auction_title(title) and not self._is_vehicle_auction_title(combined):
            raise ValueError("Branch CMS post does not explicitly identify a vehicle auction")

        vehicle_type, vehicle_type_text = vehicle_type_from_official_text(combined)
        car_category, car_category_text = car_category_from_official_text(combined)
        vehicle_class, vehicle_class_text = motorcycle_class_from_official_text(combined)
        brand, model, manufacture_year, manufacture_month, displacement, color, plates = _vehicle_identity(combined)
        plates = _plate_values_for_type(combined, plates, vehicle_type)
        if vehicle_type == VehicleType.UNKNOWN:
            brand = model = None
            manufacture_year = manufacture_month = displacement = None
            color = None
        elif vehicle_type == VehicleType.MIXED:
            brand = model = None
            manufacture_year = manufacture_month = displacement = None
            color = None
        lot_size = max(1, len(plates))
        bulk_lot = (
            vehicle_type in {VehicleType.UNKNOWN, VehicleType.MIXED}
            or lot_size > 1
            or bool(re.search(r"一批|整批|及其他動產", combined))
        )

        creator = soup.select_one("meta[name='DC.Creator']")
        organization = clean(
            str(creator.get("content") or "") if creator else str(item.metadata.get("organization") or "")
        ) or "法務部行政執行署（分署未確認）"
        case_match = re.search(r"(\d{2,3}年度[^。；;]{0,20}?字第[\d、,，至-]+號)", combined)
        case_number = clean(case_match.group(1)) if case_match else None
        auction_at = official_datetime(combined)
        status = (
            AuctionStatus.EXPIRED if auction_at and auction_at < self._now()
            else AuctionStatus.SCHEDULED if auction_at
            else AuctionStatus.ANNOUNCED
        )
        round_match = re.search(r"第\s*(\d+)\s*拍", combined)
        auction_round = int(round_match.group(1)) if round_match else None
        reserve_match = re.search(r"(?:核定)?底價\D{0,8}([\d,]+)", combined)
        reserve_price = integer(reserve_match.group(1)) if reserve_match else None
        location = _label_value(combined, ("拍賣地點", "放置地點", "觀覽地點", "地點"))
        has_key = FourState.NO if "無鑰匙" in combined else FourState.YES if re.search(r"(?:有|附)鑰匙", combined) else FourState.UNKNOWN
        can_start = FourState.NO if re.search(r"(?:無法|不能)發動|發不動", combined) else FourState.YES if re.search(r"(?:可|能)發動", combined) else FourState.UNKNOWN
        can_test = FourState.NO if re.search(r"(?:無法|不可|不得)測試", combined) else FourState.YES if re.search(r"可測試", combined) else FourState.UNKNOWN
        if re.search(r"不得再領牌|不可再領牌|僅供報廢", combined):
            registration = RegistrationStatus.SCRAP_ONLY
        elif re.search(r"繳銷重領|重新領牌|讓渡重領牌照", combined):
            registration = RegistrationStatus.RE_REGISTRATION_REQUIRED
        elif re.search(r"得辦理移轉過戶|可辦理移轉過戶", combined):
            registration = RegistrationStatus.NORMAL_TRANSFER
        else:
            registration = RegistrationStatus.UNKNOWN
        recycler_only = bool(re.search(r"廢機動車輛回收|合格回收商|回收業資格", combined))
        eligibility = BidEligibility.LICENSED_RECYCLER_ONLY if recycler_only else BidEligibility.UNKNOWN
        identifiers = [
            VehicleIdentifier(
                identifier_type="PLATE",
                normalized_value=normalize_identifier(plate),
                original_value=plate,
            )
            for plate in plates
        ]
        units = [
            ParsedVehicleUnit(source_vehicle_key=f"plate:{identifier.normalized_value}", identifiers=[identifier])
            for identifier in identifiers
        ] if len(identifiers) > 1 else []
        pdf_count = sum(artifact.mime_type == "application/pdf" for artifact in artifacts)
        evidence: list[EvidenceRef] = [
            EvidenceRef(
                field_name="official_title",
                normalized_value=title,
                source_text=title,
                extraction_method="HTML",
                trust="OFFICIAL_EXPLICIT",
            )
        ]
        for attachment_url in item.metadata.get("official_attachment_urls", []):
            evidence.append(EvidenceRef(
                field_name="official_attachment_url",
                normalized_value=str(attachment_url),
                source_text="官方 PDF 附件",
                extraction_method="HTML",
                trust="OFFICIAL_EXPLICIT",
            ))
        for field_name, normalized, source in (
            ("vehicle_type", vehicle_type.value, vehicle_type_text or ("車輛" if "車輛" in combined else None)),
            ("vehicle_class", vehicle_class.value, vehicle_class_text),
            ("car_category", car_category.value, car_category_text),
            ("registration_status", registration.value, _explicit_fact_sentence(combined, r"領牌|過戶|報廢")),
            ("has_key", has_key.value, _explicit_fact_sentence(combined, r"鑰匙")),
        ):
            if source:
                evidence.append(EvidenceRef(
                    field_name=field_name,
                    normalized_value=normalized,
                    source_text=source,
                    extraction_method="HTML",
                    trust="OFFICIAL_EXPLICIT",
                ))
        completeness, groups = _completeness_groups({
            "identity": [plates, brand, model, vehicle_type],
            "auction": [organization, auction_at, reserve_price, status, eligibility],
            "condition": [has_key, can_start, can_test, body],
            "registration": [registration, plates, FourState.UNKNOWN],
            "fees": [None, None, None],
            "media": [["official-pdf"] if pdf_count or item.metadata.get("official_attachment_urls") else []],
        })
        return ParsedAuctionRecord(
            source_record_id=item.source_record_id,
            official_url=item.official_url,
            official_title=title,
            official_case_number=case_number,
            organization=organization,
            disposal_origin="ADMINISTRATIVE_ENFORCEMENT",
            status=status,
            auction_round=auction_round,
            ends_at=auction_at,
            reserve_price=reserve_price,
            title=title,
            lot_size=lot_size,
            bulk_lot=bulk_lot,
            eligibility=eligibility,
            location=location,
            description=body or None,
            brand=brand,
            model=model,
            manufacture_year=manufacture_year,
            manufacture_month=manufacture_month,
            displacement_cc=displacement,
            vehicle_type=vehicle_type,
            vehicle_class=vehicle_class,
            car_category=car_category,
            color=color,
            has_key=has_key,
            can_start=can_start,
            can_test=can_test,
            registration_status=registration,
            condition_summary=_explicit_fact_sentence(combined, r"車況|刮傷|損壞|漏油|發動|鑰匙"),
            identifiers=identifiers,
            vehicle_units=units,
            photo_urls=[],
            evidence=evidence,
            completeness=completeness,
            completeness_groups=groups,
        )

    async def healthcheck(self) -> SourceHealth:
        started = time.monotonic()
        warnings: list[str] = []
        healthy = 0
        for branch in self.branches:
            try:
                async with asyncio.timeout(self.branch_deadline_seconds):
                    await self._preflight(branch)
                healthy += 1
            except TimeoutError:
                warnings.append(f"{branch.code}: preflight exceeded {self.branch_deadline_seconds:g} seconds")
            except Exception as exc:
                warnings.append(f"{branch.code}: {exc}")
        status = "ACTIVE" if healthy == len(self.branches) else "PARTIAL" if healthy else "DEGRADED"
        return SourceHealth(
            source="moj_enforcement_cms",
            status=status,
            checked_at=datetime.now(UTC),
            response_ms=round((time.monotonic() - started) * 1000),
            message=f"{healthy}/{len(self.branches)} branch CMS preflights succeeded; centralized CAPTCHA search was not used",
            warnings=warnings,
        )
