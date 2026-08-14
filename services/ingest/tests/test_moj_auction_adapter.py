from pathlib import Path

import httpx
import pytest

from ingest.adapters.moj_auction import MojAuctionAdapter
from ingest.models import DiscoveredItem, RawArtifact
from ingest.parser import parse_moj_auction_detail
from datetime import UTC, datetime
import hashlib

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_moj_central_discovery_fetch_and_parse() -> None:
    listing = (FIXTURES / "moj_auction_list.html").read_bytes()
    detail = (FIXTURES / "moj_auction_detail.html").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("searchList"):
            return httpx.Response(200, content=listing, headers={"content-type": "text/html"})
        if request.url.path.endswith("/90001/post"):
            return httpx.Response(200, content=detail, headers={"content-type": "text/html"})
        if request.url.path.endswith("motorcycle.jpg"):
            return httpx.Response(200, content=b"fixture-image", headers={"content-type": "image/jpeg"})
        if request.url.path.endswith("notice.pdf"):
            return httpx.Response(200, content=b"%PDF-1.4 fixture", headers={"content-type": "application/pdf"})
        if request.url.path.endswith("evidence.zip"):
            return httpx.Response(200, content=b"PK fixture", headers={"content-type": "application/x-zip-compressed"})
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = MojAuctionAdapter(client=client, request_interval=0)
        items = await adapter.discover()
        assert [item.source_record_id for item in items] == ["90001"]
        artifacts = await adapter.fetch(items[0])
        parsed = await adapter.parse(items[0], artifacts)

    assert {artifact.mime_type for artifact in artifacts} == {"text/html", "application/pdf", "application/x-zip-compressed", "image/jpeg"}
    assert parsed.vehicle_class == "ORDINARY_HEAVY"
    assert parsed.disposal_origin == "CRIMINAL_SEIZURE_OR_FORFEITURE"
    assert parsed.identifiers[0].normalized_value == "TST3001"
    assert len(parsed.photo_urls) == 1


@pytest.mark.asyncio
async def test_unregistered_moj_auction_host_is_blocked() -> None:
    adapter = MojAuctionAdapter(request_interval=0)
    with pytest.raises(ValueError, match="Blocked"):
        await adapter._request("https://example.com/")
    await adapter.close()


@pytest.mark.asyncio
async def test_redirect_is_validated_before_contacting_legacy_host() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://www.tcc.moj.gov.tw/legacy"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojAuctionAdapter(client=client, request_interval=0)
        with pytest.raises(ValueError, match="Blocked"):
            await adapter._request("https://auction.moj.gov.tw/umbraco/surface/Ini/CountAndRedirectUrl?nodeId=13564")

    assert contacted == ["https://auction.moj.gov.tw/umbraco/surface/Ini/CountAndRedirectUrl?nodeId=13564"]


def test_mixed_vehicle_notice_keeps_only_explicit_motorcycle_identity() -> None:
    content = (FIXTURES / "moj_auction_mixed_detail.html").read_bytes()
    url = "https://auction.moj.gov.tw/1724/1726/90003/post"
    item = DiscoveredItem(
        source_record_id="90003",
        official_url=url,
        discovery_url="https://auction.moj.gov.tw/1724/1726/searchList",
        title="汽車與大型重機拍賣公告",
    )
    artifact = RawArtifact(
        official_url=url,
        fetched_at=datetime.now(UTC),
        mime_type="text/html",
        filename="post",
        content=content,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )

    parsed = parse_moj_auction_detail(item, [artifact])

    assert parsed.vehicle_class == "LARGE_HEAVY"
    assert [identifier.normalized_value for identifier in parsed.identifiers] == ["TST2001"]
    assert parsed.lot_size == 1
    assert parsed.vehicle_units == []
