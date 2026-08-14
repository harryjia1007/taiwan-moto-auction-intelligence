from datetime import UTC, datetime, timedelta

from ingest.models import AuctionStatus, ParsedAuctionRecord, VehicleIdentifier
from ingest.public_feed import public_listing_payload


def record(**overrides):
    values = dict(
        source_record_id="123", official_url="https://shwoo.gov.taipei/example", official_title="普通重型機車",
        organization="臺北市政府", title="普通重型機車", status=AuctionStatus.SCHEDULED,
        ends_at=datetime.now(UTC) + timedelta(days=2),
        identifiers=[VehicleIdentifier(identifier_type="PLATE", normalized_value="ABC123", original_value="ABC-123")],
        photo_urls=["https://shwoo.gov.taipei/image?id=1"],
    )
    values.update(overrides)
    return ParsedAuctionRecord(**values)


def test_public_feed_includes_active_official_plate_but_not_private_identifiers():
    item = record(identifiers=[
        VehicleIdentifier(identifier_type="PLATE", normalized_value="ABC123", original_value="ABC-123"),
        VehicleIdentifier(identifier_type="ENGINE", normalized_value="SECRET", original_value="SECRET"),
    ])
    payload = public_listing_payload(item)
    assert payload["plate_number"] == "ABC-123"
    assert "SECRET" not in str(payload)


def test_public_feed_retains_recent_official_plate_for_history():
    item = record(status=AuctionStatus.EXPIRED, ends_at=datetime.now(UTC) - timedelta(days=1))
    assert public_listing_payload(item)["plate_number"] == "ABC-123"


def test_public_feed_clears_plate_after_thirty_days():
    item = record(status=AuctionStatus.EXPIRED, ends_at=datetime.now(UTC) - timedelta(days=31))
    assert public_listing_payload(item)["plate_number"] is None


def test_public_feed_does_not_copy_description_or_mixed_car_specs():
    item = record(
        official_title="汽車1輛、機車1輛",
        description="汽車排氣量2198CC，機車150CC，請洽王小姐 02-12345678",
        displacement_cc=2198,
        brand="納智捷、三陽",
        model="M7、悍將",
    )
    payload = public_listing_payload(item)
    assert payload["description"] is None
    assert payload["condition_summary"] == "有無鑰匙：未確認；能否發動：未確認；能否測試：未確認"
    assert payload["bulk_lot"] is True
    assert payload["brand_name"] is None
    assert payload["displacement_cc"] is None
    assert "02-12345678" not in str(payload)


def test_public_feed_supports_a_human_reviewed_official_source():
    item = record(source_record_id="court-1", official_url="https://aomp109.judicial.gov.tw/example")
    payload = public_listing_payload(item, source_adapter="judicial", source_name="司法院動產拍賣")
    assert payload["id"] == "judicial-court-1"
    assert payload["source_adapter"] == "judicial"
    assert payload["source_name"] == "司法院動產拍賣"


def test_motorcycle_fee_boilerplate_does_not_create_a_mixed_vehicle_lot():
    item = record(
        official_title="普通重型機車",
        description="拍定人應繳清汽車燃料使用費後辦理過戶",
        displacement_cc=158,
        brand="SYM",
    )
    payload = public_listing_payload(item, source_adapter="judicial", source_name="司法院動產拍賣")
    assert payload["bulk_lot"] is False
    assert payload["brand_name"] == "SYM"
    assert payload["displacement_cc"] == 158
