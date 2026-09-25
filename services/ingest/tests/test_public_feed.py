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


@pytest.mark.parametrize(
    ("plate", "masked"),
    [
        ("ABC-123", "ABC-***"),
        ("AB-12", "AB-**"),
        ("1234-AB", "1234-**"),
        ("ABC123", "ABC***"),
        ("ABC-123 等 2 面", "ABC-*** 等 2 面"),
        ("ＡＢＣ－１２３", "ABC-***"),
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


def test_public_feed_redacts_plate_tokens_even_when_parser_misses_identifier() -> None:
    item = record(
        identifiers=[],
        source_record_id="ABC-123",
        official_url="https://shwoo.gov.taipei/item/ABC-123?plate=DEF-456",
        official_title="普通重型機車 ABC-123",
        official_case_number="車牌 DEF-456",
        fee_notes=["車牌 GHI-789，另查證", "車牌 ＪＫＬ－３５７，另查證"],
    )

    payload = public_listing_payload(item)

    assert payload["source_record_id"].startswith("redacted-")
    assert payload["official_url"] == "https://shwoo.gov.taipei/"
    assert payload["official_title"] == "普通重型機車 ABC-***"
    assert payload["official_case_number"] == "車牌 DEF-***"
    assert payload["fee_notes"] == ["車牌 GHI-***，另查證", "車牌 JKL-***，另查證"]
    assert payload["plate_number"] is None
    for complete_plate in ("ABC-123", "DEF-456", "GHI-789", "ＪＫＬ－３５７"):
        assert complete_plate not in str(payload)


def test_public_feed_redacts_unhyphenated_labeled_plate_without_identifier() -> None:
    payload = public_listing_payload(record(
        identifiers=[],
        source_record_id="ABC123",
        official_url="https://shwoo.gov.taipei/item/123?plate=ABC123",
        official_title="車牌 ABC123 普通重型機車",
    ))

    assert payload["source_record_id"].startswith("redacted-")
    assert payload["official_url"] == "https://shwoo.gov.taipei/"
    assert payload["official_title"] == "車牌 ABC*** 普通重型機車"
    assert "ABC123" not in str(payload)


def test_public_feed_falls_back_when_official_url_host_does_not_match_source() -> None:
    item = record(official_url="https://web.customs.gov.tw/auction/123")

    assert public_listing_payload(item, source_adapter="shwoo")["official_url"] == "https://shwoo.gov.taipei/"


def test_public_feed_preserves_reviewed_moj_detail_hosts() -> None:
    item = record(official_url="https://www.tcc.moj.gov.tw/12345/post")

    assert public_listing_payload(item, source_adapter="moj_auction")["official_url"] == "https://www.tcc.moj.gov.tw/12345/post"


@pytest.mark.parametrize(
    "url",
    [
        "http://shwoo.gov.taipei/shwoo/item/123",
        "https://reader@shwoo.gov.taipei/shwoo/item/123",
        "https://shwoo.gov.taipei:8443/shwoo/item/123",
    ],
)
def test_public_feed_falls_back_for_unsafe_official_url(url: str) -> None:
    item = record(official_url=url)

    assert public_listing_payload(item, source_adapter="shwoo")["official_url"] == "https://shwoo.gov.taipei/"


def test_public_feed_unknown_source_uses_project_fallback_instead_of_arbitrary_url() -> None:
    item = record(official_url="https://attacker.example/case")

    assert public_listing_payload(item, source_adapter="unknown")["official_url"] == (
        "https://harryjia.com/projects/taiwan-moto-auction/"
    )


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

    payload = public_listing_payload(item, source_adapter="customs")

    assert payload["documents"] == [
        {"label": "官方完整全文", "url": "https://web.customs.gov.tw/download/auction-notice.pdf"}
    ]
    assert "完整附件名稱與證據全文不應公開" not in str(payload)
    assert "ABC-123.pdf" not in str(payload)
    assert "EN99887766.pdf" not in str(payload)
    assert "JH4KA9650MC000001.pdf" not in str(payload)


def test_public_feed_rejects_document_source_host_mismatch() -> None:
    item = record(evidence=[
        EvidenceRef(
            field_name="official_attachment_url",
            normalized_value="https://web.customs.gov.tw/download/auction-notice.pdf",
            source_text="海關官方附件",
        ),
    ])

    assert public_listing_payload(item, source_adapter="shwoo")["documents"] == []


def test_public_feed_projects_judicial_official_pdf_without_duplicate_evidence() -> None:
    official_url = (
        "https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02/"
        "DO_VIEWPDF.htm?filenm=auction-notice.pdf"
    )
    item = record(official_url=official_url, evidence=[])

    assert public_listing_payload(item, source_adapter="judicial")["documents"] == [
        {"label": "官方完整全文", "url": official_url}
    ]


def test_public_feed_projects_judicial_main_site_notice_and_link_only_full_text() -> None:
    detail_url = "https://www.judicial.gov.tw/tw/cp-1913-12345-a1b2c3d4.html"
    document_url = "https://www.judicial.gov.tw/tw/dl-54321-01234567-89ab-cdef-0123-456789abcdef.html"
    item = record(
        official_url=detail_url,
        evidence=[
            EvidenceRef(
                field_name="official_attachment_url",
                normalized_value=document_url,
                source_text="附件下載",
            )
        ],
    )

    payload = public_listing_payload(item, source_adapter="judicial_notices")

    assert payload["official_url"] == detail_url
    assert payload["documents"] == [{"label": "官方完整全文", "url": document_url}]
    assert payload["photo_urls"] == []


def test_public_feed_projects_validated_cached_moj_pdf_artifact() -> None:
    official_url = "https://auction.moj.gov.tw/media/auction-notice.pdf"

    assert public_listing_payload(
        record(evidence=[]),
        source_adapter="moj_auction",
        artifact_document_urls=(official_url,),
    )["documents"] == [{"label": "官方完整全文", "url": official_url}]


@pytest.mark.parametrize(
    "url",
    [
        "https://reader@web.customs.gov.tw/download/auction-notice.pdf",
        "https://web.customs.gov.tw:8443/download/auction-notice.pdf",
    ],
)
def test_public_feed_rejects_document_userinfo_and_nonstandard_port(url: str) -> None:
    item = record(evidence=[
        EvidenceRef(
            field_name="official_attachment_url",
            normalized_value=url,
            source_text="不安全的附件網址",
        ),
    ])

    assert public_listing_payload(item, source_adapter="customs")["documents"] == []


def test_public_feed_rejects_documents_from_unknown_source() -> None:
    item = record(evidence=[
        EvidenceRef(
            field_name="official_attachment_url",
            normalized_value="https://web.customs.gov.tw/download/auction-notice.pdf",
            source_text="未知 adapter 不可繼承其他來源的 allowlist",
        ),
    ])

    assert public_listing_payload(item, source_adapter="unknown")["documents"] == []


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
                normalized_value="https://www.tcy.moj.gov.tw/media/public-notice.pdf",
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
        {"label": "官方完整全文", "url": "https://www.tcy.moj.gov.tw/media/public-notice.pdf"}
    ]
    for private_value in ("王小明", "陳大華", "林小玉", "李四", "A123456789", "a123456789"):
        assert private_value not in serialized


@pytest.mark.parametrize(
    ("official_title", "private_value", "expected_fragment"),
    [
        ("拍賣債務人王小明所有普通重型機車", "王小明", "債務人：已隱去所有普通重型機車"),
        ("債務人王小明名下機車", "王小明", "債務人：已隱去名下機車"),
        ("拍賣債務人 JOHN CHEN 所有汽車", "JOHN CHEN", "債務人：已隱去 所有汽車"),
        ("車主：王小明未提供其他欄位", "王小明", "車主：已隱去"),
    ],
)
def test_public_feed_role_labelled_names_fail_closed_across_common_suffixes(
    official_title: str,
    private_value: str,
    expected_fragment: str,
) -> None:
    payload = public_listing_payload(record(official_title=official_title))

    assert private_value not in str(payload)
    assert expected_fragment in payload["official_title"]


def test_public_feed_redacts_more_taiwan_contact_and_identity_formats() -> None:
    item = record(
        official_title="車主：JOHN CHEN，證號 Ａ１２３４５６７８９",
        location="聯絡 +886 912-345-678 或 (02) 1234-5678 ext. 9",
        fee_notes=["CASE.OWNER+AUCTION@example.com"],
    )

    serialized = str(public_listing_payload(item))

    for private_value in (
        "JOHN CHEN",
        "Ａ１２３４５６７８９",
        "+886 912-345-678",
        "(02) 1234-5678",
        "CASE.OWNER+AUCTION@example.com",
    ):
        assert private_value not in serialized


def test_public_feed_redacts_more_role_names_and_labeled_identity_documents() -> None:
    item = record(
        official_title="債權人：王小明；聯絡人 JOHN DOE",
        official_case_number="居留證號：AB12345678",
        fee_notes=["護照號碼：P123456789", "拍定人陳大華名下車輛"],
    )

    serialized = str(public_listing_payload(item))

    for private_value in (
        "王小明",
        "JOHN DOE",
        "AB12345678",
        "P123456789",
        "陳大華",
    ):
        assert private_value not in serialized


def test_public_feed_rejects_nested_percent_encoded_personal_url() -> None:
    encoded_twice = (
        "https://www.tcy.moj.gov.tw/post/"
        "%25E5%2582%25B5%25E5%258B%2599%25E4%25BA%25BA%25E7%258E%258B%25E5%25B0%258F%25E6%2598%258E"
    )
    payload = public_listing_payload(
        record(official_url=encoded_twice),
        source_adapter="moj_enforcement_cms",
    )

    assert payload["official_url"] == "https://www.tcy.moj.gov.tw/"


def test_public_feed_redacts_labeled_private_address_but_keeps_official_storage_location() -> None:
    item = record(
        official_title="車輛拍賣；債務人戶籍地址：臺北市大安區安全路 123 號 4 樓",
        location="車輛保管地點：臺灣士林地方法院公務倉庫",
        fee_notes=["送達地址：新北市某區某路 88 號"],
    )

    payload = public_listing_payload(item)

    assert payload["official_title"] == "車輛拍賣；戶籍地址：已隱去"
    assert payload["location"] == "車輛保管地點：臺灣士林地方法院公務倉庫"
    assert payload["fee_notes"] == ["送達地址：已隱去"]
    assert "安全路" not in str(payload)
    assert "某路" not in str(payload)


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


def test_public_feed_does_not_reclassify_a_known_car_from_incidental_motorcycle_terms():
    item = record(
        official_title="自用小客車拍賣公告",
        description="現場另有機車停車區；本標的為汽車 1 輛",
        vehicle_type=VehicleType.CAR,
        car_category=CarCategory.PASSENGER,
        brand="TOYOTA",
        model="ALTIS",
        displacement_cc=1798,
    )

    payload = public_listing_payload(item, source_adapter="moj_auction")

    assert payload["vehicle_type"] == "CAR"
    assert payload["bulk_lot"] is False
    assert payload["brand_name"] == "TOYOTA"
    assert payload["model_name"] == "ALTIS"
    assert payload["displacement_cc"] == 1798


def test_public_feed_does_not_assign_shared_specs_to_separate_vehicles():
    item = record(
        official_title="普通重型機車 2 輛",
        vehicle_type=VehicleType.MOTORCYCLE,
        lot_size=2,
        bulk_lot=True,
        brand="SYM",
        model="未知歸屬的型號",
        manufacture_year=2021,
        manufacture_month=5,
        displacement_cc=150,
        color="黑色",
        mileage_km=12000,
        identifiers=[],
        vehicle_units=[
            ParsedVehicleUnit(
                source_vehicle_key="plate:AAA111",
                identifiers=[VehicleIdentifier(identifier_type="PLATE", normalized_value="AAA111", original_value="AAA-111")],
            ),
            ParsedVehicleUnit(
                source_vehicle_key="plate:BBB222",
                identifiers=[VehicleIdentifier(identifier_type="PLATE", normalized_value="BBB222", original_value="BBB-222")],
            ),
        ],
    )

    payload = public_listing_payload(item)

    assert payload["vehicle_type"] == "MOTORCYCLE"
    assert payload["bulk_lot"] is True
    assert payload["lot_size"] == 2
    assert payload["plate_number"] == "AAA-***、BBB-***"
    for field in ("brand_name", "model_name", "manufacture_year", "manufacture_month", "displacement_cc", "color", "mileage_km"):
        assert payload[field] is None


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
        if path.startswith("/rest/v1/source_access_policies"):
            return [{"decision": "ALLOW"}]

    publisher._json = fake_json
    result = SyncResult(source="moj_auction", discovered=29, fetched=29, parsed=29, changed=3, failed=3)

    await publisher.finish(result)

    source_patch = next(call for call in calls if call[1].startswith("/rest/v1/sources"))
    assert source_patch[2]["json"]["status"] == "PARTIAL"
    assert "last_successful_at" not in source_patch[2]["json"]


@pytest.mark.asyncio
async def test_zero_discovery_public_run_remains_partial() -> None:
    publisher = object.__new__(SupabasePublicPublisher)
    publisher.source_adapter = "moj_auction"
    publisher.source_name = "法務部查扣物集中拍賣"
    publisher.source_id = "source-id"
    publisher.run_id = "run-id"
    publisher.headers = {}
    calls: list[tuple[str, str, dict]] = []

    async def fake_json(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))
        if path.startswith("/rest/v1/source_access_policies"):
            return [{"decision": "ALLOW"}]

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
    publisher.source_adapter = "pcc"
    publisher.source_name = "政府電子採購網財物變賣"
    publisher.source_id = "source-id"
    publisher.run_id = "run-id"
    publisher.headers = {}
    calls: list[tuple[str, str, dict]] = []

    async def fake_json(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))
        if path.startswith(
            "/rest/v1/public_live_motorcycle_listings?plate_number=not.is.null"
        ):
            raise RuntimeError("HTTP 503")
        if path.startswith("/rest/v1/source_access_policies"):
            return [{"decision": "ALLOW"}]

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
