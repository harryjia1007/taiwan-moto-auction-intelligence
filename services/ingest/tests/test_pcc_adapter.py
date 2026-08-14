from pathlib import Path

import httpx
import pytest

from ingest.adapters.pcc import PccAssetSaleAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def test_search_results_discover_road_motorcycles_and_exclude_locomotives() -> None:
    items = PccAssetSaleAdapter._detail_items(
        (FIXTURES / "pcc_search.html").read_bytes(),
        PccAssetSaleAdapter.SEARCH_URL,
    )
    assert [item.source_record_id for item in items] == ["99900001", "99900002"]
    assert str(items[0].official_url).endswith("readOneAspamDetailOld?pk=99900001")


@pytest.mark.asyncio
async def test_discovery_deduplicates_keyword_results() -> None:
    search = (FIXTURES / "pcc_search.html").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=search, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = PccAssetSaleAdapter(client=client, request_interval=0)
        items = await adapter.discover()
    assert len(items) == 2


@pytest.mark.asyncio
async def test_unregistered_pcc_host_is_blocked() -> None:
    adapter = PccAssetSaleAdapter(request_interval=0)
    with pytest.raises(ValueError, match="Blocked"):
        await adapter._request("GET", "https://example.com/")
    await adapter.close()
