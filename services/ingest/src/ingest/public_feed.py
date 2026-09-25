from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from ingest.models import ParsedAuctionRecord, VehicleClass, VehicleType
from ingest.official_documents import official_document_urls


_PLATE_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9Ａ-Ｚａ-ｚ０-９])"
    r"(?:[A-Za-z0-9Ａ-Ｚａ-ｚ０-９]{1,4}[-－][A-Za-z0-9Ａ-Ｚａ-ｚ０-９]{1,4})"
    r"(?![A-Za-z0-9Ａ-Ｚａ-ｚ０-９])"
)
_PLAIN_PLATE_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Z]{2,3}\d{3,4}|\d{3,4}[A-Z]{2,3})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_LABELED_PLAIN_PLATE_PATTERN = re.compile(
    r"((?:車牌|車號|牌照)(?:號碼|號)?\s*[:：]?\s*)"
    r"([A-Za-z0-9Ａ-Ｚａ-ｚ０-９]{5,8})(?![A-Za-z0-9Ａ-Ｚａ-ｚ０-９])",
    re.IGNORECASE,
)
_VIN_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-Za-z0-9])", re.IGNORECASE)
_LABELED_VEHICLE_IDENTIFIER_PATTERN = re.compile(
    r"((?:引擎|車身|車架|VIN)(?:號碼|號|碼)?\s*[:：]?\s*)[A-Za-z0-9-]{5,}",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:"
    r"(?:\+?886[-－ ]?9|09)\d{2}(?:[-－ ]?\d{3}){2}"
    r"|(?:\+?886[-－ ]?|0)\d{1,2}[-－ ]?\d{3,4}[-－ ]?\d{4}"
    r"|\(\s*0?\d{1,2}\s*\)\s*\d{3,4}[-－ ]?\d{4}"
    r")(?:\s*(?:#|分機|ext\.?)\s*\d+)?(?!\d)",
    re.IGNORECASE,
)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_TAIWAN_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Z][12]\d{8}(?![A-Za-z0-9])", re.IGNORECASE)
_FULLWIDTH_TAIWAN_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9Ａ-Ｚａ-ｚ０-９])"
    r"[Ａ-Ｚａ-ｚ][１２][０-９]{8}"
    r"(?![A-Za-z0-9Ａ-Ｚａ-ｚ０-９])"
)
_LABELED_PERSONAL_IDENTIFIER_PATTERN = re.compile(
    r"((?:身分證(?:統一)?(?:編號|字號|號)?|居留證(?:統一)?(?:編號|字號|號)?|"
    r"統一證號|護照號碼)\s*[:：]?\s*)"
    r"[A-ZＡ-Ｚａ-ｚ0-9０-９][A-ZＡ-Ｚａ-ｚ0-9０-９\-－ ]{5,24}",
    re.IGNORECASE,
)
_PERSON_ROLE = (
    r"義務人|債務人|債權人|所有人|車主|被告|受刑人|保管人|"
    r"聯絡人|承辦人|代理人|買受人|拍定人|得標人|姓名"
)
_PERSON_CONTEXT_BOUNDARY = (
    r"所有|名下|所屬|持有|應|係|之|於|住址|地址|電話|身分|證號|"
    r"普通|大型|輕型|重型|機車|汽車|車輛|標的|拍賣|公告|案件|案號"
)
_PERSON_ROLE_CJK_PATTERN = re.compile(
    rf"(?P<role>{_PERSON_ROLE})\s*[:：]?\s*"
    rf"(?P<name>[\u4e00-\u9fff○ＯO·．・]{{2,6}}?)"
    rf"(?=$|[\s，,。；;、/()（）.\-_?&#]|(?:{_PERSON_CONTEXT_BOUNDARY}))"
)
_PERSON_ROLE_LATIN_PATTERN = re.compile(
    rf"(?P<role>{_PERSON_ROLE})\s*[:：]?\s*"
    rf"(?P<name>[A-Z][A-Z.'’-]*(?:[\s+-]+[A-Z][A-Z.'’-]*){{0,5}}?)"
    rf"(?=\s*(?:$|[，,。；;、/()（）?&#]|{_PERSON_CONTEXT_BOUNDARY}))",
    re.IGNORECASE,
)
# Unknown role-labelled prose is removed as a whole rather than guessing which
# substring is the person's name.  This is intentionally privacy-biased and is
# applied only after the structured CJK/Latin patterns above.
_PERSON_ROLE_FALLBACK_PATTERN = re.compile(
    rf"(?P<role>{_PERSON_ROLE})(?!\s*[:：]?\s*已隱去)\s*[:：]?\s*"
    r"[^\n，,。；;、/()（）]{2,80}"
)
_PRIVATE_ADDRESS_PATTERN = re.compile(
    r"(?:(?:義務人|債務人|所有人|車主|被告|受刑人|保管人|姓名)"
    r"[^，,。；;\n]{0,20})?"
    r"(?P<label>戶籍地址|通訊地址|聯絡地址|送達地址|住址|住所|居所)"
    r"\s*[:：]?\s*[^\n，,。；;]{4,100}"
)

# No integrated source currently grants anonymous redistribution rights for
# its official photos. A future entry requires a reviewed photo-rights ALLOW
# decision plus an exact HTTPS host; private owner views use a separate path.
_PUBLIC_PHOTO_HOST_ALLOWLIST: dict[str, frozenset[str]] = {}

# Public document links must stay on the exact official hosts reviewed for the
# adapter that produced them.  A broad ``*.gov.tw`` check would let a malformed
# record from one source point users at an unrelated government host while still
# appearing to be provenance-checked.
_PUBLIC_SOURCE_HOST_ALLOWLIST: dict[str, frozenset[str]] = {
    "shwoo": frozenset({"shwoo.gov.taipei"}),
    "judicial": frozenset({"aomp109.judicial.gov.tw"}),
    "judicial_notices": frozenset({"www.judicial.gov.tw"}),
    "moj_auction": frozenset({
        "auction.moj.gov.tw",
        "www.tcc.moj.gov.tw",
        "www.qtc.moj.gov.tw",
        "www.ulc.moj.gov.tw",
    }),
    "moj_enforcement": frozenset({"www.tpkonsale.moj.gov.tw"}),
    "moj_enforcement_cms": frozenset({
        "www.tpy.moj.gov.tw",
        "www.sly.moj.gov.tw",
        "www.pcy.moj.gov.tw",
        "www.tyy.moj.gov.tw",
        "www.scy.moj.gov.tw",
        "www.tcy.moj.gov.tw",
        "www.chy.moj.gov.tw",
        "www.cyy.moj.gov.tw",
        "www.tny.moj.gov.tw",
        "www.ksy.moj.gov.tw",
        "www.pty.moj.gov.tw",
        "www.hly.moj.gov.tw",
        "www.ily.moj.gov.tw",
    }),
    "pcc": frozenset({"web.pcc.gov.tw"}),
    "customs": frozenset({"web.customs.gov.tw"}),
}

_PUBLIC_SOURCE_FALLBACK_URLS: dict[str, str] = {
    "shwoo": "https://shwoo.gov.taipei/",
    "judicial": "https://aomp109.judicial.gov.tw/",
    "judicial_notices": "https://www.judicial.gov.tw/tw/lp-1913-1.html",
    "moj_auction": "https://auction.moj.gov.tw/",
    "moj_enforcement": "https://www.tpkonsale.moj.gov.tw/",
    "moj_enforcement_cms": "https://www.tpk.moj.gov.tw/",
    "pcc": "https://web.pcc.gov.tw/",
    "customs": "https://web.customs.gov.tw/",
}
_PUBLIC_PROJECT_FALLBACK_URL = "https://harryjia.com/projects/taiwan-moto-auction/"


def _mask_last_ascii_alnum(value: str, count: int) -> str:
    characters = list(value)
    masked = 0
    for index in range(len(characters) - 1, -1, -1):
        if characters[index].isascii() and characters[index].isalnum():
            characters[index] = "*"
            masked += 1
            if masked == count:
                break
    return "".join(characters)


def mask_public_plate(value: str) -> str | None:
    """Mask the final two or three plate characters without changing private data.

    Taiwanese plates normally end in a two-to-four character group. We keep the
    prefix that helps an owner recognise a listing, but never publish a complete
    plate. Malformed one-character values are suppressed instead of guessed.
    """
    plate = unicodedata.normalize("NFKC", value.strip())
    if not plate:
        return None

    def mask_token(match: re.Match[str]) -> str:
        token = match.group(0)
        trailing = re.search(r"([A-Za-z0-9]+)$", token)
        trailing_count = len(trailing.group(1)) if trailing else 0
        if trailing_count >= 2:
            return _mask_last_ascii_alnum(token, min(3, trailing_count))
        total_count = sum(character.isascii() and character.isalnum() for character in token)
        return _mask_last_ascii_alnum(token, min(2, total_count))

    masked, count = _PLATE_TOKEN_PATTERN.subn(mask_token, plate)
    if count:
        return masked

    total_count = sum(character.isascii() and character.isalnum() for character in plate)
    if total_count < 2:
        return None
    return _mask_last_ascii_alnum(plate, min(3, total_count))


def _record_identifiers(record: ParsedAuctionRecord) -> list[tuple[str, str]]:
    identifiers = list(record.identifiers)
    for unit in record.vehicle_units:
        identifiers.extend(unit.identifiers)
    values: list[tuple[str, str]] = []
    for identifier in identifiers:
        identifier_type = identifier.identifier_type.strip().upper()
        for value in (identifier.original_value, identifier.normalized_value):
            cleaned = value.strip()
            if cleaned:
                values.append((identifier_type, cleaned))
    return list(dict.fromkeys(values))


def _known_identifier_replacements(identifiers: list[tuple[str, str]]) -> list[tuple[str, str]]:
    replacements: list[tuple[str, str]] = []
    for identifier_type, value in identifiers:
        replacement = mask_public_plate(value) if identifier_type == "PLATE" else "車輛識別碼已隱藏"
        replacements.append((value, replacement or "車牌已隱藏"))
    return sorted(dict.fromkeys(replacements), key=lambda item: len(item[0]), reverse=True)


def _sanitize_public_text(value: str | None, replacements: list[tuple[str, str]]) -> str | None:
    if value is None:
        return None
    sanitized = value
    for identifier, replacement in replacements:
        left_boundary = r"(?<![A-Za-z0-9])" if identifier[0].isascii() and identifier[0].isalnum() else ""
        right_boundary = r"(?![A-Za-z0-9])" if identifier[-1].isascii() and identifier[-1].isalnum() else ""
        sanitized = re.sub(
            f"{left_boundary}{re.escape(identifier)}{right_boundary}",
            lambda _: replacement,
            sanitized,
            flags=re.IGNORECASE,
        )
    sanitized = _VIN_PATTERN.sub("車身識別碼已隱藏", sanitized)
    sanitized = _LABELED_VEHICLE_IDENTIFIER_PATTERN.sub(r"\1已隱藏", sanitized)
    sanitized = _PHONE_PATTERN.sub("聯絡電話已隱藏", sanitized)
    sanitized = _EMAIL_PATTERN.sub("聯絡信箱已隱藏", sanitized)
    sanitized = _LABELED_PERSONAL_IDENTIFIER_PATTERN.sub(r"\1已隱去", sanitized)
    sanitized = _TAIWAN_ID_PATTERN.sub("身分證字號已隱去", sanitized)
    sanitized = _FULLWIDTH_TAIWAN_ID_PATTERN.sub("身分證字號已隱去", sanitized)
    sanitized = _PRIVATE_ADDRESS_PATTERN.sub(
        lambda match: f"{match.group('label')}：已隱去",
        sanitized,
    )
    for pattern in (
        _PERSON_ROLE_CJK_PATTERN,
        _PERSON_ROLE_LATIN_PATTERN,
        _PERSON_ROLE_FALLBACK_PATTERN,
    ):
        sanitized = pattern.sub(lambda match: f"{match.group('role')}：已隱去", sanitized)
    sanitized = _LABELED_PLAIN_PLATE_PATTERN.sub(
        lambda match: f"{match.group(1)}{mask_public_plate(match.group(2)) or '車牌已隱藏'}",
        sanitized,
    )
    # Apply plate-shaped fallback last: 0912-345-678 must first be removed as
    # a telephone number, not partially masked as if it were a vehicle plate.
    sanitized = _PLATE_TOKEN_PATTERN.sub(
        lambda match: mask_public_plate(match.group(0)) or "車牌已隱藏",
        sanitized,
    )
    return sanitized


def _decode_for_public_safety(value: str) -> str:
    """Decode nested URL escaping without allowing an encoded PII bypass."""
    decoded = value
    for _ in range(3):
        candidate = unquote_plus(decoded)
        if candidate == decoded:
            break
        decoded = candidate
    return decoded


def _contains_known_identifier(value: str, identifiers: list[tuple[str, str]]) -> bool:
    decoded = _decode_for_public_safety(value).casefold()
    return any(identifier.casefold() in decoded for _, identifier in identifiers)


def _contains_plate_token(value: str) -> bool:
    return bool(_PLATE_TOKEN_PATTERN.search(_decode_for_public_safety(value)))


def _contains_plate_token_in_url(value: str) -> bool:
    decoded = _decode_for_public_safety(value)
    parsed = urlsplit(decoded)
    if re.search(r"(?:[?&](?:plate|license[_-]?plate|車牌|車號)=)[^&#]+", decoded, re.IGNORECASE):
        return True
    if (
        (parsed.hostname or "").lower() == "www.judicial.gov.tw"
        and not parsed.query
        and not parsed.fragment
        and re.fullmatch(
            r"/tw/dl-\d+-(?:[0-9a-f]{8}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\.html",
            parsed.path,
            flags=re.IGNORECASE,
        )
    ):
        # A fixed-length opaque document ID is not a vehicle plate, even if
        # one four-character hexadecimal UUID segment resembles a plate.
        return False
    # Judicial main-site route prefixes (cp-1913, dl-54321, lp-1913) are
    # published CMS routing IDs, not plates. Preserve those official links,
    # while still rejecting any plate-shaped token in the rest of the URL.
    without_cms_route = re.sub(
        r"(?<=/)(?:cp|dl|lp)-\d+(?=[-./?#]|$)",
        "official-route",
        decoded,
        flags=re.IGNORECASE,
    )
    return bool(_PLATE_TOKEN_PATTERN.search(without_cms_route))


def _contains_public_personal_data(value: str, *, include_phone: bool = True) -> bool:
    decoded = _decode_for_public_safety(value)
    patterns = [
        _TAIWAN_ID_PATTERN,
        _FULLWIDTH_TAIWAN_ID_PATTERN,
        _LABELED_PERSONAL_IDENTIFIER_PATTERN,
        _PERSON_ROLE_CJK_PATTERN,
        _PERSON_ROLE_LATIN_PATTERN,
        _PERSON_ROLE_FALLBACK_PATTERN,
        _PRIVATE_ADDRESS_PATTERN,
        _EMAIL_PATTERN,
    ]
    if include_phone:
        patterns.append(_PHONE_PATTERN)
    return any(pattern.search(decoded) for pattern in patterns)


def _sanitize_official_url(
    value: str,
    source_adapter: str,
    identifiers: list[tuple[str, str]],
) -> str:
    """Publish only a reviewed source/host pair and remove identifying URL data."""
    fallback = _PUBLIC_SOURCE_FALLBACK_URLS.get(source_adapter, _PUBLIC_PROJECT_FALLBACK_URL)
    allowed_hosts = _PUBLIC_SOURCE_HOST_ALLOWLIST.get(source_adapter)
    if not allowed_hosts:
        return fallback
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError:
        return fallback
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or hostname not in allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        return fallback
    if (
        _contains_known_identifier(value, identifiers)
        or _contains_plate_token_in_url(value)
        or _VIN_PATTERN.search(_decode_for_public_safety(value))
        or _contains_public_personal_data(value)
    ):
        return urlunsplit(("https", hostname, "/", "", ""))
    return value.strip()


def _public_documents(
    record: ParsedAuctionRecord,
    source_adapter: str,
    identifiers: list[tuple[str, str]],
    artifact_document_urls: tuple[str, ...],
) -> list[dict[str, str]]:
    """Project official HTTPS attachment links without copying evidence text or bytes."""
    documents: list[dict[str, str]] = []
    for candidate in official_document_urls(
        record,
        source_adapter,
        artifact_urls=artifact_document_urls,
    ):
        if (
            _contains_known_identifier(candidate, identifiers)
            or _contains_plate_token_in_url(candidate)
            or _VIN_PATTERN.search(_decode_for_public_safety(candidate))
            # Judicial main-site document links end in an opaque UUID-like
            # token that can begin with eight digits. Do not misclassify that
            # exact, source-validated identifier as a phone number; Taiwan IDs,
            # role-labelled names, email and known vehicle identifiers remain
            # blocked.
            or _contains_public_personal_data(
                candidate,
                include_phone=source_adapter != "judicial_notices",
            )
        ):
            continue
        documents.append({"label": "官方完整全文", "url": candidate})
    return documents


def _public_photo_urls(
    record: ParsedAuctionRecord,
    source_adapter: str,
    identifiers: list[tuple[str, str]],
) -> list[str]:
    """Return only explicitly licensed, exact-host HTTPS images.

    The allowlist is intentionally empty today. Public cards therefore use a
    no-photo treatment while private owner pages may still show official images.
    """
    allowed_hosts = _PUBLIC_PHOTO_HOST_ALLOWLIST.get(source_adapter)
    if not allowed_hosts:
        return []
    images: list[str] = []
    for value in record.photo_urls:
        candidate = str(value)
        parsed = urlsplit(candidate)
        try:
            port = parsed.port
        except ValueError:
            continue
        if (
            parsed.scheme != "https"
            or (parsed.hostname or "").lower() not in allowed_hosts
            or port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
            or _contains_known_identifier(candidate, identifiers)
            or _contains_plate_token_in_url(candidate)
            or _VIN_PATTERN.search(_decode_for_public_safety(candidate))
            or _contains_public_personal_data(candidate)
        ):
            continue
        images.append(candidate)
    return list(dict.fromkeys(images))


def public_listing_payload(
    record: ParsedAuctionRecord,
    *,
    source_adapter: str = "shwoo",
    source_name: str = "臺北惜物網",
    synced_at: datetime | None = None,
    artifact_document_urls: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build the intentionally narrow public projection from an official record.

    Engine, frame and VIN identifiers, evidence text, raw artifacts and people are
    never included. Recent plate data is partially masked in the public projection;
    the complete official value remains available only in the private evidence.
    """
    now = (synced_at or datetime.now(UTC)).astimezone(UTC)
    # Recent official auction notices remain useful for price/history research.
    # Keep a plate for at most 30 days after the official end time, then clear it
    # from the public projection even though the private evidence is retained.
    plate_public = record.ends_at is not None and record.ends_at >= now - timedelta(days=30)
    identifiers = _record_identifiers(record)
    replacements = _known_identifier_replacements(identifiers)
    plate_values = [
        entry.original_value
        for entry in record.identifiers
        if entry.identifier_type.strip().upper() == "PLATE"
    ]
    for unit in record.vehicle_units:
        plate_values.extend(
            entry.original_value
            for entry in unit.identifiers
            if entry.identifier_type.strip().upper() == "PLATE"
        )
    plates = [masked for value in plate_values if (masked := mask_public_plate(value)) is not None]
    plates = list(dict.fromkeys(plates))
    public_source_record_id = record.source_record_id
    if (
        _contains_known_identifier(public_source_record_id, identifiers)
        or _contains_plate_token(public_source_record_id)
        or _PLAIN_PLATE_TOKEN_PATTERN.search(unicodedata.normalize("NFKC", public_source_record_id))
        or _VIN_PATTERN.search(_decode_for_public_safety(public_source_record_id))
        or _contains_public_personal_data(public_source_record_id)
    ):
        digest = hashlib.sha256(f"{source_adapter}\0{record.source_record_id}".encode()).hexdigest()[:20]
        public_source_record_id = f"redacted-{digest}"
    vehicle_text = f"{record.official_title} {record.description or ''}"
    # Legal boilerplate frequently says 「汽車燃料使用費」 even for a single
    # motorcycle. Only explicit non-motorcycle vehicle nouns make this mixed.
    explicit_car = re.search(r"(?:自用|營業)?(?:小客|大客|小貨|大貨|客貨兩用)車|汽車\s*\d+\s*[輛台部]", vehicle_text)
    # The parser's explicit normalized classification is authoritative.  An
    # incidental mention of the other vehicle family in auction terms must not
    # turn an identified single vehicle into a mixed lot.  Text is only a
    # fallback for older records whose classification is still UNKNOWN.
    if record.vehicle_type != VehicleType.UNKNOWN:
        public_vehicle_type = record.vehicle_type.value
    elif explicit_car and "機車" in vehicle_text:
        public_vehicle_type = VehicleType.MIXED.value
    elif record.vehicle_class != VehicleClass.UNKNOWN or "機車" in vehicle_text:
        public_vehicle_type = VehicleType.MOTORCYCLE.value
    elif explicit_car:
        public_vehicle_type = VehicleType.CAR.value
    else:
        public_vehicle_type = VehicleType.UNKNOWN.value
    mixed_vehicle_lot = public_vehicle_type == VehicleType.MIXED.value
    # ParsedVehicleUnit currently carries identifiers, not unit-specific
    # specifications.  A shared prose block cannot prove which of two plates
    # owns the record-level brand, model, year, CC, colour or odometer value.
    ambiguous_multi_vehicle_specs = mixed_vehicle_lot or len(record.vehicle_units) > 1
    state_labels = {
        "YES": "是", "NO": "否", "UNKNOWN": "未確認", "CONFLICTING": "資訊衝突",
    }
    public_condition = "；".join([
        f"有無鑰匙：{state_labels[record.has_key.value]}",
        f"能否發動：{state_labels[record.can_start.value]}",
        f"能否測試：{state_labels[record.can_test.value]}",
    ])

    payload: dict[str, Any] = {
        "id": f"{source_adapter}-{public_source_record_id}",
        "source_adapter": source_adapter,
        "source_name": _sanitize_public_text(source_name, replacements) or "官方拍賣來源",
        "source_record_id": public_source_record_id,
        "official_url": _sanitize_official_url(str(record.official_url), source_adapter, identifiers),
        "official_title": _sanitize_public_text(record.official_title, replacements) or "車輛拍賣公告",
        "official_case_number": _sanitize_public_text(record.official_case_number, replacements),
        "organization_name": _sanitize_public_text(record.organization, replacements) or source_name,
        "disposal_origin": record.disposal_origin,
        "auction_status": record.status.value,
        "auction_round": record.auction_round,
        "starts_at": record.starts_at.isoformat() if record.starts_at else None,
        "ends_at": record.ends_at.isoformat() if record.ends_at else None,
        "reserve_price": record.reserve_price,
        "current_price": record.current_price,
        "sold_price": record.sold_price,
        "deposit": record.deposit,
        "eligibility": record.eligibility.value,
        "registration_status": record.registration_status.value,
        "vehicle_type": public_vehicle_type,
        "vehicle_category": "UNKNOWN" if mixed_vehicle_lot else record.vehicle_class.value,
        "car_category": "UNKNOWN" if mixed_vehicle_lot else record.car_category.value,
        "brand_name": None if ambiguous_multi_vehicle_specs else _sanitize_public_text(record.brand, replacements),
        "model_name": None if ambiguous_multi_vehicle_specs else _sanitize_public_text(record.model, replacements),
        "manufacture_year": None if ambiguous_multi_vehicle_specs else record.manufacture_year,
        "manufacture_month": None if ambiguous_multi_vehicle_specs else record.manufacture_month,
        "displacement_cc": None if ambiguous_multi_vehicle_specs else record.displacement_cc,
        "color": None if ambiguous_multi_vehicle_specs else _sanitize_public_text(record.color, replacements),
        "mileage_km": None if ambiguous_multi_vehicle_specs else record.mileage_km,
        "plate_number": "、".join(plates) if plate_public and plates else None,
        "has_key": record.has_key.value,
        "can_start": record.can_start.value,
        "can_test": record.can_test.value,
        "location": _sanitize_public_text(record.location, replacements),
        "description": None,
        "condition_summary": public_condition,
        "fee_notes": [
            sanitized
            for note in record.fee_notes
            if (sanitized := _sanitize_public_text(note, replacements))
        ],
        "lot_size": record.lot_size,
        "bulk_lot": record.bulk_lot or mixed_vehicle_lot or len(record.vehicle_units) > 1,
        "photo_urls": _public_photo_urls(record, source_adapter, identifiers),
        "documents": _public_documents(
            record,
            source_adapter,
            identifiers,
            artifact_document_urls,
        ),
        "completeness": record.completeness,
        "completeness_groups": record.completeness_groups,
        "last_synced_at": now.isoformat(),
        "active": True,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["content_checksum"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload
