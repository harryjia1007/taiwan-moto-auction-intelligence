import hashlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ingest.adapters.base import SourceAccessDenied
from ingest.adapters.moj_enforcement import (
    MojEnforcementExportedIndexParser,
    MojEnforcementManualAdapter,
)
from ingest.models import DiscoveredItem, RawArtifact
from ingest.parser import parse_moj_enforcement_detail

FIXTURES = Path(__file__).parent / "fixtures"
RECORD_ID = "11111111-1111-4111-8111-111111111111"
DETAIL_URL = f"https://www.tpkonsale.moj.gov.tw/Detail/Chattel?NO={RECORD_ID}"


def test_offline_export_parser_retains_safe_detail_metadata_and_coverage_warning() -> None:
    exported = (FIXTURES / "moj_enforcement_exported_index.html").read_bytes()
    items, warnings = MojEnforcementExportedIndexParser.parse(exported)

    assert len(items) == 1
    item = items[0]
    assert item.source_record_id == RECORD_ID
    assert str(item.official_url) == DETAIL_URL
    assert str(item.discovery_url) == "https://www.tpkonsale.moj.gov.tw/Chattel"
    assert item.metadata["organization"] == "法務部行政執行署臺南分署"
    assert item.metadata["auction_round"] == 2
    assert item.metadata["vehicle_category_bucket"] == "汽機車"
    assert item.metadata["index_provenance"] == "MANUAL_OFFICIAL_HTML_EXPORT"
    assert len(item.metadata["official_attachment_urls"]) == 1
    assert len(item.discovery_artifacts) == 1
    assert item.discovery_artifacts[0].content == exported
    assert item.discovery_artifacts[0].checksum_sha256 == hashlib.sha256(exported).hexdigest()
    assert any("additional result pages [2]" in warning for warning in warnings)


def test_multi_row_export_reuses_the_exact_same_immutable_index_artifact() -> None:
    exported = (FIXTURES / "moj_enforcement_exported_index.html").read_bytes()
    first_row = exported.split(b"<tr>", 1)[1].split(b"</tr>", 1)[0]
    second_id = b"22222222-2222-4222-8222-222222222222"
    second_row = first_row.replace(RECORD_ID.encode(), second_id).replace(
        b"1150100012345", b"1150100012346"
    )
    exported = exported.replace(b"</tbody>", b"<tr>" + second_row + b"</tr></tbody>")

    items, _ = MojEnforcementExportedIndexParser.parse(exported)

    assert len(items) == 2
    expected_checksum = hashlib.sha256(exported).hexdigest()
    assert {item.discovery_artifacts[0].checksum_sha256 for item in items} == {expected_checksum}
    assert all(item.discovery_artifacts[0].content == exported for item in items)


@pytest.mark.parametrize(
    "url",
    [
        f"https://evil.example/Detail/Chattel?NO={RECORD_ID}",
        f"https://user@www.tpkonsale.moj.gov.tw/Detail/Chattel?NO={RECORD_ID}",
        f"https://www.tpkonsale.moj.gov.tw:444/Detail/Chattel?NO={RECORD_ID}",
        "https://www.tpkonsale.moj.gov.tw/Detail/Chattel?NO=not-a-uuid",
    ],
)
def test_export_parser_rejects_cross_host_userinfo_non443_and_invalid_ids(url: str) -> None:
    with pytest.raises(ValueError):
        MojEnforcementExportedIndexParser.validate_url(url, kind="detail")


def test_export_parser_does_not_attach_a_pdf_from_another_official_record() -> None:
    exported = (FIXTURES / "moj_enforcement_exported_index.html").read_bytes().replace(
        f"PATH={RECORD_ID}".encode(),
        b"PATH=22222222-2222-4222-8222-222222222222",
    )

    items, warnings = MojEnforcementExportedIndexParser.parse(exported)

    assert len(items) == 1
    assert items[0].metadata["official_attachment_urls"] == []
    assert any("attachment PATH did not match its detail UUID" in warning for warning in warnings)


@pytest.mark.asyncio
async def test_manual_enforcement_fetch_is_robots_first_get_only_and_never_fetches_images() -> None:
    detail = (FIXTURES / "moj_enforcement_detail.html").read_bytes()
    item = MojEnforcementExportedIndexParser.parse(
        (FIXTURES / "moj_enforcement_exported_index.html").read_bytes()
    )[0][0]
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                content=b"User-agent: *\nDisallow: /*.jpg$\nDisallow: /*.gif$\n",
                headers={"content-type": "text/plain", "set-cookie": "session=secret"},
            )
        if request.url.path == "/Detail/Chattel":
            return httpx.Response(
                200,
                content=detail,
                headers={"content-type": "text/html", "set-cookie": "session=secret"},
            )
        if request.url.path == "/File/Download":
            raise AssertionError("official PDF must remain link-only")
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = MojEnforcementManualAdapter([item], client=client, request_interval=0)
        discovered = await adapter.discover()
        artifacts = await adapter.fetch(discovered[0])
        parsed = await adapter.parse(discovered[0], artifacts)

    assert requests[0] == ("GET", "/robots.txt")
    assert {method for method, _ in requests} == {"GET"}
    assert "/File/Img" not in {path for _, path in requests}
    assert "/File/Download" not in {path for _, path in requests}
    assert parsed.disposal_origin == "ADMINISTRATIVE_ENFORCEMENT"
    assert parsed.vehicle_class == "ORDINARY_HEAVY"
    assert parsed.registration_status == "RE_REGISTRATION_REQUIRED"
    assert parsed.has_key == "YES"
    assert parsed.photo_urls == []
    assert any(evidence.field_name == "official_attachment_url" for evidence in parsed.evidence)
    assert all("set-cookie" not in artifact.http_headers for artifact in artifacts)
    assert [artifact.mime_type for artifact in artifacts] == ["text/html", "text/html"]
    assert str(artifacts[0].official_url) == DETAIL_URL
    assert str(artifacts[1].official_url) == MojEnforcementManualAdapter.SEARCH_URL
    assert artifacts[1].content == (FIXTURES / "moj_enforcement_exported_index.html").read_bytes()

    evidence_by_field = {evidence.field_name: evidence for evidence in parsed.evidence}
    assert evidence_by_field["organization"].artifact_checksum_sha256 == artifacts[1].checksum_sha256
    assert evidence_by_field["vehicle_scope"].artifact_checksum_sha256 == artifacts[1].checksum_sha256
    assert evidence_by_field["registration_status"].artifact_checksum_sha256 == artifacts[0].checksum_sha256
    # This link appears in both HTML files; prefer the authoritative detail HTML
    # that was actually fetched for this source record.
    assert evidence_by_field["official_attachment_url"].artifact_checksum_sha256 == artifacts[0].checksum_sha256
    assert all(
        evidence.artifact_checksum_sha256 in {
            artifacts[0].checksum_sha256,
            artifacts[1].checksum_sha256,
        }
        for evidence in parsed.evidence
    )
    assert set(evidence_by_field) >= {
        "title",
        "official_case_number",
        "organization",
        "disposal_origin",
        "ends_at",
        "status",
        "auction_round",
        "vehicle_type",
        "vehicle_scope",
        "vehicle_class",
        "registration_status",
        "has_key",
        "description",
        "brand",
        "model",
        "manufacture_year",
        "manufacture_month",
        "displacement_cc",
        "plate",
        "condition_summary",
        "official_attachment_url",
    }


@pytest.mark.asyncio
async def test_manual_enforcement_never_follows_redirects() -> None:
    item = DiscoveredItem(
        source_record_id=RECORD_ID,
        official_url=DETAIL_URL,
        discovery_url=MojEnforcementManualAdapter.SEARCH_URL,
        title="官方車輛案件",
    )
    requested_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=b"User-agent: *\nAllow: /\n", headers={"content-type": "text/plain"})
        if request.url.path == "/Detail/Chattel":
            return httpx.Response(302, headers={"location": "https://evil.example/steal"})
        raise AssertionError(f"redirect target was contacted: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = MojEnforcementManualAdapter([item], client=client, request_interval=0)
        await adapter.discover()
        with pytest.raises(SourceAccessDenied, match="never follows redirects"):
            await adapter.fetch(item)

    assert requested_hosts == ["www.tpkonsale.moj.gov.tw", "www.tpkonsale.moj.gov.tw"]


@pytest.mark.asyncio
async def test_manual_enforcement_fails_closed_on_html_robots_error_page() -> None:
    item = DiscoveredItem(
        source_record_id=RECORD_ID,
        official_url=DETAIL_URL,
        discovery_url=MojEnforcementManualAdapter.SEARCH_URL,
        title="官方車輛案件",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/robots.txt"
        return httpx.Response(200, content=b"<html>login required</html>", headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementManualAdapter([item], client=client, request_interval=0)
        with pytest.raises(ValueError, match="robots MIME type"):
            await adapter.discover()


@pytest.mark.asyncio
async def test_manual_enforcement_requires_user_agent_directive_in_robots() -> None:
    item = DiscoveredItem(
        source_record_id=RECORD_ID,
        official_url=DETAIL_URL,
        discovery_url=MojEnforcementManualAdapter.SEARCH_URL,
        title="官方車輛案件",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/robots.txt"
        return httpx.Response(200, content=b"temporary upstream error", headers={"content-type": "text/plain"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementManualAdapter([item], client=client, request_interval=0)
        with pytest.raises(SourceAccessDenied, match="User-agent directive"):
            await adapter.discover()


def _detail_artifact(html: str) -> RawArtifact:
    content = html.encode()
    return RawArtifact(
        official_url=DETAIL_URL,
        fetched_at=datetime.now(UTC),
        mime_type="text/html",
        filename="detail.html",
        content=content,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )


def test_official_vehicle_bucket_keeps_detail_with_unknown_vehicle_type() -> None:
    exported = (FIXTURES / "moj_enforcement_exported_index.html").read_bytes()
    index_artifact = RawArtifact(
        official_url=MojEnforcementManualAdapter.SEARCH_URL,
        fetched_at=datetime.now(UTC),
        mime_type="text/html",
        filename="export.html",
        content=exported,
        checksum_sha256=hashlib.sha256(exported).hexdigest(),
    )
    item = DiscoveredItem(
        source_record_id=RECORD_ID,
        official_url=DETAIL_URL,
        discovery_url=MojEnforcementManualAdapter.SEARCH_URL,
        title="廠牌 PIAGGIO，出廠年份 2011，排氣量 151",
        metadata={
            "vehicle_category_bucket": "汽機車",
            "official_case_number": "1150100012345",
            "auction_at_text": "2099/09/01 10:00:00 第二拍",
            "auction_round": 2,
            "index_provenance": "MANUAL_OFFICIAL_HTML_EXPORT",
        },
        discovery_artifacts=[index_artifact],
    )
    artifact = _detail_artifact(
        "<div class='title_h3'>公告事項</div><ul>"
        "<li>案號：1150100012345</li><li>開標日：2099/09/01 10:00:00</li>"
        "<li>廠牌：PIAGGIO，出廠年份：2011，排氣量：151。</li></ul>"
    )

    record = parse_moj_enforcement_detail(item, [artifact, index_artifact])

    assert record.vehicle_type == "UNKNOWN"
    assert record.status == "SCHEDULED"
    assert any(
        evidence.field_name == "vehicle_scope"
        and evidence.extraction_method == "HTML"
        and evidence.artifact_checksum_sha256 == index_artifact.checksum_sha256
        for evidence in record.evidence
    )


def test_index_only_evidence_is_omitted_when_the_export_artifact_is_missing() -> None:
    item = DiscoveredItem(
        source_record_id=RECORD_ID,
        official_url=DETAIL_URL,
        discovery_url=MojEnforcementManualAdapter.SEARCH_URL,
        title="官方車輛案件",
        metadata={
            "organization": "法務部行政執行署臺南分署",
            "case_branch_text": "1150100012345 (台南分署／禮股)",
            "vehicle_category_bucket": "汽機車",
        },
    )
    artifact = _detail_artifact(
        "<div class='title_h3'>公告事項</div><ul><li>機車一輛，無法發動。</li></ul>"
    )

    record = parse_moj_enforcement_detail(item, [artifact])

    assert not any(
        evidence.field_name in {"organization", "vehicle_scope"}
        for evidence in record.evidence
    )
    assert next(
        evidence for evidence in record.evidence if evidence.field_name == "can_start"
    ).artifact_checksum_sha256 == artifact.checksum_sha256


def test_manual_manifest_title_and_metadata_never_override_detail_without_index_artifact() -> None:
    item = DiscoveredItem(
        source_record_id=RECORD_ID,
        official_url=DETAIL_URL,
        discovery_url=MojEnforcementManualAdapter.SEARCH_URL,
        title="人工輸入品牌、車牌與錯誤案件名稱",
        metadata={
            "organization": "人工輸入分署",
            "auction_round": 99,
            "official_case_number": "MANUAL-CASE",
            "vehicle_category_bucket": "汽機車",
        },
    )
    artifact = _detail_artifact(
        "<div class='title_h3'>公告事項</div><ul>"
        "<li>普通重型機車一輛，有鑰匙。</li></ul>"
    )

    record = parse_moj_enforcement_detail(item, [artifact])

    assert record.title == "普通重型機車一輛，有鑰匙。"
    assert record.organization == "法務部行政執行署（分署未確認）"
    assert record.auction_round is None
    assert record.official_case_number is None
    assert all("人工輸入" not in evidence.source_text for evidence in record.evidence)


@pytest.mark.parametrize(
    "html",
    [
        "<html><body><h1>系統錯誤</h1></body></html>",
        "<div class='title_h3'>公告事項</div><ul></ul>",
        "<div class='title_h3'>其他事項</div><ul><li>機車一輛</li></ul>",
    ],
)
def test_enforcement_detail_markup_change_fails_closed(html: str) -> None:
    item = DiscoveredItem(
        source_record_id=RECORD_ID,
        official_url=DETAIL_URL,
        discovery_url=MojEnforcementManualAdapter.SEARCH_URL,
        title="人工輸入機車案件",
        metadata={"vehicle_category_bucket": "汽機車"},
    )

    with pytest.raises(ValueError, match="detail markers changed|notice is empty"):
        parse_moj_enforcement_detail(item, [_detail_artifact(html)])


def test_missing_official_case_number_remains_unknown_instead_of_using_detail_uuid() -> None:
    item = DiscoveredItem(
        source_record_id=RECORD_ID,
        official_url=DETAIL_URL,
        discovery_url=MojEnforcementManualAdapter.SEARCH_URL,
        title="普通重型機車",
        metadata={"vehicle_category_bucket": "汽機車"},
    )
    artifact = _detail_artifact(
        "<div class='title_h3'>公告事項</div><ul>"
        "<li>開標日：2099/09/01 10:00:00</li><li>普通重型機車一輛。</li></ul>"
    )

    record = parse_moj_enforcement_detail(item, [artifact])

    assert record.official_case_number is None
    assert all(evidence.field_name != "official_case_number" for evidence in record.evidence)


def test_index_only_attachment_link_points_to_the_index_html_not_the_detail() -> None:
    item = MojEnforcementExportedIndexParser.parse(
        (FIXTURES / "moj_enforcement_exported_index.html").read_bytes()
    )[0][0]
    detail_artifact = _detail_artifact(
        "<div class='title_h3'>公告事項</div><ul>"
        "<li>案號：1150100000001</li><li>機車一輛，有鑰匙。</li></ul>"
    )
    index_artifact = item.discovery_artifacts[0]

    record = parse_moj_enforcement_detail(item, [detail_artifact, index_artifact])

    attachment_evidence = next(
        evidence
        for evidence in record.evidence
        if evidence.field_name == "official_attachment_url"
    )
    assert attachment_evidence.artifact_checksum_sha256 == index_artifact.checksum_sha256
    assert attachment_evidence.artifact_checksum_sha256 != detail_artifact.checksum_sha256


def test_ambiguous_multi_plate_specs_remain_one_bulk_lot_without_cloned_vehicles() -> None:
    item = DiscoveredItem(
        source_record_id=RECORD_ID,
        official_url=DETAIL_URL,
        discovery_url=MojEnforcementManualAdapter.SEARCH_URL,
        title="汽車二輛",
        metadata={"organization": "法務部行政執行署臺中分署"},
    )
    artifact = _detail_artifact(
        "<div class='title_h3'>公告事項</div><ul>"
        "<li>案號：1150100012345</li><li>開標日：2026/09/01 10:00:00</li>"
        "<li>汽車牌照號碼：AAA-1111、BBB-2222、廠牌：測試牌、排氣量：1800cc，汽車2輛。</li></ul>"
    )

    record = parse_moj_enforcement_detail(item, [artifact])

    assert record.bulk_lot is True
    assert record.lot_size == 2
    assert record.vehicle_units == []
    assert record.brand is None
    assert record.displacement_cc is None


@pytest.mark.asyncio
async def test_enforcement_manifest_rejects_non_detail_urls_after_robots_preflight() -> None:
    item = DiscoveredItem(
        source_record_id="bad",
        official_url="https://www.tpkonsale.moj.gov.tw/Chattel/Query?THE_USE=1",
        discovery_url="https://www.tpkonsale.moj.gov.tw/Chattel",
        title="機車",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/robots.txt"
        return httpx.Response(200, content=b"User-agent: *\nAllow: /\n", headers={"content-type": "text/plain"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = MojEnforcementManualAdapter([item], client=client, request_interval=0)
        with pytest.raises(ValueError, match="detail URL"):
            await adapter.discover()
