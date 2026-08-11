from pathlib import Path

import httpx
import pytest

from ingest.adapters.shwoo import ShwooAdapter
from ingest.models import DiscoveredItem

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_discovery_deduplicates_keyword_and_eligibility_results() -> None:
    browse = b'<form id="autionId" method="post" action="/shwoo/browse/browse00/advancedQuery"></form><h1>\xe7\x89\xa9\xe5\x93\x81\xe7\x80\x8f\xe8\xa6\xbd</h1>'
    results = '<a href="/shwoo/newproduct/newproduct00/product?AUID=939528">機器腳踏車1台</a>'

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("browse00/"):
            return httpx.Response(200, content=browse, headers={"content-type": "text/html"})
        if request.url.path.endswith("advancedQuery"):
            return httpx.Response(200, text=results, headers={"content-type": "text/html"})
        if request.url.path.endswith("bidresult"):
            return httpx.Response(200, text=results, headers={"content-type": "text/html"})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = ShwooAdapter(client=client, request_interval=0)
        items = await adapter.discover()
    assert len(items) == 1
    assert items[0].source_record_id == "939528"


def test_completed_result_uses_official_title_cell_not_query_link() -> None:
    result = b"""
      <table><tr>
        <td>1</td><td><a href='../../newproduct/newproduct00/product?FROM=bidresult&amp;AUID=937754'>\xe6\x9f\xa5\xe8\xa9\xa2</a></td>
        <td>\xe5\xb7\xb2\xe7\xb9\xb3\xe6\xac\xbe</td><td>115H122500015</td><td>1</td><td>\xe4\xb8\x89\xe9\x99\xbd\xe6\xa9\x9f\xe8\xbb\x8a1\xe5\x8f\xb0</td>
      </tr></table>
    """
    items = ShwooAdapter._detail_items(result, ShwooAdapter.RESULTS_URL, False, True)
    assert items[0].title == "\u4e09\u967d\u6a5f\u8eca1\u53f0"
    assert items[0].result_record is True


@pytest.mark.asyncio
async def test_broken_image_does_not_discard_detail_html() -> None:
    detail = (FIXTURES / "shwoo_single.html").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if "imageResize" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, content=detail, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = ShwooAdapter(client=client, request_interval=0)
        item = DiscoveredItem(
            source_record_id="939528", official_url="https://shwoo.gov.taipei/shwoo/newproduct/newproduct00/product?AUID=939528",
            title="機車", discovery_url="https://shwoo.gov.taipei/shwoo/browse/browse00/",
        )
        artifacts = await adapter.fetch(item)
    assert len(artifacts) == 1
    assert artifacts[0].mime_type == "text/html"


@pytest.mark.asyncio
async def test_redirected_image_keeps_the_url_parsed_from_official_html() -> None:
    detail = (FIXTURES / "shwoo_single.html").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if "imageResize" in str(request.url):
            return httpx.Response(302, headers={"location": "/shwoo/cached/final.jpg"})
        if request.url.path.endswith("final.jpg"):
            return httpx.Response(200, content=b"jpeg", headers={"content-type": "image/jpeg"})
        return httpx.Response(200, content=detail, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = ShwooAdapter(client=client, request_interval=0)
        item = DiscoveredItem(
            source_record_id="939528", official_url="https://shwoo.gov.taipei/shwoo/newproduct/newproduct00/product?AUID=939528",
            title="機車", discovery_url="https://shwoo.gov.taipei/shwoo/browse/browse00/",
        )
        artifacts = await adapter.fetch(item)

    assert len(artifacts) == 2
    assert "imageResize" in str(artifacts[1].official_url)
    assert "final.jpg" not in str(artifacts[1].official_url)


@pytest.mark.asyncio
async def test_unregistered_host_is_blocked() -> None:
    adapter = ShwooAdapter(request_interval=0)
    with pytest.raises(ValueError, match="Blocked"):
        await adapter._request("GET", "https://example.com/")
    await adapter.close()
