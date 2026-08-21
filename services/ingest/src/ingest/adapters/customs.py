from __future__ import annotations

import asyncio
import hashlib
import re
import time
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import parse_qs, unquote, urljoin, urlparse

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
    FourState,
    ParsedAuctionRecord,
    RawArtifact,
    RegistrationStatus,
    SourceHealth,
    VehicleClass,
    VehicleIdentifier,
    VehicleType,
)
from ingest.parser import (
    car_category_from_official_text,
    clean,
    integer,
    motorcycle_class_from_official_text,
    normalize_identifier,
    official_datetime,
    vehicle_type_from_official_text,
)


class CustomsAuctionAdapter(SourceAdapter):
    """HTML-only discovery for the four official Taiwan Customs auction lists.

    The Customs robots policy excludes ``/download/``.  This adapter therefore
    preserves attachment URLs as field evidence but never requests their bytes.
    Vehicle notices whose identity exists only inside an attachment remain an
    explicit coverage gap instead of being guessed from a generic auction title.
    """

    ORIGIN = "https://web.customs.gov.tw"
    OVERVIEW_URL = f"{ORIGIN}/singlehtml/1207?cntId=cus1_93228_1207"
    OFFICE_LISTS = {
        "keelung": ("財政部關務署基隆關", f"{ORIGIN}/keelung/multiplehtml/572"),
        "taipei": ("財政部關務署臺北關", f"{ORIGIN}/taipei/multiplehtml/120"),
        "taichung": ("財政部關務署臺中關", f"{ORIGIN}/taichung/multiplehtml/396"),
        "kaohsiung": ("財政部關務署高雄關", f"{ORIGIN}/kaohsiung/multiplehtml/541"),
    }
    ALLOWED_HOSTS = {"web.customs.gov.tw"}
    BLOCKED_PATH_PREFIXES = ("/download/",)
    MAX_BYTES = 5 * 1024 * 1024
    MAX_LIST_PAGES_PER_OFFICE = 5
    MAX_CANDIDATES_PER_PAGE = 20
    MAX_REDIRECTS = 5
    VEHICLE_TERMS = (
        "機車",
        "機器腳踏車",
        "重機",
        "汽車",
        "小客車",
        "大客車",
        "小貨車",
        "大貨車",
        "客貨兩用車",
        "休旅車",
        "轎車",
        "廂型車",
        "貨車",
        "公務車",
        "車輛",
    )

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        request_interval: float = 1.0,
        *,
        overview_url: str | None = None,
        office_lists: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        self.client = client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(25),
            headers={"User-Agent": contact_user_agent("0.5")},
        )
        self._owns_client = client is None
        self.request_interval = request_interval
        self.overview_url = overview_url or self.OVERVIEW_URL
        self.office_lists = office_lists or self.OFFICE_LISTS
        self._last_request = 0.0
        self._request_lock = asyncio.Lock()
        self._detail_artifacts: dict[str, RawArtifact] = {}
        self._discovery_warnings: list[str] = []

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        path = unquote(parsed.path).lower()
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self.ALLOWED_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
        ):
            raise ValueError(f"Blocked non-registered source URL: {url}")
        if any(path.startswith(prefix) for prefix in self.BLOCKED_PATH_PREFIXES):
            raise ValueError(f"Blocked by Customs robots policy: {url}")

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
                    for _ in range(self.MAX_REDIRECTS + 1):
                        response = await self.client.get(current_url, follow_redirects=False)
                        self._last_request = time.monotonic()
                        if not response.is_redirect:
                            break
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("Customs redirect response did not include a location")
                        current_url = urljoin(str(response.url), location)
                        self._validate_url(current_url)
                    else:
                        raise ValueError("Customs redirect limit exceeded")
                    enforce_http_status(response)
                    self._validate_url(str(response.url))
                    if len(response.content) > self.MAX_BYTES:
                        raise ValueError(f"Artifact exceeds {self.MAX_BYTES} bytes")
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/html" not in content_type:
                        raise ValueError(f"Customs HTML endpoint returned an unexpected MIME type: {content_type}")
                    return response
                except (SourceAccessDenied, SourceRateLimited, ValueError):
                    raise
                except httpx.HTTPError as exc:
                    last_error = exc
            if attempt < 2:
                await asyncio.sleep(2**attempt)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _artifact(response: httpx.Response) -> RawArtifact:
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "text/html":
            raise ValueError(f"Unexpected Customs artifact MIME type: {content_type}")
        content = response.content
        return RawArtifact(
            official_url=str(response.url),
            fetched_at=datetime.now(UTC),
            mime_type=content_type,
            filename=PurePosixPath(urlparse(str(response.url)).path).name or "customs-auction.html",
            content=content,
            http_status=response.status_code,
            http_headers={
                key: value
                for key, value in response.headers.items()
                if key.lower() in {"etag", "last-modified", "content-type", "content-length"}
            },
            checksum_sha256=hashlib.sha256(content).hexdigest(),
        )

    @staticmethod
    def _detail_path(list_url: str) -> str:
        return urlparse(list_url).path.replace("/multiplehtml/", "/singlehtml/")

    @classmethod
    def _list_page_urls(cls, html: bytes, current_url: str, seed_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        seed = urlparse(seed_url)
        urls: set[str] = set()
        for link in soup.select("a[href]"):
            label = clean(link.get_text(" ", strip=True))
            if not (label.isdigit() or label in {"下一頁", "最後一頁"}):
                continue
            target = urljoin(current_url, link.get("href", ""))
            parsed = urlparse(target)
            if parsed.scheme == "https" and parsed.hostname in cls.ALLOWED_HOSTS and parsed.path == seed.path:
                urls.add(target)
        return sorted(urls)

    @classmethod
    def _listing_candidates(
        cls,
        html: bytes,
        *,
        office_slug: str,
        organization: str,
        list_url: str,
        current_url: str,
    ) -> list[DiscoveredItem]:
        soup = BeautifulSoup(html, "html.parser")
        detail_path = cls._detail_path(list_url)
        found: dict[str, DiscoveredItem] = {}
        rows = soup.select("table tbody tr") or soup.select("table tr")
        for row in rows[: cls.MAX_CANDIDATES_PER_PAGE]:
            link = row.select_one("a[href*='cntId=']")
            if not link:
                continue
            target = urljoin(current_url, link.get("href", ""))
            parsed = urlparse(target)
            identifiers = parse_qs(parsed.query).get("cntId", [])
            if parsed.scheme != "https" or parsed.hostname not in cls.ALLOWED_HOSTS:
                continue
            if parsed.path != detail_path or len(identifiers) != 1 or not identifiers[0]:
                continue
            title = clean(link.get_text(" ", strip=True))
            if not title:
                continue
            row_text = clean(row.get_text(" ", strip=True))
            published = re.search(r"(?:\d{4}-\d{1,2}-\d{1,2}|\d{2,3}-\d{1,2}-\d{1,2})", row_text)
            record_id = f"{office_slug}-{identifiers[0]}"
            found[record_id] = DiscoveredItem(
                source_record_id=record_id,
                official_url=target,
                title=title,
                discovery_url=list_url,
                metadata={
                    "office": office_slug,
                    "organization": organization,
                    "published_date": published.group(0) if published else "",
                },
            )
        return list(found.values())

    @staticmethod
    def _article_scope(soup: BeautifulSoup) -> Tag | BeautifulSoup:
        selectors = (
            "main article",
            "article",
            "section.cp",
            "div.cp",
            ".content_detail",
            ".article-content",
        )
        candidates = [node for selector in selectors for node in soup.select(selector)]
        if candidates:
            return max(candidates, key=lambda node: len(clean(node.get_text(" ", strip=True))))
        main = soup.select_one("main")
        return main if isinstance(main, Tag) else soup

    @classmethod
    def _official_text(cls, item: DiscoveredItem, content: bytes) -> tuple[str, Tag | BeautifulSoup]:
        soup = BeautifulSoup(content, "html.parser")
        scope = cls._article_scope(soup)
        return clean(f"{item.title} {scope.get_text(' ', strip=True)}"), scope

    @staticmethod
    def _generic_vehicle_evidence(text: str) -> str | None:
        patterns = (
            r"(?:標售|拍賣|變賣|標的物|沒入|報廢).{0,20}(?:車輛|公務車)",
            r"(?:車輛|公務車).{0,20}(?:標售|拍賣|變賣|報廢)",
            r"(?:車輛|公務車)\s*\d+\s*輛",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match and "車輛通行證" not in match.group(0):
                return clean(match.group(0))
        return None

    @classmethod
    def _is_vehicle_notice(cls, item: DiscoveredItem, content: bytes) -> bool:
        text, _ = cls._official_text(item, content)
        typed, _ = vehicle_type_from_official_text(text)
        return typed != VehicleType.UNKNOWN or cls._generic_vehicle_evidence(text) is not None

    async def discover(self) -> list[DiscoveredItem]:
        self._detail_artifacts.clear()
        self._discovery_warnings.clear()
        overview = await self._request(self.overview_url)
        if "海關私貨拍賣" not in overview.text or not all(name in overview.text for name in ("基隆關", "臺北關", "臺中關", "高雄關")):
            raise ValueError("Customs auction overview structure changed")

        candidates: dict[str, DiscoveredItem] = {}
        for office_slug, (organization, seed_url) in self.office_lists.items():
            queue = [seed_url]
            seen: set[str] = set()
            while queue and len(seen) < self.MAX_LIST_PAGES_PER_OFFICE:
                page_url = queue.pop(0)
                if page_url in seen:
                    continue
                seen.add(page_url)
                response = await self._request(page_url)
                if "標售" not in response.text:
                    raise ValueError(f"Customs auction list structure changed for {office_slug}")
                for item in self._listing_candidates(
                    response.content,
                    office_slug=office_slug,
                    organization=organization,
                    list_url=seed_url,
                    current_url=str(response.url),
                ):
                    candidates[item.source_record_id] = item
                for target in self._list_page_urls(response.content, str(response.url), seed_url):
                    if target not in seen and target not in queue:
                        queue.append(target)

        found: dict[str, DiscoveredItem] = {}
        for item in candidates.values():
            try:
                response = await self._request(str(item.official_url))
            except (SourceAccessDenied, SourceRateLimited):
                raise
            except Exception as exc:
                self._discovery_warnings.append(f"{item.source_record_id}: {exc}")
                continue
            artifact = self._artifact(response)
            if not self._is_vehicle_notice(item, artifact.content):
                continue
            self._detail_artifacts[item.source_record_id] = artifact
            found[item.source_record_id] = item
        return sorted(found.values(), key=lambda item: item.source_record_id)

    async def fetch(self, item: DiscoveredItem) -> list[RawArtifact]:
        cached = self._detail_artifacts.get(item.source_record_id)
        if cached:
            return [cached]
        response = await self._request(str(item.official_url))
        artifact = self._artifact(response)
        if not self._is_vehicle_notice(item, artifact.content):
            raise ValueError("Customs notice does not explicitly identify a vehicle in allowed HTML")
        return [artifact]

    @staticmethod
    def _sentence(text: str, pattern: str) -> str | None:
        return next((clean(value) for value in re.split(r"[。；;\n]", text) if re.search(pattern, value)), None)

    @staticmethod
    def _label_value(text: str, labels: tuple[str, ...]) -> str | None:
        for label in labels:
            match = re.search(rf"{re.escape(label)}\s*[：:]\s*([^，,、；;。\n]+)", text)
            if match:
                return clean(match.group(1))
        return None

    @staticmethod
    def _attachment_evidence(scope: Tag | BeautifulSoup, base_url: str) -> list[EvidenceRef]:
        evidence: list[EvidenceRef] = []
        seen: set[str] = set()
        for link in scope.select("a[href]"):
            target = urljoin(base_url, link.get("href", ""))
            parsed = urlparse(target)
            if parsed.scheme != "https" or parsed.hostname != "web.customs.gov.tw":
                continue
            if not unquote(parsed.path).lower().startswith("/download/") or target in seen:
                continue
            seen.add(target)
            label = clean(link.get_text(" ", strip=True)) or "官方附件"
            evidence.append(
                EvidenceRef(
                    field_name="official_attachment_url",
                    normalized_value=target,
                    source_text=label,
                    extraction_method="HTML_LINK",
                    trust="OFFICIAL_EXPLICIT",
                )
            )
        return evidence

    @staticmethod
    def _vehicle_identity(text: str) -> tuple[str | None, str | None, int | None, int | None, list[str]]:
        def value_for(labels: tuple[str, ...]) -> str | None:
            for label in labels:
                match = re.search(rf"{re.escape(label)}\s*[：:]\s*([^，,、；;。\n]+)", text)
                if match:
                    return clean(match.group(1))
            return None

        brand = value_for(("廠牌名稱", "廠牌"))
        model = value_for(("型號", "型式", "車型"))
        displacement = integer(value_for(("排氣量", "汽缸容量")))
        manufacture = value_for(("出廠年月", "出廠日期", "出廠年份", "年份", "製造年月"))
        manufacture_year: int | None = None
        if manufacture:
            match = re.search(r"(\d{2,4})", manufacture)
            if match:
                raw_year = int(match.group(1))
                manufacture_year = raw_year + 1911 if raw_year < 1911 else raw_year
        plates: list[str] = []
        for match in re.finditer(r"(?<![A-Z0-9])([A-Z0-9]{2,4}[-－][A-Z0-9]{2,4})(?![A-Z0-9])", text, re.IGNORECASE):
            plate = match.group(1).replace("－", "-").upper()
            if plate not in plates:
                plates.append(plate)
        return brand, model, manufacture_year, displacement, plates

    async def parse(self, item: DiscoveredItem, artifacts: list[RawArtifact]) -> ParsedAuctionRecord:
        html = next((artifact for artifact in artifacts if artifact.mime_type == "text/html"), None)
        if not html:
            raise ValueError("Customs detail HTML is missing")
        combined, scope = self._official_text(item, html.content)
        vehicle_type, vehicle_type_text = vehicle_type_from_official_text(combined)
        generic_vehicle = self._generic_vehicle_evidence(combined)
        if vehicle_type == VehicleType.UNKNOWN and generic_vehicle is None:
            raise ValueError("Customs notice does not explicitly identify a vehicle in allowed HTML")

        organization = clean(str(item.metadata.get("organization") or "")) or "財政部關務署（關別未確認）"
        vehicle_class, vehicle_class_text = motorcycle_class_from_official_text(combined)
        car_category, car_category_text = car_category_from_official_text(combined)
        case_sentence = self._sentence(combined, r"(?:發文字號|標號|案號)\s*[：:]")
        case_match = re.search(r"(?:發文字號|標號|案號)\s*[：:]\s*([^，,；;。\s]+)", case_sentence or "")
        case_number = clean(case_match.group(1)) if case_match else None
        auction_sentence = self._sentence(combined, r"(?:開標日期|開標時間|開標日期及時間|開標日期及地點)")
        auction_at = official_datetime(auction_sentence or "")

        if re.search(r"不予開標|取消標售|停止標售", combined):
            status = AuctionStatus.CANCELLED
        elif re.search(r"(?:得標結果|決標結果|已售出|已拍定|拍定金額|得標金額|決標金額|得標價款)", combined):
            status = AuctionStatus.SOLD
        elif auction_at and auction_at < datetime.now(auction_at.tzinfo):
            status = AuctionStatus.EXPIRED
        elif auction_at:
            status = AuctionStatus.SCHEDULED
        else:
            status = AuctionStatus.ANNOUNCED

        reserve_match = re.search(r"(?:標售底價|底價)\D{0,8}([\d,]+)", combined)
        deposit_match = re.search(r"(?:保證金|押標金)\D{0,8}([\d,]+)", combined)
        reserve_price = integer(reserve_match.group(1)) if reserve_match else None
        deposit = integer(deposit_match.group(1)) if deposit_match else None
        location_sentence = self._sentence(combined, r"(?:開標地點|看貨地點|存放地點)")
        location = self._label_value(location_sentence or "", ("開標地點", "看貨地點", "存放地點"))
        brand, model, manufacture_year, displacement, plates = self._vehicle_identity(combined)
        identifiers = [
            VehicleIdentifier(
                identifier_type="PLATE",
                normalized_value=normalize_identifier(plate),
                original_value=plate,
            )
            for plate in plates
        ]
        counts = [int(value) for value in re.findall(r"(\d+)\s*輛", combined)]
        lot_size = max(counts) if counts else max(1, len(plates))
        bulk_lot = lot_size > 1 or vehicle_type == VehicleType.MIXED

        if re.search(r"限退運出口|不得提領進口", combined):
            registration = RegistrationStatus.EXPORT_ONLY
        elif re.search(r"不辦理登檢領照|不得(?:再)?領牌", combined):
            registration = RegistrationStatus.CANNOT_RELICENSE
        elif re.search(r"檢測合格.{0,20}(?:登檢|領照)", combined):
            registration = RegistrationStatus.INSPECTION_REQUIRED
        elif re.search(r"僅供報廢|報廢車", combined):
            registration = RegistrationStatus.SCRAP_ONLY
        else:
            registration = RegistrationStatus.UNKNOWN

        if re.search(r"(?:限具有|主管機關.{0,8}許可|輸入許可文件)", combined):
            eligibility = BidEligibility.SPECIAL_QUALIFICATION
        elif re.search(r"(?:個人|國民身分證)", combined):
            eligibility = BidEligibility.NATURAL_PERSON_ALLOWED
        else:
            eligibility = BidEligibility.UNKNOWN

        evidence: list[EvidenceRef] = [
            EvidenceRef(field_name="title", normalized_value=item.title, source_text=item.title),
            EvidenceRef(field_name="organization", normalized_value=organization, source_text=organization),
        ]
        for field_name, normalized, source in (
            ("official_case_number", case_number, case_sentence),
            ("ends_at", auction_at.isoformat() if auction_at else None, auction_sentence),
            ("vehicle_type", vehicle_type.value, vehicle_type_text or generic_vehicle),
            ("vehicle_class", vehicle_class.value, vehicle_class_text),
            ("car_category", car_category.value, car_category_text),
            ("location", location, location_sentence),
        ):
            if source:
                evidence.append(EvidenceRef(field_name=field_name, normalized_value=normalized, source_text=source))
        evidence.extend(self._attachment_evidence(scope, str(item.official_url)))

        attachment_count = sum(entry.field_name == "official_attachment_url" for entry in evidence)
        identity_present = sum(value is not None and value != [] for value in (plates, brand, model, vehicle_type if vehicle_type != VehicleType.UNKNOWN else None))
        auction_present = sum(value is not None for value in (organization, auction_at, reserve_price, status, eligibility if eligibility != BidEligibility.UNKNOWN else None))
        completeness_groups = {
            "identity": round(identity_present / 4 * 100),
            "auction": round(auction_present / 5 * 100),
            "condition": 0,
            "registration": 100 if registration != RegistrationStatus.UNKNOWN else 0,
            "fees": 50 if deposit is not None else 0,
            "media": 50 if attachment_count else 0,
        }
        completeness = round(
            completeness_groups["identity"] * 0.2
            + completeness_groups["auction"] * 0.25
            + completeness_groups["condition"] * 0.15
            + completeness_groups["registration"] * 0.2
            + completeness_groups["fees"] * 0.1
            + completeness_groups["media"] * 0.1
        )

        return ParsedAuctionRecord(
            source_record_id=item.source_record_id,
            official_url=item.official_url,
            official_title=item.title,
            official_case_number=case_number,
            organization=organization,
            disposal_origin="CUSTOMS_FORFEITURE",
            status=status,
            ends_at=auction_at,
            reserve_price=reserve_price,
            deposit=deposit,
            title=item.title,
            lot_size=lot_size,
            bulk_lot=bulk_lot,
            eligibility=eligibility,
            location=location,
            description=clean(scope.get_text(" ", strip=True)) or None,
            brand=brand,
            model=model,
            manufacture_year=manufacture_year,
            displacement_cc=displacement,
            vehicle_type=vehicle_type,
            vehicle_class=vehicle_class,
            car_category=car_category,
            has_key=FourState.UNKNOWN,
            can_start=FourState.UNKNOWN,
            can_test=FourState.UNKNOWN,
            registration_status=registration,
            identifiers=identifiers,
            evidence=evidence,
            completeness=completeness,
            completeness_groups=completeness_groups,
        )

    async def healthcheck(self) -> SourceHealth:
        started = time.monotonic()
        warnings: list[str] = []
        try:
            overview = await self._request(self.overview_url)
            if "海關私貨拍賣" not in overview.text:
                warnings.append("四關總覽的預期標記不存在")
            for office_slug, (_, list_url) in self.office_lists.items():
                response = await self._request(list_url)
                if "標售" not in response.text:
                    warnings.append(f"{office_slug} 公告清單的預期標記不存在")
            warnings.extend(self._discovery_warnings)
            return SourceHealth(
                source="customs",
                status="PARTIAL" if not warnings else "DEGRADED",
                checked_at=datetime.now(UTC),
                response_ms=round((time.monotonic() - started) * 1000),
                message=(
                    "四關官方 HTML 公告可讀；/download/ 附件依來源政策僅保留連結"
                    if not warnings
                    else "部分海關公告結構無法確認"
                ),
                warnings=warnings or ["附件內容未自動下載；附件內才出現的車輛可能尚未被辨識"],
            )
        except Exception as exc:
            return SourceHealth(
                source="customs",
                status="DEGRADED",
                checked_at=datetime.now(UTC),
                response_ms=round((time.monotonic() - started) * 1000),
                message="海關標售公告健康檢查失敗",
                warnings=[str(exc)],
            )
