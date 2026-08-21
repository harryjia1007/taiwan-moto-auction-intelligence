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
        assert [item.source_record_id for item in items] == ["90001", "90002"]
        artifacts = await adapter.fetch(items[0])
        parsed = await adapter.parse(items[0], artifacts)

    assert {artifact.mime_type for artifact in artifacts} == {"text/html", "application/pdf", "application/x-zip-compressed", "image/jpeg"}
    assert parsed.vehicle_class == "ORDINARY_HEAVY"
    assert parsed.vehicle_type == "MOTORCYCLE"
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
async def test_moj_url_validation_blocks_credentials_and_nonstandard_ports_before_contact() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        return httpx.Response(200, content=b"unexpected")

    unsafe_urls = (
        "https://user:password@auction.moj.gov.tw/1724/1726/searchList",
        "https://auction.moj.gov.tw:4443/1724/1726/searchList",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojAuctionAdapter(client=client, request_interval=0)
        for unsafe_url in unsafe_urls:
            with pytest.raises(ValueError, match="Blocked non-registered source URL"):
                await adapter._request(unsafe_url)

    assert contacted == []


def test_moj_artifacts_store_only_safe_response_headers() -> None:
    response = httpx.Response(
        200,
        content=b"<html><body>official evidence</body></html>",
        headers={
            "content-type": "text/html; charset=utf-8",
            "cache-control": "public, max-age=60",
            "etag": '"official-etag"',
            "set-cookie": "session=must-not-be-persisted",
            "authorization": "Bearer must-not-be-persisted",
            "x-debug-token": "must-not-be-persisted",
        },
        request=httpx.Request("GET", "https://auction.moj.gov.tw/1724/1726/123/post"),
    )
    item = DiscoveredItem(
        source_record_id="123",
        official_url="https://auction.moj.gov.tw/1724/1726/123/post",
        title="普通重型機車",
        discovery_url=MojAuctionAdapter.LIST_URL,
    )
    artifacts = (
        MojAuctionAdapter._artifact(response, datetime.now(UTC)),
        MojAuctionAdapter._central_summary_artifact(
            response,
            item,
            b"<tr>official row</tr>",
            datetime.now(UTC),
        ),
    )

    for artifact in artifacts:
        assert artifact.http_headers["content-type"] == "text/html; charset=utf-8"
        assert artifact.http_headers["cache-control"] == "public, max-age=60"
        assert artifact.http_headers["etag"] == '"official-etag"'
        assert set(artifact.http_headers) <= MojAuctionAdapter.ARTIFACT_HEADER_ALLOWLIST
        assert "set-cookie" not in artifact.http_headers
        assert "authorization" not in artifact.http_headers
        assert "x-debug-token" not in artifact.http_headers


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


@pytest.mark.asyncio
async def test_external_detail_keeps_exact_central_summary_without_contacting_external_host() -> None:
    listing = (FIXTURES / "moj_auction_external_summary_list.html").read_bytes()
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        if request.url.path.endswith("searchList"):
            return httpx.Response(200, content=listing, headers={"content-type": "text/html; charset=utf-8"})
        if request.url.path.endswith("CountAndRedirectUrl"):
            return httpx.Response(302, headers={"location": "https://www.unreviewed.moj.gov.tw/vehicle/post"})
        raise AssertionError(f"external host must never be contacted: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojAuctionAdapter(client=client, request_interval=0)
        items = await adapter.discover()
        artifacts = await adapter.fetch(items[0])
        parsed = await adapter.parse(items[0], artifacts)

    assert contacted == [
        "https://auction.moj.gov.tw/1724/1726/searchList?Page=1&PageSize=100&type=01",
        "https://auction.moj.gov.tw/umbraco/surface/Ini/CountAndRedirectUrl?nodeId=13564",
    ]
    assert len(artifacts) == 1
    assert artifacts[0].content in listing
    assert artifacts[0].filename == "moj-auction-list-row-node-13564.html"
    assert parsed.organization == "臺灣測試地方檢察署"
    assert parsed.title == "普通重型機車一輛拍賣公告"
    assert parsed.vehicle_type == "MOTORCYCLE"
    assert parsed.description is None
    assert "no reviewed automated-access policy" in items[0].metadata[MojAuctionAdapter.PARTIAL_FAILURE_KEY]
    assert all(evidence.source_text.encode() in artifacts[0].content for evidence in parsed.evidence)


@pytest.mark.asyncio
async def test_repeated_discovery_clears_stale_central_summary_artifacts() -> None:
    first_listing = (FIXTURES / "moj_auction_external_summary_list.html").read_bytes()
    empty_listing = b"<html><body><table class='table_list'><tbody></tbody></table></body></html>"
    responses = iter((first_listing, empty_listing))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("searchList")
        return httpx.Response(200, content=next(responses), headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojAuctionAdapter(client=client, request_interval=0)
        first_items = await adapter.discover()
        assert first_items[0].source_record_id in adapter._central_summary_artifacts

        second_items = await adapter.discover()

    assert second_items == []
    assert adapter._central_summary_artifacts == {}


def test_mixed_vehicle_notice_is_retained_without_inventing_one_vehicle_class() -> None:
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

    assert parsed.vehicle_type == "MIXED"
    assert parsed.vehicle_class == "UNKNOWN"
    assert parsed.brand is None
    assert parsed.bulk_lot is True


def test_car_notice_is_parsed_as_car_without_motorcycle_class() -> None:
    content = """
      <html><head><meta name="DC.Creator" content="臺灣高雄地方檢察署"></head><body>
      <h2 class="title">自用小客車拍賣公告</h2><section class="cp">
      自用小客車 1 輛，車牌 ABC-1234，廠牌：TOYOTA，型號：ALTIS，排氣量：1798cc。
      拍賣時間：115/08/28 10:00，可辦理移轉過戶，有鑰匙。
      </section></body></html>
    """.encode()
    url = "https://auction.moj.gov.tw/1724/1726/90002/post"
    item = DiscoveredItem(source_record_id="90002", official_url=url, discovery_url=MojAuctionAdapter.LIST_URL, title="自用小客車拍賣公告")
    artifact = RawArtifact(
        official_url=url, fetched_at=datetime.now(UTC), mime_type="text/html", filename="post",
        content=content, checksum_sha256=hashlib.sha256(content).hexdigest(),
    )

    parsed = parse_moj_auction_detail(item, [artifact])

    assert parsed.vehicle_type == "CAR"
    assert parsed.car_category == "PASSENGER"
    assert parsed.vehicle_class == "UNKNOWN"
    assert parsed.displacement_cc == 1798
    assert parsed.identifiers[0].normalized_value == "ABC1234"
