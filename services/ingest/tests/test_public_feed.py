from datetime import UTC, datetime, timedelta

import pytest

from ingest.models import (
    AuctionStatus,
    CarCategory,
    EvidenceRef,
    ParsedAuctionRecord,
    ParsedVehicleUnit,
    SyncResult,
    VehicleIdentifier,
    VehicleType,
)
from ingest.public_feed import mask_public_plate, public_listing_payload
from ingest.public_publisher import SupabasePublicPublisher


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


def test_public_feed_masks_active_official_plate_and_excludes_private_identifiers():
    item = record(identifiers=[
        VehicleIdentifier(identifier_type="PLATE", normalized_value="ABC123", original_value="ABC-123"),
        VehicleIdentifier(identifier_type="ENGINE", normalized_value="SECRET", original_value="SECRET"),
    ])
    payload = public_listing_payload(item)
    assert payload["plate_number"] == "ABC-***"
    assert "ABC-123" not in str(payload)
    assert "SECRET" not in str(payload)


def test_public_feed_retains_recent_official_plate_for_history():
    item = record(status=AuctionStatus.EXPIRED, ends_at=datetime.now(UTC) - timedelta(days=1))
    assert public_listing_payload(item)["plate_number"] == "ABC-***"


def test_public_feed_clears_plate_after_thirty_days():
    item = record(status=AuctionStatus.EXPIRED, ends_at=datetime.now(UTC) - timedelta(days=31))
    assert public_listing_payload(item)["plate_number"] is None


def test_public_feed_never_publishes_plate_without_a_verified_end_time():
    assert public_listing_payload(record(ends_at=None))["plate_number"] is None


def test_public_feed_suppresses_known_plate_in_text_without_a_verified_end_time():
    item = record(ends_at=None, official_title="普通重型機車，車牌 ABC-123")
    payload = public_listing_payload(item)

    assert payload["plate_number"] is None
    assert payload["official_title"] == "普通重型機車，車牌 已隱藏"
    assert "ABC-123" not in str(payload)


@pytest.mark.parametrize(
    ("plate", "masked"),
    [
        ("ABC-123", "ABC-***"),
        ("AB-12", "AB-**"),
        ("1234-AB", "1234-**"),
        ("ABC123", "ABC***"),
        ("ABC-123 等 2 面", "ABC-*** 等 2 面"),
        ("A", None),
    ],
)
def test_public_plate_mask_preserves_only_a_recognition_prefix(plate: str, masked: str | None):
    assert mask_public_plate(plate) == masked


def test_public_feed_masks_each_vehicle_unit_plate_once():
    item = record(
        identifiers=[],
        vehicle_units=[
            ParsedVehicleUnit(
                source_vehicle_key="first",
                identifiers=[VehicleIdentifier(identifier_type="PLATE", normalized_value="ABC123", original_value="ABC-123")],
            ),
            ParsedVehicleUnit(
                source_vehicle_key="second",
                identifiers=[VehicleIdentifier(identifier_type="PLATE", normalized_value="DEF456", original_value="DEF-456")],
            ),
        ],
    )

    payload = public_listing_payload(item)

    assert payload["plate_number"] == "ABC-***、DEF-***"
    assert "ABC-123" not in str(payload)
    assert "DEF-456" not in str(payload)


def test_public_feed_redacts_identifier_leaks_from_text_urls_and_media():
    item = record(
        source_record_id="VINSECRET12345678",
        official_url="https://shwoo.gov.taipei/item/VINSECRET12345678?plate=ABC-123",
        official_title="車牌 ABC-123、引擎號碼 EN99887766",
        official_case_number="ABC-123",
        location="洽詢 02-12345678",
        fee_notes=["車身號碼 FR12345678", "owner@example.com"],
        identifiers=[
            VehicleIdentifier(identifier_type="PLATE", normalized_value="ABC123", original_value="ABC-123"),
            VehicleIdentifier(identifier_type="ENGINE", normalized_value="EN99887766", original_value="EN99887766"),
            VehicleIdentifier(identifier_type="FRAME", normalized_value="FR12345678", original_value="FR12345678"),
            VehicleIdentifier(identifier_type="VIN", normalized_value="VINSECRET12345678", original_value="VINSECRET12345678"),
        ],
        photo_urls=[
            "https://shwoo.gov.taipei/images/VINSECRET12345678.jpg",
            "https://shwoo.gov.taipei/images/public-photo.jpg",
        ],
    )

    payload = public_listing_payload(item)
    serialized = str(payload)

    assert payload["source_record_id"].startswith("redacted-")
    assert payload["official_url"] == "https://shwoo.gov.taipei/"
    assert payload["official_title"] == "車牌 ABC-***、引擎號碼 車輛識別碼已隱藏"
    assert payload["official_case_number"] == "ABC-***"
    assert payload["location"] == "洽詢 聯絡電話已隱藏"
    assert payload["fee_notes"] == ["車身號碼 車輛識別碼已隱藏", "聯絡信箱已隱藏"]
    assert payload["photo_urls"] == []
    for private_value in ("ABC-123", "EN99887766", "FR12345678", "VINSECRET12345678", "02-12345678", "owner@example.com"):
        assert private_value not in serialized


@pytest.mark.parametrize(
    "synthetic_phone",
    [
        "02-123-4567",
        "02-1234-5678",
        "(02) 1234-5678",
        "02 1234 5678",
        "02－123－4567",
        "02–123–4567",
    ],
)
def test_public_feed_redacts_split_landlines_in_every_public_text_field(synthetic_phone: str) -> None:
    item = record(
        identifiers=[],
        official_title=f"公告洽詢 {synthetic_phone}",
        official_case_number=f"案號備註 {synthetic_phone}",
        organization=f"承辦單位 {synthetic_phone}",
        brand=f"廠牌備註 {synthetic_phone}",
        model=f"型號備註 {synthetic_phone}",
        color=f"顏色備註 {synthetic_phone}",
        location=f"洽詢 {synthetic_phone}",
        fee_notes=[f"費用洽詢 {synthetic_phone}"],
    )

    payload = public_listing_payload(item, source_name=f"來源 {synthetic_phone}")

    for field in (
        "source_name", "official_title", "official_case_number", "organization_name",
        "brand_name", "model_name", "color", "location",
    ):
        assert "聯絡電話已隱藏" in payload[field]
    assert payload["fee_notes"] == ["費用洽詢 聯絡電話已隱藏"]
    assert synthetic_phone not in str(payload)


def test_public_feed_rejects_split_landline_in_source_id_and_official_links() -> None:
    synthetic_phone = "(02) 1234 5678"
    encoded_phone = "%2802%29%201234%205678"
    item = record(
        identifiers=[],
        source_record_id=f"notice-{synthetic_phone}",
        official_url=f"https://shwoo.gov.taipei/item?contact={encoded_phone}",
        evidence=[EvidenceRef(
            field_name="official_attachment_url",
            normalized_value=f"https://shwoo.gov.taipei/file/notice.pdf?contact={encoded_phone}",
            source_text="合成測試附件",
        )],
    )

    payload = public_listing_payload(item)

    assert payload["source_record_id"].startswith("redacted-")
    assert payload["official_url"] == "https://shwoo.gov.taipei/"
    assert payload["documents"] == []
    assert synthetic_phone not in str(payload)
    assert encoded_phone not in str(payload)


def test_public_feed_preserves_dates_prices_and_existing_contiguous_phone_redaction() -> None:
    item = record(
        identifiers=[],
        official_title="115-09-25 公告；2026/09/25 拍賣；底價 NT$18,000",
        location="聯絡 02-12345678",
    )

    payload = public_listing_payload(item)

    assert payload["official_title"] == "115-09-25 公告；2026/09/25 拍賣；底價 NT$18,000"
    assert payload["location"] == "聯絡 聯絡電話已隱藏"


def test_public_feed_masks_plate_like_text_even_if_source_parser_missed_the_identifier():
    unparsed_plate = "KSS–7890"
    item = record(
        identifiers=[],
        source_record_id=f"notice-{unparsed_plate}",
        official_url="https://www.tcy.moj.gov.tw/notice/KSS%E2%80%937890/post",
        official_title=f"普通重型機車拍賣，車牌 {unparsed_plate}；115-08-01 公告",
        official_case_number=f"車牌 {unparsed_plate}",
        evidence=[EvidenceRef(
            field_name="official_attachment_url",
            normalized_value="https://www.tcy.moj.gov.tw/media/KSS%E2%80%937890.pdf",
            source_text="官方附件",
        )],
    )

    payload = public_listing_payload(item, source_adapter="moj_enforcement_cms")

    assert payload["source_record_id"].startswith("redacted-")
    assert payload["official_url"] == "https://www.tcy.moj.gov.tw/"
    assert payload["official_title"] == "普通重型機車拍賣，車牌 已隱藏；115-08-01 公告"
    assert payload["official_case_number"] == "車牌 已隱藏"
    assert payload["plate_number"] is None
    assert payload["documents"] == []
    assert unparsed_plate not in str(payload)


@pytest.mark.parametrize(
    ("label", "plate"),
    [
        ("車牌", "123-4567"),
        ("車牌", "ABC1234"),
        ("牌照號碼", "1234567"),
        ("車號", "AB-1234"),
    ],
)
def test_public_feed_suppresses_labeled_unparsed_plates_everywhere(label: str, plate: str):
    item = record(
        identifiers=[], ends_at=None,
        source_record_id=f"notice-{plate}",
        official_url=f"https://www.tcy.moj.gov.tw/notice/{plate}/post",
        official_title=f"普通重型機車拍賣，{label}：{plate}",
        official_case_number=f"{label} {plate}",
        location=f"保管地點，{label}為{plate}",
        evidence=[EvidenceRef(
            field_name="official_attachment_url",
            normalized_value=f"https://www.tcy.moj.gov.tw/media/{plate}.pdf",
            source_text="官方附件",
        )],
    )

    payload = public_listing_payload(item, source_adapter="moj_enforcement_cms")

    assert payload["source_record_id"].startswith("redacted-")
    assert payload["official_url"] == "https://www.tcy.moj.gov.tw/"
    assert payload["documents"] == []
    assert payload["plate_number"] is None
    assert "已隱藏" in payload["official_title"]
    assert plate not in str(payload)


def test_public_feed_suppresses_unlabeled_compact_plate_in_public_text() -> None:
    item = record(
        identifiers=[], ends_at=None,
        source_record_id="notice-ABC1234",
        official_url="https://www.tcy.moj.gov.tw/notice/ABC1234/post",
        official_title="普通重型機車 ABC1234 動產拍賣",
        official_case_number="ABC1234",
        description="標的為機車 ABC1234，完整來源說明不應公開。",
        fee_notes=["相關費用請查 ABC1234 公告"],
    )

    payload = public_listing_payload(item, source_adapter="moj_enforcement_cms")

    assert payload["source_record_id"].startswith("redacted-")
    assert payload["official_url"] == "https://www.tcy.moj.gov.tw/"
    assert payload["official_title"] == "普通重型機車 已隱藏 動產拍賣"
    assert payload["official_case_number"] == "已隱藏"
    assert payload["description"] is None
    assert payload["fee_notes"] == ["相關費用請查 已隱藏 公告"]
    assert payload["plate_number"] is None
    assert "ABC1234" not in str(payload)


def test_public_feed_projects_only_safe_official_attachment_links_without_evidence_text():
    item = record(
        identifiers=[
            VehicleIdentifier(identifier_type="PLATE", normalized_value="ABC123", original_value="ABC-123"),
            VehicleIdentifier(identifier_type="ENGINE", normalized_value="EN99887766", original_value="EN99887766"),
        ],
        evidence=[
            EvidenceRef(
                field_name="official_attachment_url",
                normalized_value="https://web.customs.gov.tw/download/auction-notice.pdf",
                source_text="完整附件名稱與證據全文不應公開",
            ),
            EvidenceRef(
                field_name="official_attachment_url",
                normalized_value="https://web.customs.gov.tw/download/ABC-123.pdf",
                source_text="車牌出現在網址",
            ),
            EvidenceRef(
                field_name="official_attachment_url",
                normalized_value="https://web.customs.gov.tw/download/EN99887766.pdf",
                source_text="引擎號碼出現在網址",
            ),
            EvidenceRef(
                field_name="official_attachment_url",
                normalized_value="https://web.customs.gov.tw/download/JH4KA9650MC000001.pdf",
                source_text="VIN 出現在網址",
            ),
            EvidenceRef(
                field_name="official_attachment_url",
                normalized_value="http://web.customs.gov.tw/download/insecure.pdf",
                source_text="非 HTTPS",
            ),
            EvidenceRef(
                field_name="official_attachment_url",
                normalized_value="https://example.com/not-official.pdf",
                source_text="非官方網域",
            ),
        ],
    )

    payload = public_listing_payload(item)

    assert payload["documents"] == [
        {"label": "官方附件", "url": "https://web.customs.gov.tw/download/auction-notice.pdf"}
    ]
    assert "完整附件名稱與證據全文不應公開" not in str(payload)
    assert "ABC-123.pdf" not in str(payload)
    assert "EN99887766.pdf" not in str(payload)
    assert "JH4KA9650MC000001.pdf" not in str(payload)


def test_public_feed_redacts_personal_data_and_drops_personal_urls() -> None:
    item = record(
        source_record_id="notice-a123456789",
        official_url="https://www.tcy.moj.gov.tw/post/%E7%BE%A9%E5%8B%99%E4%BA%BA%E7%8E%8B%E5%B0%8F%E6%98%8E",
        official_title="義務人：王小明 A123456789 普通重型機車",
        official_case_number="債務人陳大華，證號 a123456789",
        location="保管人：林小玉 0912-345-678",
        fee_notes=["車主李四應繳費", "聯絡 service@example.com"],
        evidence=[
            EvidenceRef(
                field_name="official_attachment_url",
                normalized_value="https://www.tcy.moj.gov.tw/files/%E5%8F%97%E5%88%91%E4%BA%BA%E9%99%B3%E5%A4%A7%E8%8F%AF.pdf",
                source_text="受刑人姓名附件",
            ),
            EvidenceRef(
                field_name="official_attachment_url",
                normalized_value="https://www.tcy.moj.gov.tw/files/public-notice.pdf",
                source_text="公開附件",
            ),
        ],
    )

    payload = public_listing_payload(item, source_adapter="moj_enforcement_cms")
    serialized = str(payload)

    assert payload["source_record_id"].startswith("redacted-")
    assert payload["official_url"] == "https://www.tcy.moj.gov.tw/"
    assert payload["official_title"] == "義務人：已隱去 身分證字號已隱去 普通重型機車"
    assert payload["official_case_number"] == "債務人：已隱去，證號 身分證字號已隱去"
    assert payload["location"] == "保管人：已隱去 聯絡電話已隱藏"
    assert payload["fee_notes"] == ["車主：已隱去應繳費", "聯絡 聯絡信箱已隱藏"]
    assert payload["documents"] == [
        {"label": "官方附件", "url": "https://www.tcy.moj.gov.tw/files/public-notice.pdf"}
    ]
    for private_value in ("王小明", "陳大華", "林小玉", "李四", "A123456789", "a123456789"):
        assert private_value not in serialized


@pytest.mark.parametrize("source_adapter", ["shwoo", "moj_auction", "moj_enforcement_cms", "customs"])
def test_public_feed_does_not_publish_unlicensed_official_photos(source_adapter: str) -> None:
    assert public_listing_payload(record(), source_adapter=source_adapter)["photo_urls"] == []


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
    assert payload["vehicle_type"] == "MIXED"
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


def test_public_feed_exposes_explicit_car_family_and_category():
    item = record(
        official_title="自用小客車拍賣公告", vehicle_type=VehicleType.CAR,
        car_category=CarCategory.PASSENGER, brand="TOYOTA", model="ALTIS", displacement_cc=1798,
    )
    payload = public_listing_payload(item, source_adapter="moj_auction", source_name="法務部查扣物集中拍賣")

    assert payload["vehicle_type"] == "CAR"
    assert payload["car_category"] == "PASSENGER"
    assert payload["vehicle_category"] == "UNKNOWN"
    assert payload["brand_name"] == "TOYOTA"


@pytest.mark.asyncio
async def test_partial_public_run_does_not_advance_last_successful_time() -> None:
    publisher = object.__new__(SupabasePublicPublisher)
    publisher.source_id = "source-id"
    publisher.run_id = "run-id"
    publisher.headers = {}
    calls: list[tuple[str, str, dict]] = []

    async def fake_json(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))

    publisher._json = fake_json
    result = SyncResult(source="moj_auction", discovered=29, fetched=29, parsed=29, changed=3, failed=3)

    await publisher.finish(result)

    source_patch = next(call for call in calls if call[1].startswith("/rest/v1/sources"))
    assert source_patch[2]["json"]["status"] == "PARTIAL"
    assert "last_successful_at" not in source_patch[2]["json"]


@pytest.mark.asyncio
async def test_zero_discovery_public_run_remains_partial() -> None:
    publisher = object.__new__(SupabasePublicPublisher)
    publisher.source_id = "source-id"
    publisher.run_id = "run-id"
    publisher.headers = {}
    calls: list[tuple[str, str, dict]] = []

    async def fake_json(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))

    publisher._json = fake_json
    result = SyncResult(source="moj_auction", discovered=0, fetched=0, parsed=0, changed=0, failed=0)

    await publisher.finish(result)

    run_patch = next(call for call in calls if call[1].startswith("/rest/v1/sync_runs"))
    source_patch = next(call for call in calls if call[1].startswith("/rest/v1/sources"))
    assert run_patch[2]["json"]["status"] == "PARTIAL"
    assert source_patch[2]["json"]["status"] == "PARTIAL"
    assert "last_successful_at" not in source_patch[2]["json"]


@pytest.mark.asyncio
async def test_publisher_clears_only_expired_public_plate_projection() -> None:
    publisher = object.__new__(SupabasePublicPublisher)
    publisher.headers = {"Authorization": "Bearer test"}
    calls: list[tuple[str, str, dict]] = []

    async def fake_json(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))

    publisher._json = fake_json
    await publisher._enforce_public_plate_retention(datetime(2026, 8, 21, 12, 0, tzinfo=UTC))

    assert calls == [(
        "PATCH",
        "/rest/v1/public_live_motorcycle_listings"
        "?plate_number=not.is.null&or=(ends_at.is.null,ends_at.lt.2026-07-22T12%3A00%3A00%2B00%3A00)",
        {
            "headers": {"Authorization": "Bearer test", "Prefer": "return=minimal"},
            "json": {"plate_number": None},
        },
    )]


@pytest.mark.asyncio
async def test_plate_cleanup_failure_prevents_successful_run_status() -> None:
    publisher = object.__new__(SupabasePublicPublisher)
    publisher.source_id = "source-id"
    publisher.run_id = "run-id"
    publisher.headers = {}
    calls: list[tuple[str, str, dict]] = []

    async def fake_json(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))
        if path.startswith("/rest/v1/public_live_motorcycle_listings"):
            raise RuntimeError("HTTP 503")

    publisher._json = fake_json
    result = SyncResult(source="pcc", discovered=4, fetched=4, parsed=4, changed=1, failed=0)

    await publisher.finish(result)

    run_patch = next(call for call in calls if call[1].startswith("/rest/v1/sync_runs"))
    source_patch = next(call for call in calls if call[1].startswith("/rest/v1/sources"))
    assert result.failed == 1
    assert result.warnings == ["Public plate retention cleanup failed: HTTP 503"]
    assert run_patch[2]["json"]["status"] == "PARTIAL"
    assert run_patch[2]["json"]["failed_count"] == 1
    assert source_patch[2]["json"]["status"] == "PARTIAL"
    assert "last_successful_at" not in source_patch[2]["json"]
