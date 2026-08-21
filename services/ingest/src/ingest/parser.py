from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ingest.models import (
    AuctionStatus,
    BidEligibility,
    CarCategory,
    DiscoveredItem,
    EvidenceRef,
    FourState,
    ParsedAuctionRecord,
    ParsedVehicleUnit,
    RawArtifact,
    RegistrationStatus,
    VehicleClass,
    VehicleIdentifier,
    VehicleType,
)

TAIPEI = ZoneInfo("Asia/Taipei")


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def roc_datetime(value: str) -> datetime | None:
    match = re.search(r"(?P<year>\d{2,3})/(?P<month>\d{1,2})/(?P<day>\d{1,2})(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?)?", value)
    if not match:
        return None
    parts = {key: int(number) if number else 0 for key, number in match.groupdict().items()}
    year = parts["year"] + 1911 if parts["year"] < 1911 else parts["year"]
    return datetime(year, parts["month"], parts["day"], parts["hour"], parts["minute"], parts["second"], tzinfo=TAIPEI)


def roc_compact_date(value: str) -> datetime | None:
    """Parse Judicial Yuan dates such as 1150819 without inventing a time."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) not in {6, 7}:
        return None
    year_digits = len(digits) - 4
    try:
        return datetime(int(digits[:year_digits]) + 1911, int(digits[year_digits:year_digits + 2]), int(digits[-2:]), tzinfo=TAIPEI)
    except ValueError:
        return None


def integer(value: str | None) -> int | None:
    if not value:
        return None
    unit_values = {"億": 100_000_000, "萬": 10_000, "千": 1_000, "百": 100, "十": 10}
    unit_parts = re.findall(r"([\d,]+)\s*([億萬千百十])", value)
    if unit_parts:
        total = sum(int(number.replace(",", "")) * unit_values[unit] for number, unit in unit_parts)
        suffix = re.search(r"[億萬千百十]\s*([\d,]+)(?!\s*[億萬千百十])", value)
        if suffix:
            total += int(suffix.group(1).replace(",", ""))
        return total
    match = re.search(r"([\d,]+)", value)
    return int(match.group(1).replace(",", "")) if match else None


def normalize_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper().replace("－", "-"))


def motorcycle_class_from_official_text(value: str) -> tuple[VehicleClass, str | None]:
    """Classify only from explicit official wording; displacement is not proof."""
    normalized = clean(value)
    patterns = (
        (VehicleClass.ELECTRIC_MOTORCYCLE, r"(?:普通輕型|普通重型|大型重型)?電動機車"),
        (VehicleClass.LARGE_HEAVY, r"大型重型機車|大型重機"),
        (VehicleClass.ORDINARY_HEAVY, r"普通重型機車"),
        (VehicleClass.ORDINARY_LIGHT, r"普通輕型機車"),
        (VehicleClass.HEAVY_UNSPECIFIED, r"重型機車"),
    )
    for vehicle_class, pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return vehicle_class, match.group(0)
    return VehicleClass.UNKNOWN, None


MOTORCYCLE_PATTERN = re.compile(
    r"普通輕型機車|普通重型機車|大型重型機車|大型重機|電動機車|重型機車|機器腳踏車|機車|重機"
)
CAR_PATTERN = re.compile(
    r"自用小客車|營業小客車|小客車|大客車|自用小貨車|營業小貨車|小貨車|大貨車|客貨兩用車|休旅車|轎車|廂型車|貨車|汽車"
)


def vehicle_type_from_official_text(value: str) -> tuple[VehicleType, str | None]:
    """Classify the advertised lot without treating fuel-fee boilerplate as a car."""
    normalized = clean(value)
    without_fuel_boilerplate = re.sub(r"汽車燃料(?:使用)?費", "燃料費", normalized)
    combined_vehicle = re.search(r"汽(?:、|及|與|和)?機車", without_fuel_boilerplate)
    if combined_vehicle:
        return VehicleType.MIXED, combined_vehicle.group(0)
    motorcycle = MOTORCYCLE_PATTERN.search(without_fuel_boilerplate)
    car = CAR_PATTERN.search(without_fuel_boilerplate)
    if motorcycle and car:
        return VehicleType.MIXED, f"{motorcycle.group(0)}、{car.group(0)}"
    if motorcycle:
        return VehicleType.MOTORCYCLE, motorcycle.group(0)
    if car:
        return VehicleType.CAR, car.group(0)
    return VehicleType.UNKNOWN, None


def car_category_from_official_text(value: str) -> tuple[CarCategory, str | None]:
    normalized = clean(value)
    patterns = (
        (CarCategory.SUV, r"休旅車|運動型多用途車|SUV"),
        (CarCategory.VAN, r"廂型車|客貨兩用車"),
        (CarCategory.TRUCK, r"(?:自用|營業)?(?:小貨|大貨)車|貨車|曳引車"),
        (CarCategory.BUS, r"大客車|遊覽車|公車"),
        (CarCategory.PASSENGER, r"轎車|自用小客車|營業小客車|小客車"),
    )
    for category, pattern in patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            return category, match.group(0)
    if vehicle_type_from_official_text(normalized)[0] == VehicleType.CAR:
        return CarCategory.OTHER, "汽車"
    return CarCategory.UNKNOWN, None


def _field_lines(soup: BeautifulSoup) -> dict[str, str]:
    labels = {
        "已購置年限", "廠牌", "型號", "零件或附件", "牌照異動登記", "原牌照種類", "物品說明",
    }
    fields: dict[str, str] = {}
    for text in soup.stripped_strings:
        value = clean(text)
        for label in labels:
            if value.startswith(f"{label}："):
                fields[label] = clean(value.split("：", 1)[1])
    return fields


def _table_fields(soup: BeautifulSoup) -> dict[str, str]:
    values: dict[str, str] = {}
    for row in soup.select("tr"):
        cells = [clean(cell.get_text(" ", strip=True)) for cell in row.select("th,td")]
        if len(cells) >= 2 and cells[0]:
            values[cells[0]] = cells[1]
    return values


def _evidence(
    field_name: str,
    normalized_value: object,
    source_text: str,
    table_row: str | None = None,
    trust: str = "OFFICIAL_EXPLICIT",
    extraction_method: str = "HTML",
) -> EvidenceRef:
    return EvidenceRef(
        field_name=field_name,
        normalized_value=normalized_value,
        source_text=clean(source_text),
        table_row=table_row,
        trust=trust,
        extraction_method=extraction_method,
    )


def _paired_table_fields(soup: BeautifulSoup) -> dict[str, str]:
    """Read key/value pairs from rows that may contain two field pairs."""
    values: dict[str, str] = {}
    for row in soup.select("tr"):
        cells = [clean(cell.get_text(" ", strip=True)) for cell in row.select("th,td")]
        for index in range(0, len(cells) - 1, 2):
            if cells[index]:
                values[cells[index]] = cells[index + 1]
    return values


def _completeness_groups(group_values: dict[str, list[object]]) -> tuple[int, dict[str, int]]:
    unknowns = {FourState.UNKNOWN, RegistrationStatus.UNKNOWN, BidEligibility.UNKNOWN}

    def is_present(value: object) -> bool:
        if value is None or value == "" or value == []:
            return False
        return not isinstance(value, (FourState, RegistrationStatus, BidEligibility)) or value not in unknowns

    groups = {
        name: round(sum(is_present(value) for value in values) / len(values) * 100)
        for name, values in group_values.items()
    }
    weights = {"identity": .2, "auction": .25, "condition": .15, "registration": .2, "fees": .1, "media": .1}
    return round(sum(groups[name] * weight for name, weight in weights.items())), groups


def _structured_evidence(field_name: str, normalized_value: object, source_text: object, key: str, trust: str = "OFFICIAL_EXPLICIT") -> EvidenceRef:
    return _evidence(field_name, normalized_value, str(source_text), key, trust, "STRUCTURED")


def _label_value(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[：:]\s*([^，,、；;。\n]+)", text, re.IGNORECASE)
        if match:
            return clean(match.group(1))
    return None


def official_datetime(value: str) -> datetime | None:
    slash_date = roc_datetime(value)
    if slash_date:
        return slash_date
    match = re.search(
        r"(?:中華民國)?(?P<year>\d{2,4})\s*年\s*(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日"
        r"(?:[^上下\d]{0,8}(?P<period>上午|下午)?\s*(?P<hour>\d{1,2})?\s*時?\s*(?P<minute>\d{1,2})?\s*分?)?",
        value,
    )
    if not match:
        return None
    year = int(match.group("year"))
    year = year + 1911 if year < 1911 else year
    hour = int(match.group("hour") or 0)
    if match.group("period") == "下午" and hour < 12:
        hour += 12
    if match.group("period") == "上午" and hour == 12:
        hour = 0
    try:
        return datetime(year, int(match.group("month")), int(match.group("day")), hour, int(match.group("minute") or 0), tzinfo=TAIPEI)
    except ValueError:
        return None


def _redact_personal_data(value: str) -> str:
    redacted = re.sub(r"(?<![A-Z0-9])[A-Z][12]\d{8}(?!\d)", "[已移除身分證字號]", value, flags=re.IGNORECASE)
    redacted = re.sub(r"(義務人|所有人|車主)\s*[：:]?\s*[\u4e00-\u9fff○ＯO]{2,4}", r"\1：[已移除姓名]", redacted)
    return clean(redacted)


def _vehicle_identity(text: str) -> tuple[str | None, str | None, int | None, int | None, int | None, str | None, list[str]]:
    brand_raw = _label_value(text, ("廠牌名稱", "廠牌", "廠商"))
    brand_aliases = {"光陽": "KYMCO", "三陽": "SYM", "山葉": "YAMAHA", "台灣山葉": "YAMAHA"}
    if not brand_raw:
        brand_raw = next((alias for alias in ("台灣山葉", "光陽", "三陽", "山葉", "KYMCO", "SYM", "YAMAHA", "HONDA", "SUZUKI", "PGO", "GOGORO", "PIAGGIO") if alias in text.upper()), None)
    brand = brand_aliases.get(brand_raw or "", brand_raw)
    model = _label_value(text, ("型號", "型式", "車型"))
    displacement = integer(_label_value(text, ("排氣量", "汽缸容量")))
    manufacture = _label_value(text, ("出廠年月", "出廠日期", "出廠年份", "年份", "製造年月"))
    manufacture_year = None
    manufacture_month = None
    if manufacture:
        date_match = re.search(r"(\d{2,4})\D*(\d{1,2})?", manufacture)
        if date_match:
            raw_year = int(date_match.group(1))
            manufacture_year = raw_year + 1911 if raw_year < 1911 else raw_year
            manufacture_month = int(date_match.group(2)) if date_match.group(2) else None
    color = _label_value(text, ("顏色", "車色"))
    plates: list[str] = []
    for match in re.finditer(r"(?<![A-Z0-9])([A-Z0-9]{2,4}[-－][A-Z0-9]{2,4})(?![A-Z0-9])", text, re.IGNORECASE):
        value = match.group(1).replace("－", "-").upper()
        nearby_label = text[max(0, match.start() - 16):match.start()]
        # Numeric date fragments look like legacy plate formats. Retain an
        # all-numeric value only when official text labels it as a plate.
        if not re.search(r"[A-Z]", value, re.IGNORECASE) and not re.search(r"(?:車牌|牌照)(?:號碼)?\s*[：:]?\s*$", nearby_label):
            continue
        if value not in plates:
            plates.append(value)
    return brand, model, manufacture_year, manufacture_month, displacement, color, plates


def _plate_values_for_type(text: str, plates: list[str], vehicle_type: VehicleType) -> list[str]:
    """Keep plates nearest the selected vehicle family in mixed announcements."""
    if vehicle_type in {VehicleType.MIXED, VehicleType.UNKNOWN}:
        return plates
    motorcycle_types = [(match.start(), match.end(), VehicleType.MOTORCYCLE) for match in MOTORCYCLE_PATTERN.finditer(text)]
    car_types = [(match.start(), match.end(), VehicleType.CAR) for match in CAR_PATTERN.finditer(text)]
    if vehicle_type == VehicleType.MOTORCYCLE and not car_types:
        return plates
    if vehicle_type == VehicleType.CAR and not motorcycle_types:
        return plates
    type_mentions = motorcycle_types + car_types
    selected: list[str] = []
    for plate in plates:
        plate_pattern = re.compile(re.escape(plate).replace(r"\-", r"[-－]"), re.IGNORECASE)
        target_context = False
        for plate_match in plate_pattern.finditer(text):
            nearby: list[tuple[int, VehicleType]] = []
            for start, end, mentioned_type in type_mentions:
                distance = start - plate_match.end() if start >= plate_match.end() else plate_match.start() - end if end <= plate_match.start() else 0
                if 0 <= distance <= 100:
                    nearby.append((distance, mentioned_type))
            if nearby and min(nearby, key=lambda value: value[0])[1] == vehicle_type:
                target_context = True
                break
        if target_context:
            selected.append(plate)
    return selected


def _motorcycle_plate_values(text: str, plates: list[str]) -> list[str]:
    """Backward-compatible helper for existing parser tests."""
    return _plate_values_for_type(text, plates, VehicleType.MOTORCYCLE)


def _artifact_photo_urls(artifacts: list[RawArtifact]) -> list[str]:
    return list(dict.fromkeys(str(artifact.official_url) for artifact in artifacts if artifact.mime_type.startswith("image/")))


def _explicit_fact_sentence(text: str, pattern: str) -> str | None:
    return next((clean(sentence) for sentence in re.split(r"[。；;\n]", text) if re.search(pattern, sentence)), None)


def parse_moj_auction_detail(item: DiscoveredItem, artifacts: list[RawArtifact]) -> ParsedAuctionRecord:
    """Parse the MOJ centralized seized-property page without inventing PDF-only facts."""
    html = next((artifact for artifact in artifacts if artifact.mime_type == "text/html"), None)
    soup = BeautifulSoup(html.content, "html.parser") if html else BeautifulSoup("", "html.parser")
    title_node = soup.select_one("h2.title")
    central_row = soup.select_one("tr") if not title_node else None
    central_link = central_row.select_one("td[data-title='標題'] a[href]") if central_row else None
    title = clean(
        title_node.get_text(" ", strip=True)
        if title_node else central_link.get_text(" ", strip=True)
        if central_link else item.title
    )
    body_node = soup.select_one("section.cp")
    body = clean(body_node.get_text(" ", strip=True) if body_node else "")
    combined = _redact_personal_data(f"{title} {body}")
    vehicle_type, vehicle_type_text = vehicle_type_from_official_text(combined)
    if vehicle_type == VehicleType.UNKNOWN:
        raise ValueError("MOJ record does not explicitly identify a car or motorcycle")
    car_category, car_category_text = car_category_from_official_text(combined)

    organization_meta = soup.select_one("meta[name='DC.Creator']")
    central_cells = {
        cell.get("data-title"): clean(cell.get_text(" ", strip=True))
        for cell in central_row.select("td[data-title]")
    } if central_row else {}
    organization = clean(
        organization_meta.get("content", "")
        if organization_meta else central_cells.get("單位") or str(item.metadata.get("organization") or "")
    ) or "未辨識檢察機關"
    case_match = re.search(r"(\d{2,3}年度(?:變價|執沒|扣押物|偵)字第[\d、,，至-]+號)", combined)
    official_case_number = clean(case_match.group(1)) if case_match else None
    auction_sentence = _explicit_fact_sentence(combined, r"拍賣(?:時間|日期)") or combined
    auction_at = official_datetime(auction_sentence)
    explicit_sold = bool(re.search(r"(已拍賣完畢|拍定(?:金額|價格|日期)|以新臺幣[\d,]+元拍定)", combined))
    status = AuctionStatus.SOLD if explicit_sold else AuctionStatus.EXPIRED if auction_at and auction_at < datetime.now(TAIPEI) else AuctionStatus.SCHEDULED if auction_at else AuctionStatus.ANNOUNCED
    round_match = re.search(r"第\s*(\d+)\s*(?:次|拍)", combined)
    auction_round = int(round_match.group(1)) if round_match else None
    reserve_match = re.search(r"(?:核定)?底價\D{0,8}([\d,]+)", combined)
    sold_match = re.search(r"(?:拍定金額|拍定價格|成交價)\D{0,8}([\d,]+)", combined)
    reserve_price = integer(reserve_match.group(1)) if reserve_match else None
    sold_price = integer(sold_match.group(1)) if sold_match else None
    location = _label_value(combined, ("拍賣地點", "放置地點", "觀覽地點"))
    vehicle_class, vehicle_class_text = motorcycle_class_from_official_text(combined)
    brand, model, manufacture_year, manufacture_month, displacement, color, all_plates = _vehicle_identity(combined)
    plates = _plate_values_for_type(combined, all_plates, vehicle_type)
    vehicle_noun = r"(?:機車|重機|機器腳踏車|汽車|小客車|大客車|小貨車|大貨車|客貨兩用車|休旅車|轎車|廂型車|貨車)"
    count_values = [int(value) for value in re.findall(rf"{vehicle_noun}\s*(\d+)\s*[臺台輛部]", combined)]
    if not count_values:
        count_values = [int(value) for value in re.findall(rf"(\d+)\s*[臺台輛部][^。]{{0,12}}{vehicle_noun}", combined)]
    lot_size = sum(count_values) if vehicle_type == VehicleType.MIXED and count_values else count_values[0] if count_values else max(1, len(plates))
    bulk_lot = lot_size > 1 or vehicle_type == VehicleType.MIXED or bool(re.search(rf"{vehicle_noun}[^。]{{0,8}}(?:一批|整批)", combined))
    if vehicle_type == VehicleType.MIXED:
        brand = model = None
        manufacture_year = manufacture_month = displacement = None
        vehicle_class = VehicleClass.UNKNOWN
        car_category = CarCategory.UNKNOWN

    recycler = bool(re.search(r"(廢機動車輛回收|合格回收商|回收業資格)", combined))
    eligibility = BidEligibility.LICENSED_RECYCLER_ONLY if recycler else BidEligibility.NATURAL_PERSON_ALLOWED if re.search(r"(國民身分證|有意承購者|到場競買)", combined) else BidEligibility.UNKNOWN
    if re.search(r"(不得再領牌|不可再領牌|僅供報廢)", combined):
        registration = RegistrationStatus.SCRAP_ONLY
    elif "可再領牌" in combined or "重新領牌" in combined:
        registration = RegistrationStatus.RE_REGISTRATION_REQUIRED
    elif re.search(r"(得辦理移轉過戶|可辦理移轉過戶)", combined):
        registration = RegistrationStatus.NORMAL_TRANSFER
    else:
        registration = RegistrationStatus.UNKNOWN
    has_key = FourState.NO if "無鑰匙" in combined else FourState.YES if "有鑰匙" in combined else FourState.UNKNOWN
    can_start = FourState.NO if re.search(r"(無法發動|不能發動|發不動)", combined) else FourState.YES if re.search(r"(可發動|能發動)", combined) else FourState.UNKNOWN
    can_test = FourState.NO if re.search(r"(無法測試|不可測試|不得測試)", combined) else FourState.YES if re.search(r"(可測試|提供.{0,8}測試)", combined) else FourState.UNKNOWN
    identifiers = [VehicleIdentifier(identifier_type="PLATE", normalized_value=normalize_identifier(plate), original_value=plate) for plate in plates]
    units = [ParsedVehicleUnit(source_vehicle_key=f"plate:{normalize_identifier(plate)}", identifiers=[identifier]) for plate, identifier in zip(plates, identifiers, strict=True)] if len(plates) > 1 else []
    photo_urls = _artifact_photo_urls(artifacts)

    evidence: list[EvidenceRef] = []
    for field_name, normalized, source in (
        ("title", title, title),
        ("official_case_number", official_case_number, official_case_number),
        ("organization", organization, organization),
        ("ends_at", auction_at.isoformat() if auction_at else None, auction_sentence if auction_at else None),
        ("vehicle_type", vehicle_type.value, vehicle_type_text),
        ("vehicle_class", vehicle_class.value, vehicle_class_text),
        ("car_category", car_category.value, car_category_text),
        ("registration_status", registration.value, _explicit_fact_sentence(combined, r"(領牌|過戶|報廢)")),
        ("eligibility", eligibility.value, _explicit_fact_sentence(combined, r"(身分證|承購|競買|回收商)")),
    ):
        if source:
            evidence.append(_evidence(field_name, normalized, source))
    completeness, groups = _completeness_groups({
        "identity": [plates, brand, model, vehicle_type],
        "auction": [organization, auction_at, reserve_price, status, eligibility],
        "condition": [has_key, can_start, can_test, body],
        "registration": [registration, plates, FourState.UNKNOWN],
        "fees": [None, None, None],
        "media": [photo_urls or [artifact for artifact in artifacts if artifact.mime_type == "application/pdf"]],
    })
    return ParsedAuctionRecord(
        source_record_id=item.source_record_id, official_url=item.official_url, official_title=title,
        official_case_number=official_case_number, organization=organization,
        disposal_origin="CRIMINAL_SEIZURE_OR_FORFEITURE", status=status, auction_round=auction_round,
        ends_at=auction_at, reserve_price=reserve_price, sold_price=sold_price, title=title,
        lot_size=lot_size, bulk_lot=bulk_lot, eligibility=eligibility, location=location,
        description=body or None, brand=brand, model=model, manufacture_year=manufacture_year,
        manufacture_month=manufacture_month, displacement_cc=displacement, vehicle_type=vehicle_type,
        vehicle_class=vehicle_class, car_category=car_category,
        color=color, has_key=has_key, can_start=can_start, can_test=can_test,
        registration_status=registration, condition_summary=_explicit_fact_sentence(combined, r"(車況|刮傷|損壞|發動|鑰匙)"),
        identifiers=identifiers, vehicle_units=units, photo_urls=photo_urls, evidence=evidence,
        completeness=completeness, completeness_groups=groups,
    )


def parse_moj_enforcement_detail(item: DiscoveredItem, artifacts: list[RawArtifact]) -> ParsedAuctionRecord:
    """Parse a human-selected official Administrative Enforcement detail URL."""
    html = next((artifact for artifact in artifacts if artifact.mime_type == "text/html"), None)
    if not html:
        raise ValueError("Administrative Enforcement detail HTML is missing")
    soup = BeautifulSoup(html.content, "html.parser")
    heading = soup.find("div", class_="title_h3", string=re.compile("公告事項"))
    notice = heading.find_next("ul") if heading else None
    lines = [clean(node.get_text(" ", strip=True)) for node in notice.select("li")] if notice else []
    combined = _redact_personal_data(" ".join(lines))
    vehicle_type, vehicle_type_text = vehicle_type_from_official_text(combined)
    if vehicle_type == VehicleType.UNKNOWN:
        raise ValueError("Administrative Enforcement manifest item is not explicitly a car or motorcycle")
    car_category, car_category_text = car_category_from_official_text(combined)
    case_match = re.search(r"案號[：:]\s*([A-Z0-9-]+)", combined, re.IGNORECASE)
    official_case_number = case_match.group(1) if case_match else item.source_record_id
    date_match = re.search(r"開標日[：:]\s*([\d/]+(?:\s+[\d:]+)?)", combined)
    auction_at = official_datetime(date_match.group(1)) if date_match else None
    description = next((line for line in lines if not line.startswith(("案號", "開標日"))), item.title)
    title = clean(item.title if item.title and item.title != item.source_record_id else description[:120])
    organization = clean(str(item.metadata.get("organization") or "")) or "法務部行政執行署（分署未確認）"
    vehicle_class, vehicle_class_text = motorcycle_class_from_official_text(combined)
    brand, model, manufacture_year, manufacture_month, displacement, color, all_plates = _vehicle_identity(combined)
    plates = _plate_values_for_type(combined, all_plates, vehicle_type)
    mileage_match = re.search(r"(?:里程數|里程|儀表板?所示里程數)[：:]?\s*([\d,]+)\s*(?:km|公里)?", combined, re.IGNORECASE)
    mileage = integer(mileage_match.group(1)) if mileage_match else None
    vehicle_noun = r"(?:機車|重機|機器腳踏車|汽車|小客車|大客車|小貨車|大貨車|客貨兩用車|休旅車|轎車|廂型車|貨車)"
    lot_match = re.search(rf"{vehicle_noun}\s*(\d+)\s*[臺台輛部]", combined) or re.search(rf"(\d+)\s*[臺台輛部][^。]{{0,12}}{vehicle_noun}", combined)
    lot_size = int(lot_match.group(1)) if lot_match else max(1, len(plates))
    bulk_lot = lot_size > 1 or vehicle_type == VehicleType.MIXED or bool(re.search(rf"{vehicle_noun}[^。]{{0,8}}(?:一批|整批)", combined))
    if vehicle_type == VehicleType.MIXED:
        brand = model = None
        manufacture_year = manufacture_month = displacement = None
        vehicle_class = VehicleClass.UNKNOWN
        car_category = CarCategory.UNKNOWN
    round_match = re.search(r"第\s*(\d+)\s*拍", combined)
    auction_round = int(round_match.group(1)) if round_match else int(item.metadata["auction_round"]) if item.metadata.get("auction_round") else None
    sold_match = re.search(r"(?:拍定金額|拍定價格)\D{0,8}([\d,]+)", combined)
    sold_price = integer(sold_match.group(1)) if sold_match else None
    reserve_match = re.search(r"(?:核定)?底價\D{0,8}([\d,]+)", combined)
    reserve_price = integer(reserve_match.group(1)) if reserve_match else None
    status = AuctionStatus.SOLD if sold_price is not None or "已拍定" in combined else AuctionStatus.EXPIRED if auction_at and auction_at < datetime.now(TAIPEI) else AuctionStatus.SCHEDULED if auction_at else AuctionStatus.ANNOUNCED
    recycler = bool(re.search(r"(廢機動車輛回收|合格回收商|回收業資格)", combined))
    eligibility = BidEligibility.LICENSED_RECYCLER_ONLY if recycler else BidEligibility.UNKNOWN
    if re.search(r"(不得再領牌|不可再領牌|僅供報廢)", combined):
        registration = RegistrationStatus.SCRAP_ONLY
    elif re.search(r"(繳銷重領|重新領牌|讓渡重領牌照)", combined):
        registration = RegistrationStatus.RE_REGISTRATION_REQUIRED
    elif re.search(r"(得辦理移轉過戶|可辦理移轉過戶|本區新領)", combined):
        registration = RegistrationStatus.NORMAL_TRANSFER
    else:
        registration = RegistrationStatus.UNKNOWN
    has_key = FourState.NO if "無鑰匙" in combined else FourState.YES if re.search(r"(有鑰匙|附鑰匙)", combined) else FourState.UNKNOWN
    can_start = FourState.NO if re.search(r"(無法發動|不能發動|發不動)", combined) else FourState.YES if re.search(r"(可發動|能發動)", combined) else FourState.UNKNOWN
    can_test = FourState.NO if re.search(r"(無法測試|不可測試|不得測試)", combined) else FourState.YES if re.search(r"(可測試|提供.{0,8}測試)", combined) else FourState.UNKNOWN
    location = _label_value(combined, ("拍賣地點", "放置地點", "觀覽地點", "地點"))
    fee_notes = [sentence for sentence in (_explicit_fact_sentence(combined, r"(欠稅|燃料費|養護費|罰鍰|鑑定費)"),) if sentence]
    identifiers = [VehicleIdentifier(identifier_type="PLATE", normalized_value=normalize_identifier(plate), original_value=plate) for plate in plates]
    units = [ParsedVehicleUnit(source_vehicle_key=f"plate:{normalize_identifier(plate)}", identifiers=[identifier]) for plate, identifier in zip(plates, identifiers, strict=True)] if len(plates) > 1 else []
    photo_urls = _artifact_photo_urls(artifacts)
    evidence: list[EvidenceRef] = []
    for field_name, normalized, source in (
        ("official_case_number", official_case_number, case_match.group(0) if case_match else None),
        ("ends_at", auction_at.isoformat() if auction_at else None, date_match.group(0) if date_match else None),
        ("vehicle_type", vehicle_type.value, vehicle_type_text),
        ("vehicle_class", vehicle_class.value, vehicle_class_text),
        ("car_category", car_category.value, car_category_text),
        ("registration_status", registration.value, _explicit_fact_sentence(combined, r"(領牌|過戶|報廢|牌照狀態)")),
        ("has_key", has_key.value, _explicit_fact_sentence(combined, r"鑰匙")),
    ):
        if source:
            evidence.append(_evidence(field_name, normalized, source))
    completeness, groups = _completeness_groups({
        "identity": [plates, brand, model, vehicle_type],
        "auction": [organization, auction_at, reserve_price, status, eligibility],
        "condition": [has_key, can_start, can_test, description],
        "registration": [registration, plates, FourState.UNKNOWN],
        "fees": [fee_notes, None, None],
        "media": [photo_urls],
    })
    return ParsedAuctionRecord(
        source_record_id=item.source_record_id, official_url=item.official_url, official_title=title,
        official_case_number=official_case_number, organization=organization,
        disposal_origin="ADMINISTRATIVE_ENFORCEMENT", status=status, auction_round=auction_round,
        ends_at=auction_at, reserve_price=reserve_price, sold_price=sold_price, fee_notes=fee_notes,
        title=title, lot_size=lot_size, bulk_lot=bulk_lot, eligibility=eligibility, location=location,
        description=description, brand=brand, model=model, manufacture_year=manufacture_year,
        manufacture_month=manufacture_month, displacement_cc=displacement, vehicle_type=vehicle_type,
        vehicle_class=vehicle_class, car_category=car_category,
        color=color, mileage_km=mileage, has_key=has_key, can_start=can_start, can_test=can_test,
        registration_status=registration, condition_summary=_explicit_fact_sentence(combined, r"(車況|刮傷|漏油|發動|鑰匙)"),
        identifiers=identifiers, vehicle_units=units, photo_urls=photo_urls, evidence=evidence,
        completeness=completeness, completeness_groups=groups,
    )


def parse_judicial_record(item: DiscoveredItem, artifact: RawArtifact) -> ParsedAuctionRecord:
    """Parse one official Judicial Yuan movable-property result row.

    The result API is authoritative structured evidence. The accompanying PDF is
    preserved separately even when its prose is not required for normalization.
    """
    row = json.loads(artifact.content)
    if not isinstance(row, dict):
        raise ValueError("Judicial artifact must contain one result object")

    title = clean(str(row.get("ttitle") or item.title))
    notes = clean(str(row.get("notes") or ""))
    organization = clean(str(row.get("crtnm") or "未辨識法院"))
    sale_date = official_datetime(str(row.get("sale_time") or "")) or roc_compact_date(str(row.get("saledate") or ""))
    status = AuctionStatus.EXPIRED if sale_date and sale_date.date() < datetime.now(TAIPEI).date() else AuctionStatus.SCHEDULED
    auction_round = integer(str(row.get("saleno") or ""))
    quantity = integer(str(row.get("qty") or "")) or 1

    case_number = clean(str(row.get("crm") or ""))
    if not case_number:
        case_year = clean(str(row.get("crmyy") or ""))
        case_type = clean(str(row.get("crmid") or ""))
        case_serial = clean(str(row.get("crmno") or ""))
        case_number = f"{case_year}{case_type}字第{case_serial}號" if case_year and case_type and case_serial else ""

    identity_text = clean(" ".join((str(row.get("registeno") or ""), title, notes))).upper()
    vehicle_type, vehicle_type_text = vehicle_type_from_official_text(identity_text)
    car_category, car_category_text = car_category_from_official_text(identity_text)
    vehicle_class, vehicle_class_text = motorcycle_class_from_official_text(f"{title} {notes}")
    plates = list(dict.fromkeys(
        match.group(1).replace("－", "-")
        for match in re.finditer(r"(?<![A-Z0-9])([A-Z0-9]{2,4}[-－][A-Z0-9]{2,4})(?![A-Z0-9])", identity_text)
    ))
    plate = plates[0] if plates else None
    brand_raw = _label_value(notes, ("廠牌", "廠牌名稱"))
    brand_aliases = {"光陽": "KYMCO", "三陽": "SYM", "山葉": "YAMAHA", "台灣山葉": "YAMAHA"}
    if not brand_raw:
        brand_raw = next((alias for alias in ("台灣山葉", "光陽", "三陽", "山葉") if alias in f"{title} {notes}"), None)
    brand = brand_aliases.get(brand_raw or "", brand_raw)
    model = _label_value(notes, ("型式", "型號", "車型"))
    displacement_text = _label_value(notes, ("排氣量(馬力)", "排氣量（馬力）", "排氣量", "汽缸容量"))
    displacement = integer(displacement_text)
    color = _label_value(notes, ("顏色", "車色"))
    mileage = integer(_label_value(notes, ("里程數", "里程")))
    location = clean(str(row.get("location") or "")) or _label_value(notes, ("物品所在地", "拍賣地點"))
    has_key = FourState.NO if re.search(r"(?:無|沒有)\s*(?:機車)?鑰匙|(?:機車)?鑰匙(?:未交付|未扣得)", notes) else FourState.YES if re.search(r"(?:有|附)\s*(?:機車)?鑰匙", notes) else FourState.UNKNOWN
    can_start = FourState.NO if re.search(r"(?:無法|不能)(?:發動|啟動)|發不動", notes) else FourState.YES if re.search(r"(?:可|能)(?:發動|啟動)", notes) else FourState.UNKNOWN
    can_test = FourState.NO if re.search(r"(?:無法|不能|不得)測試", notes) else FourState.YES if re.search(r"(?:可|能)測試", notes) else FourState.UNKNOWN
    engine = _label_value(notes, ("引擎號碼", "引擎號", "引擎"))
    frame = _label_value(notes, ("車身號碼", "車架號碼", "車台號碼"))
    manufacture = _label_value(notes, ("出廠年月", "製造年月"))
    manufacture_year: int | None = None
    manufacture_month: int | None = None
    if manufacture:
        manufacture_match = re.search(r"(\d{2,4})\D+(\d{1,2})", manufacture)
        if not manufacture_match:
            manufacture_match = re.search(r"^(\d{4})(\d{2})$", re.sub(r"\D", "", manufacture))
        if manufacture_match:
            raw_year = int(manufacture_match.group(1))
            manufacture_year = raw_year + 1911 if raw_year < 1911 else raw_year
            manufacture_month = int(manufacture_match.group(2))

    identifiers: list[VehicleIdentifier] = [
        VehicleIdentifier(identifier_type="PLATE", normalized_value=normalize_identifier(value), original_value=value)
        for value in plates
    ]
    for kind, value in (("ENGINE", engine), ("FRAME", frame)):
        if value:
            identifiers.append(VehicleIdentifier(identifier_type=kind, normalized_value=normalize_identifier(value), original_value=value))
    vehicle_units = [
        ParsedVehicleUnit(source_vehicle_key=f"plate:{normalize_identifier(value)}", identifiers=[identifier])
        for value, identifier in zip(plates, identifiers[:len(plates)], strict=True)
    ] if len(plates) > 1 else []

    reserve_raw = integer(str(row.get("sumprice") or ""))
    reserve_price = reserve_raw if reserve_raw and reserve_raw > 0 else None
    deposit = integer(str(row.get("deposit") or ""))
    raw_fee_notes = row.get("fee_notes")
    if isinstance(raw_fee_notes, list):
        fee_notes = [clean(str(value)) for value in raw_fee_notes if clean(str(value))]
    elif raw_fee_notes:
        fee_notes = [clean(str(raw_fee_notes))]
    else:
        fee_notes = []
    official_url = str(item.official_url)
    evidence: list[EvidenceRef] = []
    for field_name, normalized, source_value, key in [
        ("official_case_number", case_number or None, case_number, "crm"),
        ("organization", organization, row.get("crtnm"), "crtnm"),
        ("ends_at", sale_date.date().isoformat() if sale_date else None, row.get("saledate"), "saledate"),
        ("auction_round", auction_round, row.get("saleno"), "saleno"),
        ("lot_size", quantity, row.get("qty"), "qty"),
        ("reserve_price", reserve_price, row.get("sumprice"), "sumprice"),
        ("deposit", deposit, row.get("deposit"), "deposit"),
        ("title", title, row.get("ttitle"), "ttitle"),
    ]:
        if source_value not in (None, ""):
            trust = "OFFICIAL_INFERRED" if field_name == "reserve_price" and reserve_price is None else "OFFICIAL_EXPLICIT"
            evidence.append(_structured_evidence(field_name, normalized, source_value, key, trust))
    evidence.append(_structured_evidence("disposal_origin", "JUDICIAL_EXECUTION", organization, "crtnm", "OFFICIAL_INFERRED"))
    for field_name, normalized, source_value in [
        ("plate", "、".join(plates) or None, "、".join(plates) or None), ("brand", brand, brand_raw), ("model", model, model),
        ("manufacture_year", manufacture_year, manufacture), ("displacement_cc", displacement, displacement_text),
        ("color", color, color), ("mileage_km", mileage, mileage), ("location", location, location),
        ("has_key", has_key.value, _explicit_fact_sentence(notes, r"鑰匙")),
        ("can_start", can_start.value, _explicit_fact_sentence(notes, r"(?:發動|啟動)")),
        ("can_test", can_test.value, _explicit_fact_sentence(notes, r"測試")),
        ("engine", engine, engine), ("frame", frame, frame),
    ]:
        if source_value:
            evidence.append(_structured_evidence(field_name, normalized, source_value, "notes"))
    if vehicle_class_text:
        evidence.append(_structured_evidence("vehicle_class", vehicle_class.value, vehicle_class_text, "ttitle/notes"))
    if vehicle_type_text:
        evidence.append(_structured_evidence("vehicle_type", vehicle_type.value, vehicle_type_text, "ttitle/notes"))
    if car_category_text:
        evidence.append(_structured_evidence("car_category", car_category.value, car_category_text, "ttitle/notes"))

    if vehicle_type == VehicleType.MIXED:
        brand = model = None
        manufacture_year = manufacture_month = displacement = None
        vehicle_class = VehicleClass.UNKNOWN
        car_category = CarCategory.UNKNOWN

    completeness, groups = _completeness_groups({
        "identity": [plates, brand, model, case_number],
        "auction": [organization, sale_date, auction_round, reserve_price, status],
        "condition": [has_key, can_start, can_test, notes],
        "registration": [RegistrationStatus.UNKNOWN, plate, FourState.UNKNOWN],
        "fees": [deposit, fee_notes, None],
        "media": [integer(str(item.metadata.get("pic_cnt") or "")) or None],
    })
    bulk_lot = quantity > 1
    return ParsedAuctionRecord(
        source_record_id=item.source_record_id,
        official_url=official_url,
        official_title=title,
        official_case_number=case_number or None,
        organization=organization,
        disposal_origin="JUDICIAL_EXECUTION",
        status=status,
        auction_round=auction_round,
        ends_at=sale_date,
        reserve_price=reserve_price,
        deposit=deposit,
        fee_notes=fee_notes,
        title=title,
        lot_size=quantity,
        bulk_lot=bulk_lot,
        eligibility=BidEligibility.UNKNOWN,
        description=notes or None,
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
        location=location,
        has_key=has_key,
        can_start=can_start,
        can_test=can_test,
        registration_status=RegistrationStatus.UNKNOWN,
        condition_summary=notes or None,
        identifiers=identifiers,
        vehicle_units=vehicle_units,
        evidence=evidence,
        completeness=completeness,
        completeness_groups=groups,
    )


def parse_pcc_detail(item: DiscoveredItem, artifact: RawArtifact) -> ParsedAuctionRecord:
    """Parse an official Government e-Procurement asset-sale detail page."""
    soup = BeautifulSoup(artifact.content, "html.parser")
    table = _paired_table_fields(soup)
    title = table.get("財物名稱") or item.title
    organization = table.get("機關名稱", "未辨識機關")
    qualification = table.get("投標資格摘要", "")
    additional = table.get("附加說明", "")
    combined = clean(" ".join(filter(None, [title, qualification, additional])))
    vehicle_type, vehicle_type_text = vehicle_type_from_official_text(combined)
    car_category, car_category_text = car_category_from_official_text(combined)
    vehicle_class, vehicle_class_text = motorcycle_class_from_official_text(combined)

    starts_at = roc_datetime(table.get("公告日期", ""))
    ends_at = roc_datetime(table.get("截止投標", ""))
    status = AuctionStatus.EXPIRED if ends_at and ends_at < datetime.now(TAIPEI) else AuctionStatus.SCHEDULED
    reserve_price = integer(table.get("底價金額"))
    deposit_text = table.get("保證金額度", "")
    deposit = 0 if "免收保證金" in deposit_text else integer(deposit_text)

    recycler_terms = bool(re.search(r"(廢機動車輛回收|廢棄物回收|回收清除機構|回收業資格)", qualification))
    business_terms = bool(re.search(r"(公司或商業登記|投標人應為依法設立之公司|營業稅納稅證明)", qualification))
    if recycler_terms:
        eligibility = BidEligibility.LICENSED_RECYCLER_ONLY
    elif business_terms:
        eligibility = BidEligibility.BUSINESS_ONLY
    elif qualification:
        eligibility = BidEligibility.SPECIAL_QUALIFICATION
    else:
        eligibility = BidEligibility.UNKNOWN

    explicit_scrap = bool(re.search(r"(僅能依廢棄物處理|不得再領牌|不可再領牌)", combined))
    inferred_scrap = bool(re.search(r"(?:報廢|廢)(?:汽(?:、|及|與|和)?機車|汽車|機車|機動車輛|車輛)", combined))
    if "可再領牌" in combined:
        registration = RegistrationStatus.RE_REGISTRATION_REQUIRED
    elif explicit_scrap or inferred_scrap:
        registration = RegistrationStatus.SCRAP_ONLY
    else:
        registration = RegistrationStatus.REGISTRABILITY_UNKNOWN

    if re.search(r"(交通違規移置|逾期未領回|移置保管)", combined):
        disposal_origin = "IMPOUNDED_UNCLAIMED"
    elif re.search(r"(扣押|沒收|沒入|贓物)", combined):
        disposal_origin = "CRIMINAL_SEIZURE_OR_FORFEITURE"
    elif "海關" in organization:
        disposal_origin = "CUSTOMS_FORFEITURE"
    elif explicit_scrap or inferred_scrap:
        disposal_origin = "SCRAP_DISPOSAL"
    else:
        disposal_origin = "PUBLIC_ASSET_DISPOSAL"

    normalized_title = title.replace("⾞", "車")
    vehicle_noun = r"(?:汽車|機車|小客車|大客車|小貨車|大貨車|客貨兩用車|休旅車|轎車|廂型車|貨車)"
    count_match = re.search(rf"{vehicle_noun}\s*(\d+)\s*[輛台部]", normalized_title)
    if not count_match:
        count_match = re.search(rf"(\d+)\s*[輛台部][^，。]{{0,8}}{vehicle_noun}", normalized_title)
    vehicle_count = int(count_match.group(1)) if count_match else None
    lot_size = vehicle_count or 1
    bulk_lot = vehicle_count != 1

    fee_notes = [deposit_text] if deposit_text else []
    location = table.get("變賣標的所在地") or table.get("開標地點") or table.get("機關地址")
    description = clean(" ".join(filter(None, [qualification, table.get("現場查看時間"), additional]))) or None

    evidence: list[EvidenceRef] = []
    for field_name, value, source in [
        ("organization", organization, table.get("機關名稱")),
        ("official_case_number", table.get("標案案號"), table.get("標案案號")),
        ("auction_round", integer(table.get("公告次數")), table.get("公告次數")),
        ("starts_at", starts_at.isoformat() if starts_at else None, table.get("公告日期")),
        ("ends_at", ends_at.isoformat() if ends_at else None, table.get("截止投標")),
        ("reserve_price", reserve_price, table.get("底價金額")),
        ("deposit", deposit, deposit_text),
        ("eligibility", eligibility.value, qualification),
        ("location", location, location),
    ]:
        if source:
            evidence.append(_evidence(field_name, value, source, field_name))
    if explicit_scrap:
        evidence.append(_evidence("registration_status", registration.value, additional or title, "附加說明"))
    elif inferred_scrap:
        evidence.append(_evidence("registration_status", registration.value, title, "財物名稱", "OFFICIAL_INFERRED"))
    evidence.append(_evidence("disposal_origin", disposal_origin, title, "財物名稱", "OFFICIAL_INFERRED"))
    if vehicle_count is not None:
        evidence.append(_evidence("lot_size", vehicle_count, count_match.group(0), "財物名稱"))
    if vehicle_class_text:
        evidence.append(_evidence("vehicle_class", vehicle_class.value, vehicle_class_text, "財物名稱／附加說明"))
    if vehicle_type_text:
        evidence.append(_evidence("vehicle_type", vehicle_type.value, vehicle_type_text, "財物名稱／附加說明"))
    if car_category_text:
        evidence.append(_evidence("car_category", car_category.value, car_category_text, "財物名稱／附加說明"))

    completeness, groups = _completeness_groups({
        "identity": [table.get("標案案號"), vehicle_count],
        "auction": [organization, ends_at, reserve_price, status, eligibility],
        "condition": [FourState.UNKNOWN, FourState.UNKNOWN, FourState.UNKNOWN, additional],
        "registration": [registration, None, FourState.UNKNOWN],
        "fees": [deposit, None, None],
        "media": [None],
    })

    return ParsedAuctionRecord(
        source_record_id=item.source_record_id,
        official_url=item.official_url,
        official_title=title,
        official_case_number=table.get("標案案號"),
        organization=organization,
        disposal_origin=disposal_origin,
        status=status,
        auction_round=integer(table.get("公告次數")),
        starts_at=starts_at,
        ends_at=ends_at,
        reserve_price=reserve_price,
        deposit=deposit,
        fee_notes=fee_notes,
        title=title,
        lot_size=lot_size,
        bulk_lot=bulk_lot,
        eligibility=eligibility,
        location=location,
        description=description,
        vehicle_type=vehicle_type,
        vehicle_class=vehicle_class,
        car_category=car_category,
        registration_status=registration,
        condition_summary=additional or None,
        evidence=evidence,
        completeness=completeness,
        completeness_groups=groups,
    )


def parse_shwoo_detail(item: DiscoveredItem, artifact: RawArtifact) -> ParsedAuctionRecord:
    soup = BeautifulSoup(artifact.content, "html.parser")
    full_text = clean(soup.get_text("\n", strip=True))
    table = _table_fields(soup)
    fields = _field_lines(soup)

    heading = clean((soup.find("strong") or soup.find("h1") or soup.title).get_text(" ", strip=True))
    case_match = re.search(r"[【\[](?P<case>[^】\]]+)[】\]](?P<title>.+)", heading)
    official_case = case_match.group("case") if case_match else None
    title = clean(case_match.group("title") if case_match else table.get("物品名稱") or item.title)

    dates = table.get("拍賣開始與截止日", "")
    date_parts = dates.split("~", 1)
    starts_at = roc_datetime(date_parts[0]) if date_parts else None
    ends_at = roc_datetime(date_parts[1]) if len(date_parts) > 1 else None

    reserve_text = table.get("底價")
    reserve_price = integer(reserve_text)
    current_match = re.search(r"目前出價\s*([\d,]+)\s*元", full_text)
    sold_match = re.search(r"得標金額\s*([\d,]+)\s*元", full_text)
    current_price = integer(current_match.group(1)) if current_match else None
    sold_price = integer(sold_match.group(1)) if sold_match else None
    deposit_text = table.get("押標金") or next((text for text in re.split(r"[。；\n]", full_text) if "押標金" in text), None)
    deposit = integer(deposit_text)
    payment_text = next((value for key, value in table.items() if "繳款期限" in key or "付款期限" in key), None)
    pickup_text = next((value for key, value in table.items() if "領取期限" in key or "提貨期限" in key), None)
    payment_deadline = roc_datetime(payment_text) if payment_text else None
    pickup_deadline = roc_datetime(pickup_text) if pickup_text else None

    # Do not treat navigation/actions such as 「取消追蹤」 as an auction cancellation.
    # Require the official text to connect cancellation to the auction/notice itself.
    if re.search(r"(?:本標案|本拍賣|本公告|本案)(?:已|業經|因故)?取消|狀態[：:]?已取消", full_text):
        status = AuctionStatus.CANCELLED
    elif sold_price is not None and (item.result_record or "結案" in full_text):
        status = AuctionStatus.SOLD
    elif item.result_record:
        status = AuctionStatus.UNKNOWN
    elif ends_at and ends_at < datetime.now(TAIPEI):
        status = AuctionStatus.EXPIRED
    else:
        status = AuctionStatus.SCHEDULED

    description_match = re.search(r"物品說明[:：]\s*(.+?)(?:其他條款|注意事項)", full_text)
    description = clean(description_match.group(1)) if description_match else None
    registration_text = fields.get("牌照異動登記", "")
    combined = clean(" ".join(filter(None, [registration_text, description])))
    vehicle_class, vehicle_class_text = motorcycle_class_from_official_text(f"{title} {combined}")
    fee_notes = list(dict.fromkeys(
        clean(sentence) for sentence in re.split(r"[。；]", combined)
        if re.search(r"(手續費|規費|拖吊費|保管費|過戶費|稅費|燃料費)", sentence)
    ))

    can_relicense = "可再領牌" in combined
    cannot_relicense = "不可再領牌" in combined or "報廢無法再領牌" in combined
    if can_relicense and cannot_relicense:
        registration = RegistrationStatus.REGISTRABILITY_UNKNOWN
    elif cannot_relicense:
        registration = RegistrationStatus.SCRAP_ONLY
    elif "已繳銷" in combined and can_relicense:
        registration = RegistrationStatus.RE_REGISTRATION_REQUIRED
    elif "需檢驗" in combined or "檢驗合格" in combined:
        registration = RegistrationStatus.INSPECTION_REQUIRED
    elif "無牌照" in combined:
        registration = RegistrationStatus.REGISTRABILITY_UNKNOWN
    else:
        registration = RegistrationStatus.UNKNOWN

    recycler_language = "應回收廢棄物回收業登記證" in combined
    eligibility = BidEligibility.LICENSED_RECYCLER_ONLY if item.recycler_only or recycler_language else BidEligibility.NATURAL_PERSON_ALLOWED

    no_key, yes_key = "無鑰匙" in combined, "有鑰匙" in combined
    cannot_start = bool(re.search(r"(發不動|無法發動|不能發動)", combined))
    can_start_text = bool(re.search(r"(可發動|能發動)", combined))
    cannot_test = bool(re.search(r"(無法測試|不得測試|不可測試)", combined))
    can_test_text = bool(re.search(r"(提供.{0,8}測試|可測試)", combined))
    has_key = FourState.CONFLICTING if no_key and yes_key else FourState.NO if no_key else FourState.YES if yes_key else FourState.UNKNOWN
    can_start = FourState.CONFLICTING if cannot_start and can_start_text else FourState.NO if cannot_start else FourState.YES if can_start_text else FourState.UNKNOWN
    can_test = FourState.CONFLICTING if cannot_test and can_test_text else FourState.NO if cannot_test else FourState.YES if can_test_text else FourState.UNKNOWN

    no_tax = "無欠稅" in combined
    no_fines = "無道路交通違規" in combined or "無罰鍰" in combined
    yes_tax = "有欠稅" in combined or "欠稅未繳" in combined
    yes_fines = bool(re.search(r"(欠繳罰鍰|罰鍰未繳)", combined))
    tax_arrears = FourState.CONFLICTING if no_tax and yes_tax else FourState.NO if no_tax else FourState.YES if yes_tax else FourState.UNKNOWN
    fine_arrears = FourState.CONFLICTING if no_fines and yes_fines else FourState.NO if no_fines else FourState.YES if yes_fines else FourState.UNKNOWN
    fuel_arrears = FourState.NO if "無欠燃料費" in combined else FourState.YES if "欠燃料" in combined else FourState.UNKNOWN

    brand = fields.get("廠牌")
    model = fields.get("型號")
    year_match = re.search(r"出廠(?:年份|年月)[：:]?\s*(\d{4})[.年/-]?(\d{1,2})?", combined)
    displacement_match = re.search(r"排氣量[：:]?\s*([\d,]+)\s*[cC][cC]", combined)
    color_match = re.search(r"車身號碼[：:]?\s*[A-Z0-9-]+\s*([\u4e00-\u9fff]{1,3}色)", combined)
    mileage_match = re.search(r"(?:里程|公里數)[：:]?\s*([\d,]+)", combined)

    identity_text = clean(" ".join([title, combined, " ".join(table.values()), " ".join(fields.values())]))
    vehicle_type, vehicle_type_text = vehicle_type_from_official_text(identity_text)
    car_category, car_category_text = car_category_from_official_text(identity_text)
    plate_values = list(dict.fromkeys(re.findall(r"[A-Z0-9]{2,4}[－-][A-Z0-9]{2,4}", identity_text, re.IGNORECASE)))
    identifiers: list[VehicleIdentifier] = []
    if plate_values:
        original = plate_values[0]
        identifiers.append(VehicleIdentifier(identifier_type="PLATE", normalized_value=normalize_identifier(original), original_value=original))
    for kind, pattern in {
        "ENGINE": r"引擎號碼[：:]?\s*([A-Z0-9-]+)",
        "FRAME": r"車身號碼[：:]?\s*([A-Z0-9-]+)",
    }.items():
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            original = match.group(1)
            identifiers.append(VehicleIdentifier(identifier_type=kind, normalized_value=normalize_identifier(original), original_value=original))

    lot_match = re.search(r"(\d+)\s*[臺台輛部]", title)
    lot_size = int(lot_match.group(1)) if lot_match else 1
    vehicle_units = [
        ParsedVehicleUnit(
            source_vehicle_key=f"plate:{normalize_identifier(plate)}",
            identifiers=[VehicleIdentifier(identifier_type="PLATE", normalized_value=normalize_identifier(plate), original_value=plate)],
        )
        for plate in plate_values[:lot_size]
    ] if lot_size > 1 and len(plate_values) >= 2 else []

    photo_urls: list[str] = []
    for link in soup.select("a[href*='imageResize'], img[src*='/image?']"):
        relative = link.get("href") or link.get("src")
        if relative:
            url = urljoin(str(item.official_url), relative)
            if url not in photo_urls:
                photo_urls.append(url)

    evidence: list[EvidenceRef] = []
    for name, normalized, source in [
        ("reserve_price", reserve_price, reserve_text),
        ("auction_round", integer(table.get("拍賣次數")), table.get("拍賣次數")),
        ("registration_status", registration.value, registration_text),
        ("brand", brand, fields.get("廠牌")),
        ("model", model, fields.get("型號")),
        ("deposit", deposit, deposit_text),
        ("payment_deadline", payment_deadline.isoformat() if payment_deadline else None, payment_text),
        ("pickup_deadline", pickup_deadline.isoformat() if pickup_deadline else None, pickup_text),
    ]:
        if source:
            evidence.append(_evidence(name, normalized, source, name))
    if can_start != FourState.UNKNOWN:
        phrase = next((sentence for sentence in re.split(r"[。；]", combined) if re.search(r"(發不動|無法發動|不能發動|可發動|能發動)", sentence)), combined)
        evidence.append(_evidence("can_start", can_start.value, phrase))
    if can_test != FourState.UNKNOWN:
        phrase = next((sentence for sentence in re.split(r"[。；]", combined) if "測試" in sentence), combined)
        evidence.append(_evidence("can_test", can_test.value, phrase))
    if no_tax:
        evidence.append(_evidence("tax_arrears", tax_arrears.value, "無欠稅"))
    if no_fines:
        evidence.append(_evidence("fine_arrears", fine_arrears.value, "無道路交通違規事件"))
    if vehicle_class_text:
        evidence.append(_evidence("vehicle_class", vehicle_class.value, vehicle_class_text))
    if vehicle_type_text:
        evidence.append(_evidence("vehicle_type", vehicle_type.value, vehicle_type_text))
    if car_category_text:
        evidence.append(_evidence("car_category", car_category.value, car_category_text))

    group_values = {
        "identity": [vehicle_type, brand, model, year_match, identifiers],
        "auction": [table.get("拍賣單位"), ends_at, reserve_price, status, eligibility],
        "condition": [has_key, can_start, can_test, description],
        "registration": [registration, next((i for i in identifiers if i.identifier_type == "PLATE"), None), tax_arrears],
        "fees": [tax_arrears, fine_arrears, fuel_arrears],
        "media": [photo_urls],
    }
    unknowns = {FourState.UNKNOWN, RegistrationStatus.UNKNOWN, BidEligibility.UNKNOWN}
    def is_present(value: object) -> bool:
        if value is None or value == "" or value == []:
            return False
        return not isinstance(value, (FourState, RegistrationStatus, BidEligibility)) or value not in unknowns
    groups = {
        name: round(sum(is_present(value) for value in values) / len(values) * 100)
        for name, values in group_values.items()
    }
    weights = {"identity": .2, "auction": .25, "condition": .15, "registration": .2, "fees": .1, "media": .1}
    completeness = round(sum(groups[name] * weight for name, weight in weights.items()))

    return ParsedAuctionRecord(
        source_record_id=item.source_record_id,
        official_url=item.official_url,
        official_title=heading or item.title,
        official_case_number=official_case,
        organization=table.get("拍賣單位", "未辨識機關"),
        status=status,
        auction_round=integer(table.get("拍賣次數")),
        starts_at=starts_at,
        ends_at=ends_at,
        reserve_price=reserve_price,
        current_price=current_price,
        sold_price=sold_price,
        deposit=deposit,
        payment_deadline=payment_deadline,
        pickup_deadline=pickup_deadline,
        fee_notes=fee_notes,
        title=title,
        lot_size=lot_size,
        bulk_lot=lot_size > 1,
        eligibility=eligibility,
        location=table.get("放置地點"),
        description=description,
        brand=brand,
        model=model,
        manufacture_year=int(year_match.group(1)) if year_match else None,
        manufacture_month=int(year_match.group(2)) if year_match and year_match.group(2) else None,
        displacement_cc=integer(displacement_match.group(1)) if displacement_match else None,
        vehicle_type=vehicle_type,
        vehicle_class=vehicle_class,
        car_category=car_category,
        color=color_match.group(1) if color_match else None,
        mileage_km=integer(mileage_match.group(1)) if mileage_match else None,
        has_key=has_key,
        can_start=can_start,
        can_test=can_test,
        registration_status=registration,
        condition_summary=description,
        visible_damage=next((sentence for sentence in re.split(r"[。；]", combined) if re.search(r"(生鏽|損壞|破損|刮傷)", sentence)), None),
        tax_arrears=tax_arrears,
        fine_arrears=fine_arrears,
        fuel_fee_arrears=fuel_arrears,
        identifiers=identifiers,
        vehicle_units=vehicle_units,
        photo_urls=photo_urls,
        evidence=evidence,
        completeness=completeness,
        completeness_groups=groups,
    )
