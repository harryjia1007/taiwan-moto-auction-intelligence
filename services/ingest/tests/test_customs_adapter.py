from pathlib import Path

import httpx
import pytest

from ingest.adapters.customs import CustomsAuctionAdapter


FIXTURES = Path(__file__).parent / "fixtures"
OVERVIEW = """
<html><body><main><h1>海關私貨拍賣訊息</h1>
<p>基隆關、臺北關、臺中關、高雄關標售公告</p></main></body></html>
""".encode()


@pytest.mark.asyncio
async def test_customs_discovers_html_vehicle_and_never_downloads_attachment() -> None:
    listing = (FIXTURES / "customs_list.html").read_bytes()
    last_page = (FIXTURES / "customs_list_last.html").read_bytes()
    vehicle = (FIXTURES / "customs_vehicle_detail.html").read_bytes()
    general = (FIXTURES / "customs_general_detail.html").read_bytes()
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        if request.url.path == "/singlehtml/1207":
            return httpx.Response(200, content=OVERVIEW, headers={"content-type": "text/html"})
        if request.url.path == "/taichung/multiplehtml/396":
            content = last_page if request.url.params.get("page") == "2" else listing
            return httpx.Response(200, content=content, headers={"content-type": "text/html; charset=utf-8"})
        if request.url.params.get("cntId") == "fixture-vehicle":
            return httpx.Response(200, content=vehicle, headers={"content-type": "text/html"})
        if request.url.params.get("cntId") == "fixture-general":
            return httpx.Response(200, content=general, headers={"content-type": "text/html"})
        raise AssertionError(f"unexpected request: {request.url}")

    office_lists = {
        "taichung": (
            "財政部關務署臺中關",
            "https://web.customs.gov.tw/taichung/multiplehtml/396",
        )
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        adapter = CustomsAuctionAdapter(client=client, request_interval=0, office_lists=office_lists)
        items = await adapter.discover()
        artifacts = await adapter.fetch(items[0])
        parsed = await adapter.parse(items[0], artifacts)

    assert [item.source_record_id for item in items] == ["taichung-fixture-vehicle"]
    assert parsed.vehicle_type == "CAR"
    assert parsed.car_category == "PASSENGER"
    assert parsed.displacement_cc == 1498
    assert parsed.registration_status == "INSPECTION_REQUIRED"
    assert parsed.eligibility == "NATURAL_PERSON_ALLOWED"
    assert parsed.disposal_origin == "CUSTOMS_FORFEITURE"
    assert parsed.status in {"SCHEDULED", "EXPIRED"}
    assert parsed.lot_size == 2
    assert parsed.identifiers[0].normalized_value == "TST0001"
    attachment_evidence = [entry for entry in parsed.evidence if entry.field_name == "official_attachment_url"]
    assert [entry.normalized_value for entry in attachment_evidence] == [
        "https://web.customs.gov.tw/download/customs-fixture-vehicle-list.pdf"
    ]
    assert not any("/download/" in url for url in contacted)


def test_customs_listing_candidates_are_scoped_to_the_office_detail_channel() -> None:
    items = CustomsAuctionAdapter._listing_candidates(
        (FIXTURES / "customs_list.html").read_bytes(),
        office_slug="taichung",
        organization="財政部關務署臺中關",
        list_url="https://web.customs.gov.tw/taichung/multiplehtml/396",
        current_url="https://web.customs.gov.tw/taichung/multiplehtml/396",
    )
    assert [item.source_record_id for item in items] == [
        "taichung-fixture-vehicle",
        "taichung-fixture-general",
    ]
    assert items[0].metadata["published_date"] == "115-08-10"


@pytest.mark.asyncio
async def test_customs_blocks_downloads_other_hosts_and_insecure_urls() -> None:
    adapter = CustomsAuctionAdapter(request_interval=0)
    for url in (
        "https://web.customs.gov.tw/download/private-list.pdf",
        "https://example.com/taichung/multiplehtml/396",
        "http://web.customs.gov.tw/taichung/multiplehtml/396",
    ):
        with pytest.raises(ValueError, match="Blocked"):
            await adapter._request(url)
    await adapter.close()


@pytest.mark.asyncio
async def test_customs_fails_closed_on_non_html_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF fixture", headers={"content-type": "application/pdf"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        adapter = CustomsAuctionAdapter(client=client, request_interval=0)
        with pytest.raises(ValueError, match="unexpected MIME"):
            await adapter._request("https://web.customs.gov.tw/taichung/multiplehtml/396")
