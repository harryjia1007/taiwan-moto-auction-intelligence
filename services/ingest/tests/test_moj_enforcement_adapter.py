from pathlib import Path

import httpx
import pytest

from ingest.adapters.moj_enforcement import MojEnforcementManualAdapter
from ingest.models import DiscoveredItem

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_manual_enforcement_detail_preserves_photos_and_classification() -> None:
    detail = (FIXTURES / "moj_enforcement_detail.html").read_bytes()
    item = DiscoveredItem(
        source_record_id="00000000-0000-0000-0000-000000000001",
        official_url="https://www.tpkonsale.moj.gov.tw/Detail/Chattel?NO=00000000-0000-0000-0000-000000000001",
        discovery_url="https://www.tpkonsale.moj.gov.tw/Chattel",
        title="光陽普通重型機車",
        metadata={"organization": "法務部行政執行署嘉義分署", "auction_round": 1},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/Detail/Chattel":
            return httpx.Response(200, content=detail, headers={"content-type": "text/html"})
        if request.url.path == "/File/Img":
            return httpx.Response(200, content=b"fixture-image", headers={"content-type": "image/jpeg"})
        if request.url.path == "/File/Download":
            return httpx.Response(200, content=b"%PDF-1.4 fixture", headers={"content-type": "application/pdf"})
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = MojEnforcementManualAdapter([item], client=client, request_interval=0)
        discovered = await adapter.discover()
        artifacts = await adapter.fetch(discovered[0])
        parsed = await adapter.parse(discovered[0], artifacts)

    assert parsed.disposal_origin == "ADMINISTRATIVE_ENFORCEMENT"
    assert parsed.vehicle_class == "ORDINARY_HEAVY"
    assert parsed.registration_status == "RE_REGISTRATION_REQUIRED"
    assert parsed.has_key == "YES"
    assert len(parsed.photo_urls) == 1


@pytest.mark.asyncio
async def test_enforcement_manifest_rejects_non_detail_urls() -> None:
    item = DiscoveredItem(
        source_record_id="bad", official_url="https://www.tpkonsale.moj.gov.tw/Chattel/Query?THE_USE=1",
        discovery_url="https://www.tpkonsale.moj.gov.tw/Chattel", title="機車",
    )
    adapter = MojEnforcementManualAdapter([item], request_interval=0)
    with pytest.raises(ValueError, match="Detail/Chattel"):
        await adapter.discover()
    await adapter.close()
