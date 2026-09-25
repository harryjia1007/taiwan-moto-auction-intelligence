import asyncio
import gzip
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from ingest.adapters.base import SourceAccessDenied
from ingest.adapters.moj_enforcement_cms import EnforcementBranch, MojEnforcementCmsAdapter
from ingest.models import DiscoveredItem, RawArtifact

FIXTURES = Path(__file__).parent / "fixtures"
TAIPEI = ZoneInfo("Asia/Taipei")
BRANCH = EnforcementBranch("tcy", "法務部行政執行署臺中分署")
SECOND_BRANCH = EnforcementBranch("tyy", "法務部行政執行署桃園分署")


def test_cms_skips_navigation_slot_and_does_not_invent_type_filter() -> None:
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


def test_cms_link_only_and_unrecognized_layouts_fail_closed() -> None:
    adapter = MojEnforcementCmsAdapter(branches=(BRANCH,), request_interval=0)
    link_only = """<div class='list'><ul><li>
      <a href='/umbraco/surface/Ini/CountAndRedirectUrl?nodeId=123'>公告</a>
    </li></ul></div>""".encode()
    with pytest.raises(ValueError, match="redirect links only"):
        adapter._items_from_list(link_only, BRANCH, f"{BRANCH.origin}/list", datetime(2026, 6, 1, tzinfo=TAIPEI))
    with pytest.raises(ValueError, match="unrecognized announcement list markup"):
        adapter._items_from_list(b"<html><body>redesigned</body></html>", BRANCH, f"{BRANCH.origin}/list", datetime(2026, 6, 1, tzinfo=TAIPEI))
    items, dates, has_next = adapter._items_from_list(
        "<div class='no_data'>查無資料</div>".encode(),
        BRANCH,
        f"{BRANCH.origin}/list",
        datetime(2026, 6, 1, tzinfo=TAIPEI),
    )
    assert (items, dates, has_next) == ([], [], False)
    asyncio.run(adapter.close())


@pytest.mark.asyncio
@pytest.mark.parametrize(("cache_bytes", "expected_fetches"), [(8 * 1024 * 1024, 1), (1, 2)])
async def test_generic_auction_title_requires_explicit_vehicle_detail_and_reuses_artifact(
    cache_bytes: int, expected_fetches: int,
) -> None:
    contacted: list[str] = []
    list_html = """<table class='table_list'><tbody>
      <tr><td data-title='標題'><a href='/notice/1767001/post'>動產拍賣公告</a></td>
          <td data-title='張貼日/發布日期'>115-08-01</td></tr>
      <tr><td data-title='標題'><a href='/notice/1767002/post'>第2次動產拍賣</a></td>
          <td data-title='張貼日/發布日期'>115-08-01</td></tr>
    </tbody></table>""".encode()
    vehicle_detail = """<html><head><meta name='ContentTitle' content='動產拍賣公告'></head>
      <body><section class='cp'>本次拍賣普通重型機車一輛，車牌 KSS-7890。</section></body></html>""".encode()
    nonvehicle_detail = """<html><head><meta name='ContentTitle' content='第2次動產拍賣'></head>
      <body><section class='cp'>本次標的為金飾及珠寶。</section></body></html>""".encode()

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        if request.url.path == "/notice/1767001/post":
            return httpx.Response(200, content=vehicle_detail, headers={"content-type": "text/html"})
        if request.url.path == "/notice/1767002/post":
            return httpx.Response(200, content=nonvehicle_detail, headers={"content-type": "text/html"})
        if request.url.path in {"/9103/9127/9129/", "/9103/9127/653498/"}:
            return httpx.Response(200, content=list_html, headers={"content-type": "text/html"})
        return response_for(request, [])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,), client=client, request_interval=0,
            now=lambda: datetime(2026, 8, 18, tzinfo=TAIPEI),
        )
        adapter.MAX_CACHED_DETAIL_BYTES = cache_bytes
        items = await adapter.discover()
        assert [item.source_record_id for item in items] == ["tcy-1767001"]
        assert items[0].metadata["discovery_method"] == "BRANCH_CMS_GENERIC_TITLE_DETAIL_VALIDATED"
        artifacts = await adapter.fetch(items[0])
        parsed = await adapter.parse(items[0], artifacts)

    assert parsed.vehicle_type == "MOTORCYCLE"
    assert [identifier.original_value for identifier in parsed.identifiers] == ["KSS-7890"]
    assert contacted.count(f"{BRANCH.origin}/notice/1767001/post") == expected_fetches
    assert contacted.count(f"{BRANCH.origin}/notice/1767002/post") == 1


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
async def test_robots_redirect_is_narrow_and_requests_identity_encoding() -> None:
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
    assert set(encodings) == {"identity"}


@pytest.mark.asyncio
async def test_cms_decodes_valid_gzip_once_even_when_server_ignores_identity() -> None:
    html = b"<html><body>fixture</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(
            200, content=gzip.compress(html),
            headers={"content-type": "text/html", "content-encoding": "gzip"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(branches=(BRANCH,), client=client, request_interval=0)
        response = await adapter._request(f"{BRANCH.origin}/fixture/post", expected_host=BRANCH.host)

    assert response.content == html
    assert "content-encoding" not in response.headers
    assert response.headers["content-length"] == str(len(html))


@pytest.mark.asyncio
async def test_cms_html_response_limit_rejects_oversized_generic_detail() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        return httpx.Response(200, content=b"x" * 65, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(branches=(BRANCH,), client=client, request_interval=0)
        with pytest.raises(ValueError, match="exceeds 64 bytes"):
            await adapter._request(
                f"{BRANCH.origin}/notice/1767001/post", expected_host=BRANCH.host,
                maximum_bytes=64,
            )

    assert contacted == [f"{BRANCH.origin}/notice/1767001/post"]


@pytest.mark.asyncio
async def test_robots_redirect_outside_reviewed_paths_is_never_contacted() -> None:
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
    assert adapter.discovery_warnings == [
        "tcy: branch discovery failed closed: stage=robots; error=SourceAccessDenied"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [403, 429])
async def test_policy_response_does_not_retry_or_continue_on_same_branch(status_code: int) -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        return httpx.Response(status_code, headers={"retry-after": "120"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,), client=client, request_interval=0, max_request_attempts=3,
        )
        with pytest.raises(RuntimeError, match="could be checked safely"):
            await adapter.discover()

    assert contacted == [f"{BRANCH.origin}/robots.txt"]
    expected_error = "SourceAccessDenied" if status_code == 403 else "SourceRateLimited"
    assert adapter.discovery_warnings == [
        f"tcy: branch discovery failed closed: stage=robots; error={expected_error}"
    ]


@pytest.mark.asyncio
async def test_loaded_robots_rules_guard_each_redirect_target() -> None:
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


def test_robots_without_user_agent_directive_fail_closed() -> None:
    adapter = MojEnforcementCmsAdapter(branches=(BRANCH,), request_interval=0)
    with pytest.raises(SourceAccessDenied, match="User-agent directive"):
        adapter._check_robots(
            "Sitemap: https://www.tcy.moj.gov.tw/sitemap?id=9103\n",
            BRANCH,
            [f"{BRANCH.origin}/"],
        )
    asyncio.run(adapter.close())


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

    assert adapter.discovery_warnings == [
        "tcy: branch discovery failed closed: stage=robots; error=SourceAccessDenied"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_path", "expected_stage", "message"),
    [
        ("/robots.txt", "robots", ""),
        ("/sitemap", "sitemap", "https://example.invalid/?case=SYNTH-1234"),
        ("/", "homepage", ""),
    ],
)
async def test_branch_discovery_diagnostic_has_stage_and_type_but_no_raw_exception_text(
    failure_path: str, expected_stage: str, message: str,
) -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == failure_path:
            raise httpx.ReadError(message, request=request)
        return response_for(request, contacted)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementCmsAdapter(
            branches=(BRANCH,), client=client, request_interval=0, max_request_attempts=1,
        )
        with pytest.raises(RuntimeError, match="could be checked safely"):
            await adapter.discover()

    assert adapter.discovery_warnings == [
        f"tcy: branch discovery failed closed: stage={expected_stage}; error=ReadError"
    ]
    if message:
        assert message not in adapter.discovery_warnings[0]


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
    assert not MojEnforcementCmsAdapter._is_vehicle_auction_title("汽車燃料使用費拍賣")


def test_generic_auction_detail_does_not_treat_vehicle_tax_as_a_lot() -> None:
    jewelry_only = """<html><head><meta name='ContentTitle' content='動產拍賣公告'></head>
      <body><section class='cp'>本次標的為金飾及珠寶。債務人欠繳汽車燃料使用費，請先繳清。</section></body></html>""".encode()
    other_case_vehicle = """<html><head><meta name='ContentTitle' content='動產拍賣公告'></head>
      <body><section class='cp'>本次拍賣標的為金飾及珠寶，債務人名下汽車另案處理。</section></body></html>""".encode()
    vehicle_lot = """<html><head><meta name='ContentTitle' content='動產拍賣公告'></head>
      <body><section class='cp'>本次標的為普通重型機車一輛。拍定後須繳汽車燃料使用費。</section></body></html>""".encode()

    assert not MojEnforcementCmsAdapter._detail_explicitly_identifies_vehicle_auction(jewelry_only)
    assert not MojEnforcementCmsAdapter._detail_explicitly_identifies_vehicle_auction(other_case_vehicle)
    assert MojEnforcementCmsAdapter._detail_explicitly_identifies_vehicle_auction(vehicle_lot)


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
