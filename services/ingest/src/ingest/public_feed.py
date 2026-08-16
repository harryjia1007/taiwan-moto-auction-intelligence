from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from ingest.models import ParsedAuctionRecord, VehicleClass, VehicleType


def public_listing_payload(
    record: ParsedAuctionRecord,
    *,
    source_adapter: str = "shwoo",
    source_name: str = "臺北惜物網",
    synced_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the intentionally narrow public projection from an official record.

    Engine, frame and VIN identifiers, evidence text, raw artifacts and people are
    never included. A plate is published only while the auction is still active.
    """
    now = (synced_at or datetime.now(UTC)).astimezone(UTC)
    # Recent official auction notices remain useful for price/history research.
    # Keep a plate for at most 30 days after the official end time, then clear it
    # from the public projection even though the private evidence is retained.
    plate_public = record.ends_at is None or record.ends_at >= now - timedelta(days=30)
    plates = [entry.original_value for entry in record.identifiers if entry.identifier_type == "PLATE"]
    for unit in record.vehicle_units:
        plates.extend(entry.original_value for entry in unit.identifiers if entry.identifier_type == "PLATE")
    plates = list(dict.fromkeys(plates))
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
        "id": f"{source_adapter}-{record.source_record_id}",
        "source_adapter": source_adapter,
        "source_name": source_name,
        "source_record_id": record.source_record_id,
        "official_url": str(record.official_url),
        "official_title": record.official_title,
        "official_case_number": record.official_case_number,
        "organization_name": record.organization,
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
        "brand_name": None if mixed_vehicle_lot else record.brand,
        "model_name": None if mixed_vehicle_lot else record.model,
        "manufacture_year": record.manufacture_year,
        "manufacture_month": record.manufacture_month,
        "displacement_cc": None if mixed_vehicle_lot else record.displacement_cc,
        "color": record.color,
        "mileage_km": record.mileage_km,
        "plate_number": "、".join(plates) if plate_public and plates else None,
        "has_key": record.has_key.value,
        "can_start": record.can_start.value,
        "can_test": record.can_test.value,
        "location": record.location,
        "description": None,
        "condition_summary": public_condition,
        "fee_notes": record.fee_notes,
        "lot_size": record.lot_size,
        "bulk_lot": record.bulk_lot or mixed_vehicle_lot,
        "photo_urls": [str(url) for url in record.photo_urls],
        "documents": [],
        "completeness": record.completeness,
        "completeness_groups": record.completeness_groups,
        "last_synced_at": now.isoformat(),
        "active": True,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["content_checksum"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload
