from pathlib import Path

import httpx
import pytest

from ingest.adapters.pcc import PccAssetSaleAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def test_open_data_discovers_vehicle_notices_and_excludes_railway_locomotives() -> None:
    items = PccAssetSaleAdapter._open_data_items(
        (FIXTURES / "pcc_open_data.xml").read_bytes(),
        PccAssetSaleAdapter.OPEN_DATA_URL,
    )

    assert [item.title for item in items] == [
        "合成測試報廢機車標售",
        "合成測試逾期未領回車輛公開標售案",
        "合成測試公務汽車一輛",
    ]
    assert all(item.source_record_id.startswith("open-data-") for item in items)
    assert items[0].metadata["feed_updated_at"] == "20260818 00:25"


def test_search_result_rows_expose_all_open_data_matching_fields() -> None:
    items = PccAssetSaleAdapter._detail_items(
        (FIXTURES / "pcc_search.html").read_bytes(),
        PccAssetSaleAdapter.SEARCH_URL,
    )

    assert [item.source_record_id for item in items] == ["99900001", "99900002"]
    assert str(items[0].official_url).endswith("readOneAspamDetailOld?pk=99900001")
    assert items[0].metadata == {
        "organization": "合成司法機關",
        "case_number": "SYNTH-PCC-01",
        "announcement_count": "1",
        "announcement_date": "115/07/29",
    }


@pytest.mark.asyncio
async def test_discovery_uses_one_official_open_data_request() -> None:
    feed = (FIXTURES / "pcc_open_data.xml").read_bytes()
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=feed, headers={"content-type": "application/octet-stream"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = PccAssetSaleAdapter(client=client, request_interval=0)
        items = await adapter.discover()

    assert len(items) == 3
    assert requested == [PccAssetSaleAdapter.OPEN_DATA_URL]


@pytest.mark.asyncio
async def test_fetch_resolves_exact_feed_row_to_https_detail() -> None:
    feed = (FIXTURES / "pcc_open_data.xml").read_bytes()
    search = (FIXTURES / "pcc_search.html").read_bytes()
    detail = (FIXTURES / "pcc_court_scrap.html").read_bytes()
    item = PccAssetSaleAdapter._open_data_items(feed, PccAssetSaleAdapter.OPEN_DATA_URL)[0]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/readAspam"):
            assert request.url.params["searchTenderCaseNo"] == "SYNTH-PCC-01"
            assert request.url.params["searchOrgName"] == "合成司法機關"
            assert "searchAssetsName" not in request.url.params
            return httpx.Response(200, content=search, headers={"content-type": "text/html"})
        if request.url.path.endswith("/readOneAspamDetailOld"):
            return httpx.Response(200, content=detail, headers={"content-type": "text/html"})
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = PccAssetSaleAdapter(client=client, request_interval=0)
        artifacts = await adapter.fetch(item)

    assert str(item.official_url).endswith("readOneAspamDetailOld?pk=99900001")
    assert item.metadata["pcc_detail_record_id"] == "99900001"
    assert str(artifacts[0].official_url) == str(item.official_url)


@pytest.mark.asyncio
async def test_fetch_fails_closed_when_feed_row_cannot_be_matched() -> None:
    feed = (FIXTURES / "pcc_open_data.xml").read_bytes()
    item = PccAssetSaleAdapter._open_data_items(feed, PccAssetSaleAdapter.OPEN_DATA_URL)[2]
    search = (FIXTURES / "pcc_search.html").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=search, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = PccAssetSaleAdapter(client=client, request_interval=0)
        with pytest.raises(ValueError, match="found 0"):
            await adapter.fetch(item)


@pytest.mark.asyncio
async def test_discovery_rejects_non_xml_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>error</html>", headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = PccAssetSaleAdapter(client=client, request_interval=0)
        with pytest.raises(ValueError, match="MIME"):
            await adapter.discover()


@pytest.mark.asyncio
async def test_unregistered_pcc_host_is_blocked() -> None:
    adapter = PccAssetSaleAdapter(request_interval=0)
    with pytest.raises(ValueError, match="Blocked"):
        await adapter._request("GET", "https://example.com/")
    await adapter.close()


@pytest.mark.asyncio
async def test_cross_host_redirect_is_rejected_before_contact() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://example.com/pcc-feed.xml"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        adapter = PccAssetSaleAdapter(client=client, request_interval=0)
        with pytest.raises(ValueError, match="Blocked non-registered source URL"):
            await adapter.discover()

    assert contacted == [PccAssetSaleAdapter.OPEN_DATA_URL]


@pytest.mark.asyncio
async def test_same_host_https_redirect_is_followed_with_validation() -> None:
    feed = (FIXTURES / "pcc_open_data.xml").read_bytes()
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        if request.url.path.endswith("downloadOpenData"):
            return httpx.Response(302, headers={"location": "/opas/aspam/public/feed.xml"})
        return httpx.Response(200, content=feed, headers={"content-type": "application/xml"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = PccAssetSaleAdapter(client=client, request_interval=0)
        items = await adapter.discover()

    assert len(items) == 3
    assert contacted == [
        PccAssetSaleAdapter.OPEN_DATA_URL,
        "https://web.pcc.gov.tw/opas/aspam/public/feed.xml",
    ]
