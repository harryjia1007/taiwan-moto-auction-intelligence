import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import pytest

from ingest.models import BidEligibility, DiscoveredItem, FourState, RawArtifact, RegistrationStatus, VehicleClass
from ingest.parser import motorcycle_class_from_official_text, parse_judicial_record, parse_pcc_detail, parse_shwoo_detail, roc_compact_date, roc_datetime

FIXTURES = Path(__file__).parent / "fixtures"


def artifact(name: str) -> RawArtifact:
    content = (FIXTURES / name).read_bytes()
    return RawArtifact(
        official_url=f"https://shwoo.gov.taipei/{name}", fetched_at=datetime.fromisoformat("2026-08-09T00:00:00+00:00"),
        mime_type="text/html", filename=name, content=content, checksum_sha256=sha256(content).hexdigest(),
    )


def item(auid: str = "939528", recycler: bool = False) -> DiscoveredItem:
    return DiscoveredItem(
        source_record_id=auid,
        official_url=f"https://shwoo.gov.taipei/shwoo/newproduct/newproduct00/product?AUID={auid}",
        title="機車", discovery_url="https://shwoo.gov.taipei/shwoo/browse/browse00/", recycler_only=recycler,
    )


def pcc_item(primary_key: str, title: str) -> DiscoveredItem:
    return DiscoveredItem(
        source_record_id=primary_key,
        official_url=f"https://web.pcc.gov.tw/opas/aspam/public/readOneAspamDetailOld?pk={primary_key}",
        title=title,
        discovery_url="https://web.pcc.gov.tw/opas/aspam/public/readAspam?searchAssetsName=%E6%A9%9F%E8%BB%8A",
    )


def test_roc_date_conversion() -> None:
    value = roc_datetime("115/08/12 12:00:00")
    assert value is not None
    assert value.isoformat() == "2026-08-12T12:00:00+08:00"


def test_judicial_compact_roc_date_conversion() -> None:
    value = roc_compact_date("1150819")
    assert value is not None
    assert (value.year, value.month, value.day) == (2026, 8, 19)


@pytest.mark.parametrize(
    ("official_text", "expected"),
    [
        ("普通輕型機車一輛", VehicleClass.ORDINARY_LIGHT),
        ("普通重型機車一輛", VehicleClass.ORDINARY_HEAVY),
        ("大型重型機車一輛", VehicleClass.LARGE_HEAVY),
        ("大型重機一部", VehicleClass.LARGE_HEAVY),
        ("電動機車一輛", VehicleClass.ELECTRIC_MOTORCYCLE),
        ("重型機車一輛", VehicleClass.HEAVY_UNSPECIFIED),
        ("排氣量 124cc 機車一輛", VehicleClass.UNKNOWN),
    ],
)
def test_motorcycle_class_requires_explicit_official_wording(official_text: str, expected: VehicleClass) -> None:
    assert motorcycle_class_from_official_text(official_text)[0] == expected


def test_judicial_structured_record_preserves_unknown_price_and_exact_identity() -> None:
    content = (FIXTURES / "judicial_motorcycle.json").read_bytes()
    judicial_item = DiscoveredItem(
        source_record_id="TEST-ROW-001",
        official_url="https://www.judicial.gov.tw/tw/lp-85-1.html",
        title="合成普通重型機車",
        discovery_url="https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02.htm",
    )
    source = RawArtifact(
        official_url=judicial_item.official_url,
        fetched_at=datetime.fromisoformat("2026-08-09T00:00:00+00:00"),
        mime_type="application/json",
        filename="judicial.json",
        content=content,
        checksum_sha256=sha256(content).hexdigest(),
    )
    record = parse_judicial_record(judicial_item, source)
    assert record.organization == "臺灣臺北地方法院"
    assert record.official_case_number == "115司執字第000001號（合成測試）"
    assert record.auction_round == 1
    assert record.reserve_price is None
    assert record.brand == "YAMAHA"
    assert record.model == "XC100M"
    assert record.manufacture_year == 2011
    assert record.manufacture_month == 12
    assert record.displacement_cc == 101
    assert record.registration_status == RegistrationStatus.UNKNOWN
    assert record.can_start == FourState.UNKNOWN
    assert all(ref.extraction_method == "STRUCTURED" for ref in record.evidence)


def test_judicial_unlabelled_brand_and_compact_manufacture_date() -> None:
    row = {
        "rowid": 854459, "filenm": "/tcd/example.pdf", "saledate": "1150819", "saleno": "1",
        "ttitle": "「721-GWL」普通重型機車", "registeno": "「721-GWL」普通重型機車", "qty": "1",
        "notes": "光陽牌；型式：SJ25HE；排氣量：124CC；出廠年月：200912。", "sumprice": 0,
        "crtnm": "臺灣臺中地方法院", "crm": "115司執字第038541號", "pic_cnt": 0,
    }
    content = json.dumps(row, ensure_ascii=False).encode()
    judicial_item = DiscoveredItem(
        source_record_id="854459",
        official_url="https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02/DO_VIEWPDF.htm?filenm=x.pdf",
        title=row["ttitle"],
        discovery_url="https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02.htm",
    )
    source = RawArtifact(
        official_url=judicial_item.official_url, fetched_at=datetime.fromisoformat("2026-08-09T00:00:00+00:00"),
        mime_type="application/json", content=content, checksum_sha256=sha256(content).hexdigest(),
    )
    record = parse_judicial_record(judicial_item, source)
    assert record.brand == "KYMCO"
    assert record.model == "SJ25HE"
    assert (record.manufacture_year, record.manufacture_month) == (2009, 12)
    assert next(identifier for identifier in record.identifiers if identifier.identifier_type == "PLATE").original_value == "721-GWL"


def test_single_motorcycle_preserves_unknown_semantics() -> None:
    record = parse_shwoo_detail(item(), artifact("shwoo_single.html"))
    assert record.official_case_number == "115Y431240018"
    assert record.brand == "三陽牌"
    assert record.model == "HM12VB"
    assert record.reserve_price == 2000
    assert record.current_price == 4300
    assert record.registration_status == RegistrationStatus.RE_REGISTRATION_REQUIRED
    assert record.has_key == FourState.UNKNOWN
    assert record.can_start == FourState.NO
    assert record.can_test == FourState.YES  # static testing is explicitly offered
    assert record.tax_arrears == FourState.NO
    assert record.fine_arrears == FourState.NO
    assert record.fuel_fee_arrears == FourState.UNKNOWN
    assert {identifier.identifier_type for identifier in record.identifiers} == {"PLATE", "ENGINE", "FRAME"}
    assert record.photo_urls


def test_bulk_listing_creates_separable_vehicle_units() -> None:
    record = parse_shwoo_detail(item("939611", recycler=True), artifact("shwoo_bulk_recycler.html"))
    assert record.lot_size == 7
    assert record.bulk_lot is True
    assert record.eligibility == BidEligibility.LICENSED_RECYCLER_ONLY
    assert len(record.vehicle_units) == 7
    assert record.vehicle_units[0].identifiers[0].normalized_value == "TST1001"


def test_conflicting_official_statements_are_not_silently_resolved() -> None:
    record = parse_shwoo_detail(item("1"), artifact("shwoo_conflicting.html"))
    assert record.registration_status == RegistrationStatus.REGISTRABILITY_UNKNOWN
    assert record.has_key == FourState.CONFLICTING
    assert record.can_start == FourState.CONFLICTING


def test_reprocessing_is_deterministic() -> None:
    first = parse_shwoo_detail(item(), artifact("shwoo_single.html"))
    second = parse_shwoo_detail(item(), artifact("shwoo_single.html"))
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_pcc_court_disposal_is_not_mislabeled_as_judicial_execution() -> None:
    source = artifact("pcc_court_scrap.html")
    source.official_url = "https://web.pcc.gov.tw/opas/aspam/public/readOneAspamDetailOld?pk=70020198"
    record = parse_pcc_detail(pcc_item("70020198", "標售本院115年奉准報廢機車"), source)
    assert record.organization == "臺灣花蓮地方法院"
    assert record.official_case_number == "HLD11508191"
    assert record.reserve_price == 800
    assert record.deposit == 0
    assert record.eligibility == BidEligibility.LICENSED_RECYCLER_ONLY
    assert record.registration_status == RegistrationStatus.SCRAP_ONLY
    assert record.disposal_origin == "SCRAP_DISPOSAL"
    assert record.bulk_lot is True  # The official page does not separate vehicle identities.


def test_pcc_impounded_batch_preserves_count_and_origin() -> None:
    source = artifact("pcc_impounded.html")
    source.official_url = "https://web.pcc.gov.tw/opas/aspam/public/readOneAspamDetailOld?pk=70020257"
    record = parse_pcc_detail(pcc_item("70020257", "逾期未領回汽機車"), source)
    assert record.disposal_origin == "IMPOUNDED_UNCLAIMED"
    assert record.lot_size == 4
    assert record.bulk_lot is True
    assert record.reserve_price == 134000
    assert record.deposit == 2500
    assert record.vehicle_units == []


def test_fee_and_deadline_fields_are_evidenced() -> None:
    source = artifact("shwoo_single.html")
    changed = source.content.decode().replace(
        "</table>",
        "<tr><td>押標金</td><td>新台幣 1,000 元</td></tr>"
        "<tr><td>付款期限</td><td>115/08/20 17:00</td></tr>"
        "<tr><td>領取期限</td><td>115/08/25 12:00</td></tr></table>",
    ).replace("</div><h2>其他條款", "六、過戶費由得標人負擔。</div><h2>其他條款")
    source.content = changed.encode()
    record = parse_shwoo_detail(item(), source)
    assert record.deposit == 1000
    assert record.payment_deadline and record.payment_deadline.year == 2026
    assert record.pickup_deadline and record.pickup_deadline.day == 25
    assert record.fee_notes == ["六、過戶費由得標人負擔"]
    assert {evidence.field_name for evidence in record.evidence} >= {"deposit", "payment_deadline", "pickup_deadline"}


@pytest.mark.parametrize("missing", ["廠牌：三陽牌", "型號：HM12VB", "牌照異動登記：已繳銷(可再領牌)"])
def test_missing_fields_remain_missing(missing: str) -> None:
    original = artifact("shwoo_single.html")
    changed = original.content.decode().replace(missing, "")
    original.content = changed.encode()
    record = parse_shwoo_detail(item(), original)
    if missing.startswith("廠牌"):
        assert record.brand is None
    elif missing.startswith("型號"):
        assert record.model is None
    else:
        assert record.registration_status in {RegistrationStatus.RE_REGISTRATION_REQUIRED, RegistrationStatus.UNKNOWN}
