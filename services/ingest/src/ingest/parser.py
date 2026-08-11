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
    DiscoveredItem,
    EvidenceRef,
    FourState,
    ParsedAuctionRecord,
    ParsedVehicleUnit,
    RawArtifact,
    RegistrationStatus,
    VehicleIdentifier,
)

TAIPEI = ZoneInfo("Asia/Taipei")


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def roc_datetime(value: str) -> datetime | None:
    match = re.search(r"(?P<year>\d{2,3})/(?P<month>\d{1,2})/(?P<day>\d{1,2})(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?)?", value)
    if not match:
        return None
    parts = {key: int(number) if number else 0 for key, number in match.groupdict().items()}
    return datetime(parts["year"] + 1911, parts["month"], parts["day"], parts["hour"], parts["minute"], parts["second"], tzinfo=TAIPEI)


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
    match = re.search(r"([\d,]+)", value)
    return int(match.group(1).replace(",", "")) if match else None


def normalize_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper().replace("－", "-"))


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
    sale_date = roc_compact_date(str(row.get("saledate") or ""))
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
    plate_match = re.search(r"(?<![A-Z0-9])([A-Z0-9]{2,4}[-－][A-Z0-9]{2,4})(?![A-Z0-9])", identity_text)
    plate = plate_match.group(1).replace("－", "-") if plate_match else None
    brand_raw = _label_value(notes, ("廠牌", "廠牌名稱"))
    brand_aliases = {"光陽": "KYMCO", "三陽": "SYM", "山葉": "YAMAHA", "台灣山葉": "YAMAHA"}
    if not brand_raw:
        brand_raw = next((alias for alias in ("台灣山葉", "光陽", "三陽", "山葉") if alias in f"{title} {notes}"), None)
    brand = brand_aliases.get(brand_raw or "", brand_raw)
    model = _label_value(notes, ("型式", "型號", "車型"))
    displacement_text = _label_value(notes, ("排氣量(馬力)", "排氣量（馬力）", "排氣量", "汽缸容量"))
    displacement = integer(displacement_text)
    color = _label_value(notes, ("顏色", "車色"))
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

    identifiers: list[VehicleIdentifier] = []
    for kind, value in (("PLATE", plate), ("ENGINE", engine), ("FRAME", frame)):
        if value:
            identifiers.append(VehicleIdentifier(identifier_type=kind, normalized_value=normalize_identifier(value), original_value=value))

    reserve_raw = integer(str(row.get("sumprice") or ""))
    reserve_price = reserve_raw if reserve_raw and reserve_raw > 0 else None
    official_url = str(item.official_url)
    evidence: list[EvidenceRef] = []
    for field_name, normalized, source_value, key in [
        ("official_case_number", case_number or None, case_number, "crm"),
        ("organization", organization, row.get("crtnm"), "crtnm"),
        ("ends_at", sale_date.date().isoformat() if sale_date else None, row.get("saledate"), "saledate"),
        ("auction_round", auction_round, row.get("saleno"), "saleno"),
        ("lot_size", quantity, row.get("qty"), "qty"),
        ("reserve_price", reserve_price, row.get("sumprice"), "sumprice"),
        ("title", title, row.get("ttitle"), "ttitle"),
    ]:
        if source_value not in (None, ""):
            trust = "OFFICIAL_INFERRED" if field_name == "reserve_price" and reserve_price is None else "OFFICIAL_EXPLICIT"
            evidence.append(_structured_evidence(field_name, normalized, source_value, key, trust))
    evidence.append(_structured_evidence("disposal_origin", "JUDICIAL_EXECUTION", organization, "crtnm", "OFFICIAL_INFERRED"))
    for field_name, normalized, source_value in [
        ("plate", plate, plate), ("brand", brand, brand_raw), ("model", model, model),
        ("manufacture_year", manufacture_year, manufacture), ("displacement_cc", displacement, displacement_text),
        ("color", color, color), ("engine", engine, engine), ("frame", frame, frame),
    ]:
        if source_value:
            evidence.append(_structured_evidence(field_name, normalized, source_value, "notes"))

    completeness, groups = _completeness_groups({
        "identity": [plate, brand, model, case_number],
        "auction": [organization, sale_date, auction_round, reserve_price, status],
        "condition": [FourState.UNKNOWN, FourState.UNKNOWN, FourState.UNKNOWN, notes],
        "registration": [RegistrationStatus.UNKNOWN, plate, FourState.UNKNOWN],
        "fees": [None, None, None],
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
        color=color,
        registration_status=RegistrationStatus.UNKNOWN,
        condition_summary=notes or None,
        identifiers=identifiers,
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
    inferred_scrap = "報廢機車" in combined or "廢機車" in combined
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
    count_match = re.search(r"機車\s*(\d+)\s*[輛台部]", normalized_title)
    if not count_match:
        count_match = re.search(r"(\d+)\s*[輛台部][^，。]{0,8}機車", normalized_title)
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

    if "取消" in full_text:
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

    plate_values = list(dict.fromkeys(re.findall(r"[A-Z0-9]{2,4}[－-][A-Z0-9]{2,4}", combined, re.IGNORECASE)))
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

    group_values = {
        "identity": [brand, model, year_match, displacement_match, identifiers],
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
