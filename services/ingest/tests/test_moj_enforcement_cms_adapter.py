import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from ingest.adapters.moj_enforcement_cms import EnforcementBranch, MojEnforcementCmsAdapter
from ingest.adapters.base import SourceAccessDenied
from ingest.models import DiscoveredItem, RawArtifact

FIXTURES = Path(__file__).parent / "fixtures"
TAIPEI = ZoneInfo("Asia/Taipei")
BRANCH = EnforcementBranch("tcy", "法務部行政執行署臺中分署")
SECOND_BRANCH = EnforcementBranch("tyy", "法務部行政執行署桃園分署")
THIRD_BRANCH = EnforcementBranch("sly", "法務部行政執行署士林分署")
FOURTH_BRANCH = EnforcementBranch("pcy", "法務部行政執行署新北分署")
FIFTH_BRANCH = EnforcementBranch("scy", "法務部行政執行署新竹分署")


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


def test_navigation_landing_does_not_consume_a_bounded_announcement_list_slot() -> None:
    homepage = """<html><body>
      <a href='/9103/9127/9129/Lpsimplelist'>動產拍賣公告</a>
      <a href='/9103/9127/Normalnodelist'>電子公布欄</a>
      <a href='/9103/9127/653498/Lpsimplelist'>最新消息</a>
    </body></html>""".encode()
    adapter = MojEnforcementCmsAdapter(branches=(BRANCH,), request_interval=0)

    assert adapter._announcement_lists(homepage, BRANCH) == [
        f"{BRANCH.origin}/9103/9127/9129/",
        f"{BRANCH.origin}/9103/9127/653498/",
    ]
    assert adapter._page_url(f"{BRANCH.origin}/9103/9127/653498/", 1, 30).endswith(
        "/9103/9127/653498/?Page=1&PageSize=30"
    )
    asyncio.run(adapter.close())


def test_official_link_only_auction_page_is_not_reported_as_checked_cases() -> None:
    link_page = """<html><body><h2 class='title'>動產拍賣公告</h2>
      <div class='list'><ul><li>
        <a href='/umbraco/surface/Ini/CountAndRedirectUrl?nodeId=123'>分署拍賣公告</a>
      </li></ul></div>
    </body></html>""".encode()
    adapter = MojEnforcementCmsAdapter(branches=(BRANCH,), request_interval=0)

    with pytest.raises(ValueError, match="redirect links only; no dated CMS announcement rows"):
        adapter._items_from_list(
            link_page,
            BRANCH,
            f"{BRANCH.origin}/9103/9127/9129/",
            datetime(2026, 6, 1, tzinfo=TAIPEI),
        )

    asyncio.run(adapter.close())


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
    html_checksum = artifacts[0].checksum_sha256
    assert all(
        evidence.artifact_checksum_sha256 == html_checksum
        for evidence in parsed.evidence
    )
    assert {evidence.field_name for evidence in parsed.evidence} >= {
        "official_title",
        "organization",
        "ends_at",
        "status",
        "reserve_price",
        "location",
        "description",
        "disposal_origin",
        "brand",
        "model",
        "displacement_cc",
        "plate",
        "lot_size",
        "vehicle_type",
        "vehicle_class",
        "registration_status",
        "has_key",
        "can_start",
        "condition_summary",
        "official_attachment_url",
    }


@pytest.mark.asyncio
async def test_cms_request_enforces_streaming_size_limit_without_content_length() -> None:
    class OversizedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"12345678"
            yield b"abcdefgh"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=OversizedStream(),
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,),
            client=client,
            request_interval=0,
        )
        with pytest.raises(ValueError, match="Artifact exceeds 12 bytes"):
            await adapter._request(
                f"{BRANCH.origin}/bounded/post",
                expected_host=BRANCH.host,
                maximum_bytes=12,
            )


@pytest.mark.asyncio
async def test_cms_detail_never_uses_discovery_title_when_detail_marker_is_missing() -> None:
    content = b"<html><body><section class='cp'>ordinary heavy motorcycle auction</section></body></html>"
    url = f"{BRANCH.origin}/notice/post"
    item = DiscoveredItem(
        source_record_id="tcy-marker-change",
        official_url=url,
        discovery_url=f"{BRANCH.origin}/notice/",
        title="普通重型機車拍賣公告",
        metadata={"organization": BRANCH.organization},
    )
    artifact = RawArtifact(
        official_url=url,
        fetched_at=datetime.now(UTC),
        mime_type="text/html",
        content=content,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )
    adapter = MojEnforcementCmsAdapter(branches=(BRANCH,), request_interval=0)

    with pytest.raises(ValueError, match="detail title marker changed"):
        await adapter.parse(item, [artifact])

    await adapter.close()


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
async def test_branch_cms_accepts_same_host_plain_text_robots_redirect_before_policy_load() -> None:
    contacted: list[str] = []
    encodings: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        encodings.append(request.headers.get("accept-encoding", ""))
        if request.url.path == "/robots.txt":
            contacted.append(str(request.url))
            return httpx.Response(302, headers={"location": "/robots"})
        if request.url.path == "/robots":
            contacted.append(str(request.url))
            return httpx.Response(
                200,
                text="User-agent: *\nDisallow:\nSitemap: https://www.tcy.moj.gov.tw/sitemap?id=9103\n",
                headers={"content-type": "text/plain"},
            )
        return response_for(request, contacted)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,), client=client, request_interval=0,
            now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
        )
        items = await adapter.discover()

    assert items
    assert contacted[:2] == [f"{BRANCH.origin}/robots.txt", f"{BRANCH.origin}/robots"]
    assert encodings and set(encodings) == {"identity"}


@pytest.mark.asyncio
async def test_robots_preflight_rejects_unreviewed_redirect_before_contact() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        assert request.url.path == "/robots.txt"
        return httpx.Response(302, headers={"location": "/unreviewed-policy?token=fixture"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(branches=(BRANCH,), client=client, request_interval=0)
        with pytest.raises(RuntimeError, match="could be checked safely"):
            await adapter.discover()

    assert contacted == [f"{BRANCH.origin}/robots.txt"]
    assert any("outside the reviewed robots paths" in warning for warning in adapter.discovery_warnings)


def test_robots_without_user_agent_directive_fail_closed() -> None:
    adapter = MojEnforcementCmsAdapter(branches=(BRANCH,), request_interval=0)

    with pytest.raises(SourceAccessDenied, match="User-agent directive"):
        adapter._check_robots(
            "Sitemap: https://www.tcy.moj.gov.tw/sitemap?id=9103\n",
            BRANCH,
            ["https://www.tcy.moj.gov.tw/"],
        )


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
async def test_same_host_redirect_rechecks_robots_and_follows_allowed_target() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        if request.url.path == "/legacy-list":
            return httpx.Response(302, headers={"location": "/current-list"})
        if request.url.path == "/current-list":
            return httpx.Response(200, text="<html>official</html>", headers={"content-type": "text/html"})
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(branches=(BRANCH,), client=client, request_interval=0)
        adapter._check_robots(
            "User-agent: *\nDisallow: /private\n"
            "Sitemap: https://www.tcy.moj.gov.tw/sitemap?id=9103\n",
            BRANCH,
            [f"{BRANCH.origin}/legacy-list"],
        )
        response = await adapter._request(f"{BRANCH.origin}/legacy-list", expected_host=BRANCH.host)

    assert response.status_code == 200
    assert contacted == [
        f"{BRANCH.origin}/legacy-list",
        f"{BRANCH.origin}/current-list",
    ]


@pytest.mark.asyncio
async def test_same_host_redirect_to_robots_disallowed_target_is_never_contacted() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        if request.url.path == "/legacy-list":
            return httpx.Response(302, headers={"location": "/private/hidden-list"})
        raise AssertionError(f"robots-disallowed redirect target was contacted: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(branches=(BRANCH,), client=client, request_interval=0)
        adapter._check_robots(
            "User-agent: *\nDisallow: /private/\n"
            "Sitemap: https://www.tcy.moj.gov.tw/sitemap?id=9103\n",
            BRANCH,
            [f"{BRANCH.origin}/legacy-list"],
        )
        with pytest.raises(SourceAccessDenied, match="robots.txt disallows"):
            await adapter._request(f"{BRANCH.origin}/legacy-list", expected_host=BRANCH.host)

    assert contacted == [f"{BRANCH.origin}/legacy-list"]


@pytest.mark.asyncio
async def test_unknown_list_markup_fails_closed_instead_of_reporting_zero() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {"/9103/9127/9129/", "/9103/9127/653498/"}:
            contacted.append(str(request.url))
            return httpx.Response(
                200,
                text="<html><body><main>redesigned page without official list structure</main></body></html>",
                headers={"content-type": "text/html"},
            )
        return response_for(request, contacted)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,), client=client, request_interval=0,
            now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
        )
        with pytest.raises(RuntimeError, match="could be checked safely"):
            await adapter.discover()

    assert any("unrecognized announcement list markup" in warning for warning in adapter.discovery_warnings)


@pytest.mark.asyncio
async def test_official_empty_list_marker_is_a_successful_zero_result() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {"/9103/9127/9129/", "/9103/9127/653498/"}:
            contacted.append(str(request.url))
            return httpx.Response(
                200,
                text="<html><body><div class='no_data'>查無資料</div></body></html>",
                headers={"content-type": "text/html"},
            )
        return response_for(request, contacted)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,), client=client, request_interval=0,
            now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
        )
        items = await adapter.discover()

    assert items == []
    assert not any("announcement list failed closed" in warning for warning in adapter.discovery_warnings)


@pytest.mark.asyncio
async def test_pagination_safety_bound_is_reported_as_partial_coverage() -> None:
    contacted: list[str] = []
    recent_list = """<html><body>
      <table class='table_list'><tbody><tr>
        <td data-title='標題'><a href='/9103/9127/9129/1766929/post'>普通重型機車拍賣公告</a></td>
        <td data-title='張貼日/發布日期' class='date'>115-08-01</td>
      </tr></tbody></table>
      <ul class='page'><li><a title='下一頁' href='?Page=2'>下一頁</a></li></ul>
    </body></html>"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {"/9103/9127/9129/", "/9103/9127/653498/"}:
            contacted.append(str(request.url))
            return httpx.Response(200, text=recent_list, headers={"content-type": "text/html"})
        return response_for(request, contacted)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,), client=client, request_interval=0,
            now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
        )
        items = await adapter.discover()

    assert [item.source_record_id for item in items] == ["tcy-1766929"]
    assert len([url for url in contacted if "Page=" in url]) == adapter.MAX_LIST_PAGES
    assert any("safety bound" in warning for warning in adapter.discovery_warnings)


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
async def test_repeated_preflight_connect_timeouts_open_circuit_and_mark_remaining_branch_unchecked() -> None:
    contacted_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted_hosts.append(request.url.host)
        if request.url.host == BRANCH.host:
            return response_for(request, [])
        raise httpx.ConnectTimeout("fixture network route unavailable", request=request)

    branches = (BRANCH, SECOND_BRANCH, THIRD_BRANCH, FOURTH_BRANCH, FIFTH_BRANCH)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=branches,
            client=client,
            request_interval=0,
            max_request_attempts=1,
            now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
        )
        items = await adapter.discover()

    assert items
    assert SECOND_BRANCH.host in contacted_hosts
    assert THIRD_BRANCH.host in contacted_hosts
    assert FOURTH_BRANCH.host in contacted_hosts
    assert FIFTH_BRANCH.host not in contacted_hosts
    assert any("circuit breaker opened" in warning for warning in adapter.discovery_warnings)
    assert any(
        warning.startswith(f"{FIFTH_BRANCH.code}: branch not checked")
        for warning in adapter.discovery_warnings
    )


@pytest.mark.asyncio
async def test_preflight_circuit_breaker_fails_run_when_no_branch_was_checked() -> None:
    contacted_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted_hosts.append(request.url.host)
        raise httpx.ConnectTimeout("fixture network route unavailable", request=request)

    branches = (BRANCH, SECOND_BRANCH, THIRD_BRANCH, FOURTH_BRANCH)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=branches,
            client=client,
            request_interval=0,
            max_request_attempts=1,
            now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
        )
        with pytest.raises(RuntimeError, match="No Administrative Enforcement branch CMS"):
            await adapter.discover()

    assert contacted_hosts == [BRANCH.host, SECOND_BRANCH.host, THIRD_BRANCH.host]
    assert any(
        warning.startswith(f"{FOURTH_BRANCH.code}: branch not checked")
        for warning in adapter.discovery_warnings
    )


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
    assert MojEnforcementCmsAdapter._is_generic_auction_title("第8次動產拍賣公告")
    assert not MojEnforcementCmsAdapter._is_generic_auction_title("第8次不動產拍賣公告")


@pytest.mark.asyncio
async def test_generic_auction_title_is_boundedly_validated_from_detail_and_reuses_artifact() -> None:
    contacted: list[str] = []
    generic_list = """<html><body><table class='table_list'><tbody><tr>
      <td data-title='標題'><a href='/9103/9127/9129/1770000/post'>第9次動產拍賣公告</a></td>
      <td data-title='張貼日/發布日期' class='date'>115-08-10</td>
    </tr></tbody></table></body></html>"""
    detail = """<html><head>
      <meta name='ContentTitle' content='第9次動產拍賣公告'>
      <meta name='DC.Creator' content='行政執行署臺中分署'>
      </head><body><section class='cp'>標的為普通重型機車一輛，車牌 TST-9090。</section></body></html>"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {"/9103/9127/9129/", "/9103/9127/653498/"}:
            contacted.append(str(request.url))
            return httpx.Response(200, text=generic_list, headers={"content-type": "text/html"})
        if request.url.path == "/9103/9127/9129/1770000/post":
            contacted.append(str(request.url))
            return httpx.Response(200, text=detail, headers={"content-type": "text/html"})
        return response_for(request, contacted)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,),
            client=client,
            request_interval=0,
            now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
        )
        items = await adapter.discover()
        artifacts = await adapter.fetch(items[0])
        parsed = await adapter.parse(items[0], artifacts)

    assert [item.source_record_id for item in items] == ["tcy-1770000"]
    assert items[0].metadata["discovery_method"] == "BRANCH_CMS_GENERIC_TITLE_DETAIL_VALIDATED"
    assert len([url for url in contacted if "/1770000/post" in url]) == 1
    assert artifacts[0].content == detail.encode()
    assert parsed.vehicle_type == "MOTORCYCLE"


@pytest.mark.asyncio
async def test_generic_auction_detail_safety_bound_emits_coverage_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contacted: list[str] = []
    generic_list = """<html><body><table class='table_list'><tbody>
      <tr><td data-title='標題'><a href='/9103/9127/9129/1770001/post'>第1次動產拍賣公告</a></td>
      <td data-title='張貼日/發布日期' class='date'>115-08-10</td></tr>
      <tr><td data-title='標題'><a href='/9103/9127/9129/1770002/post'>第2次動產拍賣公告</a></td>
      <td data-title='張貼日/發布日期' class='date'>115-08-09</td></tr>
    </tbody></table></body></html>"""
    irrelevant_detail = """<html><head><meta name='ContentTitle' content='動產拍賣'></head>
      <body><section class='cp'>珠寶及名錶</section></body></html>"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {"/9103/9127/9129/", "/9103/9127/653498/"}:
            return httpx.Response(200, text=generic_list, headers={"content-type": "text/html"})
        if request.url.path.endswith("/post"):
            contacted.append(str(request.url))
            return httpx.Response(200, text=irrelevant_detail, headers={"content-type": "text/html"})
        return response_for(request, [])

    monkeypatch.setattr(MojEnforcementCmsAdapter, "MAX_GENERIC_DETAIL_CANDIDATES_PER_BRANCH", 1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,),
            client=client,
            request_interval=0,
            now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
        )
        assert await adapter.discover() == []

    assert len(contacted) == 1
    assert any("generic auction titles" in warning for warning in adapter.discovery_warnings)


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


@pytest.mark.asyncio
async def test_multi_plate_cms_notice_does_not_clone_shared_specs_into_vehicle_rows() -> None:
    content = """<html><head>
      <meta name='ContentTitle' content='普通重型機車二輛拍賣公告'>
      <meta name='DC.Creator' content='行政執行署臺中分署'>
      </head><body><section class='cp'>
      普通重型機車，車牌 AAA-111、BBB-222，廠牌測試牌，排氣量125cc。
      </section></body></html>""".encode()
    url = "https://www.tcy.moj.gov.tw/9103/9127/9129/1766001/post"
    item = DiscoveredItem(
        source_record_id="tcy-1766001",
        official_url=url,
        discovery_url="https://www.tcy.moj.gov.tw/9103/9127/9129/",
        title="普通重型機車二輛拍賣公告",
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

    assert len(parsed.identifiers) == 2
    assert parsed.bulk_lot is True
    assert parsed.vehicle_units == []
    assert parsed.brand is None
    assert parsed.displacement_cc is None
