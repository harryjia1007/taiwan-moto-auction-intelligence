from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import httpx
import pytest

from ingest.adapters.base import SourceAccessDenied, SourceRateLimited
from ingest.adapters.judicial_notices import JudicialPublicNoticesAdapter, _roc_datetime
from ingest.models import AuctionStatus, FourState, RegistrationStatus, VehicleClass, VehicleType


FIXTURES = Path(__file__).parent / "fixtures"
TAIPEI = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=TAIPEI)


@pytest.mark.parametrize(
    ("source_text", "expected_hour"),
    [
        ("拍賣日期：115年9月25日下午2時30分", 14),
        ("拍賣日期：115年9月25日上午10時30分", 10),
        ("拍賣日期：115年9月25日14時30分", 14),
    ],
)
def test_roc_datetime_preserves_meridiem(source_text: str, expected_hour: int) -> None:
    assert _roc_datetime(source_text) == datetime(2026, 9, 25, expected_hour, 30, tzinfo=TAIPEI)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_vehicle_detail_semantics_ignore_car_company_names_in_real_estate_notices() -> None:
    assert not JudicialPublicNoticesAdapter._is_vehicle_auction_detail(
        "公告徵詢不動產優先承買事項",
        [
            "債權人某某汽車股份有限公司與債務人間強制執行事件",
            "旨揭不動產已拍定，限期表示是否優先應買",
        ],
    )


def test_vehicle_detail_semantics_accept_an_explicit_generic_car_lot() -> None:
    assert JudicialPublicNoticesAdapter._is_vehicle_auction_detail(
        "法院公告拍賣動產",
        ["拍賣標的：汽車一輛，廠牌及車牌詳如附表"],
    )


def test_vehicle_detail_semantics_accept_a_labeled_plate_without_guessing_from_company_names() -> None:
    assert JudicialPublicNoticesAdapter._is_vehicle_auction_detail(
        "法院公告拍賣動產",
        ["拍賣標的詳如附表；車牌：ABC-1234；現況點交"],
    )


def official_response(request: httpx.Request, contacted: list[str], posted: list[dict[str, list[str]]]) -> httpx.Response:
    contacted.append(f"{request.method} {request.url}")
    if request.url.path == "/robots.txt":
        return httpx.Response(
            200,
            text="User-agent: *\nDisallow: /tw/private/\n",
            headers={"content-type": "text/plain"},
        )
    if request.url.path == "/tw/lp-1913-1.html" and request.method == "GET":
        return httpx.Response(
            200,
            content=fixture("judicial_notices_search_form.html"),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    if request.url.path == "/tw/lp-1913-1.html" and request.method == "POST":
        posted.append(parse_qs(request.content.decode(), keep_blank_values=True))
        return httpx.Response(
            200,
            content=fixture("judicial_notices_search_results.html"),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    if request.url.path == "/tw/cp-1913-1600001-a1b2c-1.html":
        return httpx.Response(
            200,
            content=fixture("judicial_notices_vehicle_detail.html"),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    if request.url.path == "/tw/cp-1913-1600002-d4e5f-1.html":
        return httpx.Response(
            200,
            content=fixture("judicial_notices_irrelevant_detail.html"),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    raise AssertionError(f"unexpected request: {request.method} {request.url}")


@pytest.mark.asyncio
async def test_discovers_only_explicit_vehicle_auctions_and_never_contacts_blocked_portal() -> None:
    contacted: list[str] = []
    posted: list[dict[str, list[str]]] = []
    transport = httpx.MockTransport(lambda request: official_response(request, contacted, posted))
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = JudicialPublicNoticesAdapter(
            client=client,
            request_interval=0,
            now=lambda: NOW,
            search_queries=("機車",),
        )
        items = await adapter.discover()

    assert [item.source_record_id for item in items] == ["1600001-a1b2c"]
    assert items[0].metadata["discovery_method"] == "JUDICIAL_MAIN_OTHER_NOTICES"
    assert len(items[0].discovery_artifacts) == 1
    assert contacted[0] == "GET https://www.judicial.gov.tw/robots.txt"
    assert not any("aomp109" in url for url in contacted)
    assert not any("/tw/dl-" in url for url in contacted)
    assert posted[0]["Action"] == ["Qeury"]
    assert posted[0]["Q_DMBody"] == ["機車"]
    assert posted[0]["TBOXDMPostDateS"] == ["115/02/24"]
    assert posted[0]["TBOXDMPostDateE"] == ["115/08/23"]


@pytest.mark.asyncio
async def test_fetch_preserves_search_and_detail_html_and_parse_attaches_exact_checksum_evidence() -> None:
    contacted: list[str] = []
    posted: list[dict[str, list[str]]] = []
    transport = httpx.MockTransport(lambda request: official_response(request, contacted, posted))
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = JudicialPublicNoticesAdapter(
            client=client,
            request_interval=0,
            now=lambda: NOW,
            search_queries=("機車",),
        )
        item = (await adapter.discover())[0]
        artifacts = await adapter.fetch(item)
        record = await adapter.parse(item, artifacts)

    assert [artifact.filename for artifact in artifacts] == [
        "judicial-notice-1600001-a1b2c.html",
        "judicial-notices-search-4012de0ee5-p1.html",
    ]
    detail_checksum = artifacts[0].checksum_sha256
    assert all(evidence.artifact_checksum_sha256 == detail_checksum for evidence in record.evidence)
    assert record.organization == "臺灣測試地方法院"
    assert record.official_case_number == "115年度司執字第123號"
    assert record.disposal_origin == "JUDICIAL_EXECUTION"
    assert record.status == AuctionStatus.SCHEDULED
    assert record.auction_round == 2
    assert record.ends_at == datetime(2026, 9, 5, 10, 0, tzinfo=TAIPEI)
    assert record.reserve_price == 20_000
    assert record.deposit == 4_000
    assert record.vehicle_type == VehicleType.MOTORCYCLE
    assert record.vehicle_class == VehicleClass.ORDINARY_HEAVY
    assert record.displacement_cc == 149
    assert record.manufacture_year == 2025
    assert record.manufacture_month == 3
    assert record.mileage_km == 12_345
    assert record.identifiers[0].identifier_type == "PLATE"
    assert record.identifiers[0].normalized_value == "TST0001"
    assert record.can_test == FourState.NO
    assert record.can_start == FourState.UNKNOWN
    assert record.registration_status == RegistrationStatus.UNKNOWN
    assert record.photo_urls == []
    assert any(
        evidence.field_name == "official_attachment_url"
        and evidence.normalized_value == "https://www.judicial.gov.tw/tw/dl-12345-abcd1234.html"
        and evidence.source_text == "官方拍賣公告附件"
        for evidence in record.evidence
    )
    assert not any("/tw/dl-" in url for url in contacted)


@pytest.mark.asyncio
async def test_official_zero_result_marker_is_accepted_without_inventing_records() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n", headers={"content-type": "text/plain"})
        if request.method == "GET":
            return httpx.Response(
                200,
                content=fixture("judicial_notices_search_form.html"),
                headers={"content-type": "text/html"},
            )
        return httpx.Response(
            200,
            content=fixture("judicial_notices_search_empty.html"),
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = JudicialPublicNoticesAdapter(
            client=client,
            request_interval=0,
            now=lambda: NOW,
            search_queries=("機車",),
        )
        assert await adapter.discover() == []


@pytest.mark.asyncio
async def test_unknown_empty_markup_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n", headers={"content-type": "text/plain"})
        if request.method == "GET":
            return httpx.Response(
                200,
                content=fixture("judicial_notices_search_form.html"),
                headers={"content-type": "text/html"},
            )
        return httpx.Response(200, text="<html><section class='lp'>新版版面</section></html>", headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = JudicialPublicNoticesAdapter(
            client=client,
            request_interval=0,
            now=lambda: NOW,
            search_queries=("機車",),
        )
        with pytest.raises(ValueError, match="result table and empty marker"):
            await adapter.discover()


@pytest.mark.asyncio
async def test_robots_disallow_stops_before_search_form() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        assert request.url.path == "/robots.txt"
        return httpx.Response(
            200,
            text="User-agent: *\nDisallow: /tw/lp-1913\n",
            headers={"content-type": "text/plain"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = JudicialPublicNoticesAdapter(
            client=client,
            request_interval=0,
            now=lambda: NOW,
            search_queries=("機車",),
        )
        with pytest.raises(SourceAccessDenied, match="robots.txt disallows"):
            await adapter.discover()

    assert contacted == ["https://www.judicial.gov.tw/robots.txt"]


@pytest.mark.asyncio
async def test_rate_limit_and_cross_host_redirect_fail_closed() -> None:
    phase = "rate_limit"
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n", headers={"content-type": "text/plain"})
        if phase == "rate_limit":
            return httpx.Response(429, headers={"retry-after": "120", "content-type": "text/html"})
        return httpx.Response(302, headers={"location": "https://aomp109.judicial.gov.tw/blocked"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = JudicialPublicNoticesAdapter(
            client=client,
            request_interval=0,
            now=lambda: NOW,
            search_queries=("機車",),
        )
        with pytest.raises(SourceRateLimited) as limited:
            await adapter.discover()
        assert limited.value.retry_after_seconds == 120

        phase = "redirect"
        with pytest.raises(ValueError, match="non-registered Judicial Yuan URL"):
            await adapter.discover()

    assert not any("GET https://aomp109" in url for url in contacted)


@pytest.mark.asyncio
async def test_page_safety_bound_is_reported_as_partial_coverage() -> None:
    contacted: list[str] = []
    posted: list[dict[str, list[str]]] = []
    paginated = fixture("judicial_notices_search_results.html").replace(
        b"</section>",
        b"<ul class='page'><li><a href='/tw/lp-1913-1-2-20.html' title='\xe4\xb8\x8b\xe4\xb8\x80\xe9\xa0\x81'>next</a></li></ul></section>",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/tw/lp-1913-1.html" and request.method == "POST":
            contacted.append(f"{request.method} {request.url}")
            return httpx.Response(200, content=paginated, headers={"content-type": "text/html"})
        return official_response(request, contacted, posted)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = JudicialPublicNoticesAdapter(
            client=client,
            request_interval=0,
            now=lambda: NOW,
            search_queries=("機車",),
            max_pages_per_query=1,
        )
        items = await adapter.discover()

    assert len(items) == 1
    assert any("1-page safety bound" in warning for warning in adapter.discovery_warnings)
    assert not any("lp-1913-1-2-20" in url for url in contacted)


def test_parser_does_not_treat_cannot_test_as_cannot_start() -> None:
    content = fixture("judicial_notices_vehicle_detail.html")
    title, _, lines = JudicialPublicNoticesAdapter._detail_parts(content)
    assert JudicialPublicNoticesAdapter._is_vehicle_auction_detail(title, lines)
    assert any("不得試車" in line for line in lines)
    assert not any("無法發動" in line or "不能發動" in line for line in lines)


def test_disposal_origin_is_not_invented_from_a_court_host() -> None:
    classify = JudicialPublicNoticesAdapter._disposal_origin_from_official_text

    assert classify("115年度司執字第123號普通重型機車拍賣") == "JUDICIAL_EXECUTION"
    assert classify("本機關汰換汽車公開標售") == "SCRAP_DISPOSAL"
    assert classify("普通重型機車拍賣公告") == "UNKNOWN"


def test_network_allowlist_excludes_aomp109_downloads_and_images() -> None:
    validate = JudicialPublicNoticesAdapter._validate_url

    validate("https://www.judicial.gov.tw/tw/lp-1913-1.html")
    validate("https://www.judicial.gov.tw/tw/cp-1913-1600001-a1b2c-1.html")
    with pytest.raises(ValueError, match="non-registered"):
        validate("https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02.htm")
    with pytest.raises(ValueError, match="out-of-scope"):
        validate("https://www.judicial.gov.tw/tw/dl-12345-abcd1234.html")
    with pytest.raises(ValueError, match="out-of-scope"):
        validate("https://www.judicial.gov.tw/Public/Images/vehicle.jpg")
