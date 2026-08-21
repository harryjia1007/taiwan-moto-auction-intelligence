import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from ingest.adapters.moj_enforcement_cms import EnforcementBranch, MojEnforcementCmsAdapter
from ingest.models import DiscoveredItem, RawArtifact

FIXTURES = Path(__file__).parent / "fixtures"
TAIPEI = ZoneInfo("Asia/Taipei")
BRANCH = EnforcementBranch("tcy", "法務部行政執行署臺中分署")
SECOND_BRANCH = EnforcementBranch("tyy", "法務部行政執行署桃園分署")


def response_for(request: httpx.Request, contacted: list[str]) -> httpx.Response:
    contacted.append(str(request.url))
    path = request.url.path
    if path == "/robots.txt":
        return httpx.Response(
            200,
            text="User-agent: *\nDisallow:\nSitemap: https://www.tcy.moj.gov.tw/sitemap?id=9103\n",
            headers={"content-type": "text/plain"},
        )
    if path == "/sitemap":
        return httpx.Response(
            200,
            content=(FIXTURES / "moj_enforcement_cms_sitemap.xml").read_bytes(),
            headers={"content-type": "text/xml"},
        )
    if path == "/":
        return httpx.Response(
            200,
            content=(FIXTURES / "moj_enforcement_cms_home.html").read_bytes(),
            headers={"content-type": "text/html"},
        )
    if path in {"/9103/9127/9129/", "/9103/9127/653498/"}:
        return httpx.Response(
            200,
            content=(FIXTURES / "moj_enforcement_cms_list.html").read_bytes(),
            headers={"content-type": "text/html"},
        )
    if path == "/9103/9127/9129/1766929/post":
        return httpx.Response(
            200,
            content=(FIXTURES / "moj_enforcement_cms_detail.html").read_bytes(),
            headers={"content-type": "text/html"},
        )
    if path == "/media/20751397/vehicle-notice.pdf":
        return httpx.Response(200, content=b"%PDF-1.4 fixture", headers={"content-type": "application/pdf"})
    raise AssertionError(f"unexpected request: {request.url}")


@pytest.mark.asyncio
async def test_branch_cms_discovers_only_recent_vehicle_auctions() -> None:
    contacted: list[str] = []
    transport = httpx.MockTransport(lambda request: response_for(request, contacted))
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,),
            client=client,
            request_interval=0,
            now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
        )
        items = await adapter.discover()

    assert [item.source_record_id for item in items] == ["tcy-1766000", "tcy-1766929"]
    assert all(item.metadata["discovery_method"] == "BRANCH_CMS_ANNOUNCEMENT_LIST" for item in items)
    assert not any("tpkonsale" in url for url in contacted)
    assert len([url for url in contacted if "Page=" in url]) == 1


@pytest.mark.asyncio
async def test_branch_cms_fetches_html_and_pdf_but_never_images() -> None:
    contacted: list[str] = []
    transport = httpx.MockTransport(lambda request: response_for(request, contacted))
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,), client=client, request_interval=0,
            now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
        )
        items = await adapter.discover()
        item = next(item for item in items if item.source_record_id == "tcy-1766929")
        artifacts = await adapter.fetch(item)
        parsed = await adapter.parse(item, artifacts)

    assert [artifact.mime_type for artifact in artifacts] == ["text/html", "application/pdf"]
    assert not any(url.endswith(("vehicle.jpg", "vehicle-photo.jpg")) for url in contacted)
    assert parsed.disposal_origin == "ADMINISTRATIVE_ENFORCEMENT"
    assert parsed.vehicle_type == "MOTORCYCLE"
    assert parsed.vehicle_class == "ORDINARY_HEAVY"
    assert parsed.identifiers[0].normalized_value == "TST3001"
    assert parsed.reserve_price == 20_000
    assert parsed.photo_urls == []


@pytest.mark.asyncio
async def test_branch_cms_fails_closed_when_robots_disallows_collection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/robots.txt"
        return httpx.Response(
            200,
            text="User-agent: *\nDisallow: /\nSitemap: https://www.tcy.moj.gov.tw/sitemap?id=9103\n",
            headers={"content-type": "text/plain"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(branches=(BRANCH,), client=client, request_interval=0)
        with pytest.raises(RuntimeError, match="could be checked safely"):
            await adapter.discover()

    assert any("robots.txt disallows" in warning for warning in adapter.discovery_warnings)


@pytest.mark.asyncio
async def test_robots_disallowed_detail_is_never_contacted_and_records_warning() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            contacted.append(str(request.url))
            return httpx.Response(
                200,
                text=(
                    "User-agent: *\n"
                    "Disallow: /9103/9127/9129/1766929/post\n"
                    "Sitemap: https://www.tcy.moj.gov.tw/sitemap?id=9103\n"
                ),
                headers={"content-type": "text/plain"},
            )
        return response_for(request, contacted)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,), client=client, request_interval=0,
            now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
        )
        items = await adapter.discover()

    assert [item.source_record_id for item in items] == ["tcy-1766000"]
    assert not any("/1766929/post" in url for url in contacted)
    assert any("skipped a robots-disallowed detail" in warning for warning in adapter.discovery_warnings)


@pytest.mark.asyncio
async def test_robots_disallowed_pdf_is_linked_but_never_downloaded() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            contacted.append(str(request.url))
            return httpx.Response(
                200,
                text=(
                    "User-agent: *\n"
                    "Disallow: /media/\n"
                    "Sitemap: https://www.tcy.moj.gov.tw/sitemap?id=9103\n"
                ),
                headers={"content-type": "text/plain"},
            )
        return response_for(request, contacted)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,), client=client, request_interval=0,
            now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
        )
        items = await adapter.discover()
        item = next(item for item in items if item.source_record_id == "tcy-1766929")
        artifacts = await adapter.fetch(item)
        parsed = await adapter.parse(item, artifacts)

    attachment_url = "https://www.tcy.moj.gov.tw/media/20751397/vehicle-notice.pdf?mediaDL=true"
    assert [artifact.mime_type for artifact in artifacts] == ["text/html"]
    assert item.metadata["official_attachment_urls"] == [attachment_url]
    assert item.metadata["ingest_partial_failure"].endswith("official PDF attachment(s); links only")
    assert not any(url == attachment_url for url in contacted)
    assert any(
        evidence.field_name == "official_attachment_url" and evidence.normalized_value == attachment_url
        for evidence in parsed.evidence
    )


@pytest.mark.asyncio
async def test_branch_discovery_timeout_is_isolated_from_next_branch() -> None:
    adapter = MojEnforcementCmsAdapter(
        branches=(BRANCH, SECOND_BRANCH),
        request_interval=0,
        branch_deadline_seconds=0.01,
    )

    async def fake_discover_branch(branch: EnforcementBranch, cutoff: datetime) -> list[DiscoveredItem]:
        if branch == BRANCH:
            await asyncio.sleep(0.05)
            return []
        return [DiscoveredItem(
            source_record_id="tyy-safe",
            official_url=f"{branch.origin}/safe/1/post",
            discovery_url=f"{branch.origin}/safe/",
            title="普通重型機車拍賣公告",
        )]

    adapter._discover_branch = fake_discover_branch  # type: ignore[method-assign]
    items = await adapter.discover()
    await adapter.close()

    assert [item.source_record_id for item in items] == ["tyy-safe"]
    assert any("branch discovery exceeded" in warning for warning in adapter.discovery_warnings)


@pytest.mark.asyncio
async def test_healthcheck_timeout_is_isolated_and_remains_partial() -> None:
    adapter = MojEnforcementCmsAdapter(
        branches=(BRANCH, SECOND_BRANCH),
        request_interval=0,
        branch_deadline_seconds=0.01,
    )

    async def fake_preflight(branch: EnforcementBranch) -> tuple[str, bytes]:
        if branch == BRANCH:
            await asyncio.sleep(0.05)
        return "", b""

    adapter._preflight = fake_preflight  # type: ignore[method-assign]
    health = await adapter.healthcheck()
    await adapter.close()

    assert health.status == "PARTIAL"
    assert health.message.startswith("1/2 branch CMS preflights succeeded")
    assert any("preflight exceeded" in warning for warning in health.warnings)


def test_vehicle_filter_requires_both_auction_and_vehicle_language() -> None:
    assert MojEnforcementCmsAdapter._is_vehicle_auction_title("普通重型機車拍賣公告")
    assert MojEnforcementCmsAdapter._is_vehicle_auction_title("第8次車輛及其他動產拍賣")
    assert not MojEnforcementCmsAdapter._is_vehicle_auction_title("機車報廢便民服務")
    assert not MojEnforcementCmsAdapter._is_vehicle_auction_title("珠寶及名錶拍賣")


def test_cms_artifact_headers_exclude_cookie_and_authorization_metadata() -> None:
    response = httpx.Response(
        200,
        request=httpx.Request("GET", "https://www.tcy.moj.gov.tw/notice/post"),
        content=b"<html><body>fixture</body></html>",
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "ETag": '"public-version"',
            "Set-Cookie": "session=private-token; Secure",
            "Authorization": "Bearer private-token",
            "X-Request-Identity": "private-user",
        },
    )

    artifact = MojEnforcementCmsAdapter._artifact(response, datetime.now(UTC))

    assert artifact.http_headers == {
        "content-length": str(len(response.content)),
        "content-type": "text/html; charset=utf-8",
        "etag": '"public-version"',
    }
    assert "private-token" not in str(artifact.http_headers)


@pytest.mark.asyncio
async def test_generic_vehicle_notice_remains_an_unknown_bulk_lot() -> None:
    content = """<html><head>
      <meta name='ContentTitle' content='公告第8次車輛及其他動產拍賣（115年8月25日）'>
      <meta name='DC.Creator' content='行政執行署臺中分署'>
      </head><body><section class='cp'></section></body></html>""".encode()
    url = "https://www.tcy.moj.gov.tw/9103/9127/9129/1766000/post"
    item = DiscoveredItem(
        source_record_id="tcy-1766000",
        official_url=url,
        discovery_url="https://www.tcy.moj.gov.tw/9103/9127/9129/",
        title="公告第8次車輛及其他動產拍賣（115年8月25日）",
        metadata={"organization": BRANCH.organization},
    )
    artifact = RawArtifact(
        official_url=url,
        fetched_at=datetime.now(UTC),
        mime_type="text/html",
        filename="post",
        content=content,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )
    adapter = MojEnforcementCmsAdapter(
        branches=(BRANCH,), request_interval=0,
        now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
    )
    parsed = await adapter.parse(item, [artifact])
    await adapter.close()

    assert parsed.vehicle_type == "UNKNOWN"
    assert parsed.bulk_lot is True
    assert parsed.brand is None
    assert parsed.vehicle_units == []
