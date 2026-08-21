from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from ingest.models import ParsedAuctionRecord, VehicleClass, VehicleType


_PLATE_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z0-9]{1,4}[-－][A-Za-z0-9]{1,4})(?![A-Za-z0-9])"
)
_VIN_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-Za-z0-9])", re.IGNORECASE)
_LABELED_VEHICLE_IDENTIFIER_PATTERN = re.compile(
    r"((?:引擎|車身|車架|VIN)(?:號碼|號|碼)?\s*[:：]?\s*)[A-Za-z0-9-]{5,}",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:09\d{2}(?:[-－ ]?\d{3}){2}|0\d{1,2}[-－ ]?\d{6,8})"
    r"(?:\s*(?:#|分機)\s*\d+)?(?!\d)"
)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_TAIWAN_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Z][12]\d{8}(?![A-Za-z0-9])", re.IGNORECASE)
_PERSON_ROLE_PATTERN = re.compile(
    r"(?P<role>義務人|債務人|所有人|車主|被告|受刑人|保管人|姓名)"
    r"\s*[:：]?\s*(?P<name>[\u4e00-\u9fff○ＯO·．・]{2,6}?)"
    r"(?=$|[\s，,。；;、/()（）.\-_?&#]|應|係|之|於|住址|電話|身分|證號)"
)

# No integrated source currently grants anonymous redistribution rights for
# its official photos. A future entry requires a reviewed photo-rights ALLOW
# decision plus an exact HTTPS host; private owner views use a separate path.
_PUBLIC_PHOTO_HOST_ALLOWLIST: dict[str, frozenset[str]] = {}


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
    plate = value.strip()
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
    sanitized = _TAIWAN_ID_PATTERN.sub("身分證字號已隱去", sanitized)
    sanitized = _PERSON_ROLE_PATTERN.sub(lambda match: f"{match.group('role')}：已隱去", sanitized)
    return sanitized


def _contains_known_identifier(value: str, identifiers: list[tuple[str, str]]) -> bool:
    decoded = unquote(value).casefold()
    return any(identifier.casefold() in decoded for _, identifier in identifiers)


def _contains_public_personal_data(value: str) -> bool:
    decoded = unquote(value)
    return any(
        pattern.search(decoded)
        for pattern in (_TAIWAN_ID_PATTERN, _PERSON_ROLE_PATTERN, _PHONE_PATTERN, _EMAIL_PATTERN)
    )


def _sanitize_official_url(value: str, identifiers: list[tuple[str, str]]) -> str:
    """Keep a working official link, but fall back to its origin if its URL leaks an identifier."""
    if (
        not _contains_known_identifier(value, identifiers)
        and not _VIN_PATTERN.search(unquote(value))
        and not _contains_public_personal_data(value)
    ):
        return value
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def _public_documents(
    record: ParsedAuctionRecord,
    identifiers: list[tuple[str, str]],
) -> list[dict[str, str]]:
    """Project official HTTPS attachment links without copying evidence text or bytes."""
    documents: list[dict[str, str]] = []
    seen: set[str] = set()
    for evidence in record.evidence:
        if evidence.field_name.strip().lower() != "official_attachment_url":
            continue
        value = evidence.normalized_value
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        parsed = urlsplit(candidate)
        try:
            port = parsed.port
        except ValueError:
            continue
        hostname = (parsed.hostname or "").lower()
        official_host = (
            hostname.endswith(".gov.tw")
            or hostname == "gov.tw"
            or hostname.endswith(".gov.taipei")
            or hostname == "gov.taipei"
        )
        if (
            parsed.scheme != "https"
            or not official_host
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
            or candidate in seen
            or _contains_known_identifier(candidate, identifiers)
            or _VIN_PATTERN.search(unquote(candidate))
            or _contains_public_personal_data(candidate)
        ):
            continue
        seen.add(candidate)
        documents.append({"label": "官方附件", "url": candidate})
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
            or _VIN_PATTERN.search(unquote(candidate))
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
        or _VIN_PATTERN.search(public_source_record_id)
        or _contains_public_personal_data(public_source_record_id)
    ):
        digest = hashlib.sha256(f"{source_adapter}\0{record.source_record_id}".encode()).hexdigest()[:20]
        public_source_record_id = f"redacted-{digest}"
    vehicle_text = f"{record.official_title} {record.description or ''}"
    # Legal boilerplate frequently says 「汽車燃料使用費」 even for a single
    # motorcycle. Only explicit non-motorcycle vehicle nouns make this mixed.
    explicit_car = re.search(r"(?:自用|營業)?(?:小客|大客|小貨|大貨|客貨兩用)車|汽車\s*\d+\s*[輛台部]", vehicle_text)
    mixed_vehicle_lot = record.vehicle_type == VehicleType.MIXED or bool(explicit_car and "機車" in vehicle_text)
    if mixed_vehicle_lot:
        public_vehicle_type = VehicleType.MIXED.value
    elif record.vehicle_type != VehicleType.UNKNOWN:
        public_vehicle_type = record.vehicle_type.value
    elif record.vehicle_class != VehicleClass.UNKNOWN or "機車" in vehicle_text:
        public_vehicle_type = VehicleType.MOTORCYCLE.value
    elif explicit_car:
        public_vehicle_type = VehicleType.CAR.value
    else:
        public_vehicle_type = VehicleType.UNKNOWN.value
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
        "official_url": _sanitize_official_url(str(record.official_url), identifiers),
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
        "brand_name": None if mixed_vehicle_lot else _sanitize_public_text(record.brand, replacements),
        "model_name": None if mixed_vehicle_lot else _sanitize_public_text(record.model, replacements),
        "manufacture_year": record.manufacture_year,
        "manufacture_month": record.manufacture_month,
        "displacement_cc": None if mixed_vehicle_lot else record.displacement_cc,
        "color": _sanitize_public_text(record.color, replacements),
        "mileage_km": record.mileage_km,
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
        "bulk_lot": record.bulk_lot or mixed_vehicle_lot,
        "photo_urls": _public_photo_urls(record, source_adapter, identifiers),
        "documents": _public_documents(record, identifiers),
        "completeness": record.completeness,
        "completeness_groups": record.completeness_groups,
        "last_synced_at": now.isoformat(),
        "active": True,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["content_checksum"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload
