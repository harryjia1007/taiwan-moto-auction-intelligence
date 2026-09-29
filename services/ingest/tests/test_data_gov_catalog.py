from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from ingest.data_gov_catalog import (
    CATALOG_EXPORT_URL,
    DataGovCatalogNetworkError,
    DataGovCatalogValidationError,
    download_official_catalog,
    evaluate_catalog,
    github_warning_lines,
    taipei_catalog_cutoff,
    watch_official_catalog,
)


FIXTURES = Path(__file__).parent / "fixtures"
CATALOG_FIXTURE = (FIXTURES / "data_gov_catalog.json").read_bytes()
OFFICIAL_DOWNLOAD_HEADERS = {
    "content-type": "text/html; charset=UTF-8",
    "content-disposition": 'attachment; filename="datagovtw_dataset_20260821.json"',
}


def test_catalog_semantics_require_agency_auction_and_vehicle_and_exclude_old_or_property_only() -> None:
    result = evaluate_catalog(
        CATALOG_FIXTURE,
        published_after=date(2026, 8, 10),
        checked_at=datetime(2026, 8, 21, 10, tzinfo=UTC),
        min_entries=1,
    )

    assert result.status == "warning"
    assert {candidate.dataset_id for candidate in result.candidates} == {900001, 900002, 900003, 900008}
    assert {candidate.scope for candidate in result.candidates} == {
        "ADMINISTRATIVE_ENFORCEMENT",
        "JUDICIAL",
        "GOVERNMENT_VEHICLE_AUCTION",
    }
    assert 900004 not in {candidate.dataset_id for candidate in result.candidates}  # pure real estate
    assert 900005 not in {candidate.dataset_id for candidate in result.candidates}  # inventory, not auction
    assert 900006 not in {candidate.dataset_id for candidate in result.candidates}  # auction, not vehicle
    assert 900007 not in {candidate.dataset_id for candidate in result.candidates}  # outside new window


def test_result_exposes_only_review_metadata_not_catalog_text_or_contacts() -> None:
    result = evaluate_catalog(CATALOG_FIXTURE, published_after=date(2026, 8, 10), min_entries=1)
    encoded = json.dumps(result.as_dict(), ensure_ascii=False)

    assert "測試聯絡窗口" not in encoded
    assert "行政執行分署汽機車拍賣資料" not in encoded
    assert "資料集描述" not in encoded
    assert result.as_dict()["notice"] == "metadata candidate only; no auction case was created or published"
    assert all(set(candidate) == {"dataset_id", "metadata_url", "published_on", "scope"}
               for candidate in result.as_dict()["candidates"])


def test_no_candidate_is_success_and_does_not_create_case_semantics() -> None:
    rows = json.loads(CATALOG_FIXTURE)
    document = json.dumps([row for row in rows if row["資料集識別碼"] in {900004, 900005, 900006}]).encode()

    result = evaluate_catalog(document, published_after=date(2026, 8, 10), min_entries=1)

    assert result.status == "success"
    assert result.candidates == ()
    assert result.as_dict()["candidate_count"] == 0


@pytest.mark.asyncio
async def test_download_accepts_official_json_attachment_mime_exception_and_uses_contact_user_agent() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, headers=OFFICIAL_DOWNLOAD_HEADERS, content=CATALOG_FIXTURE)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        cookies={"synthetic-session": "must-not-be-sent"},
        headers={"Cookie": "synthetic-default=must-not-be-sent"},
    ) as client:
        document = await download_official_catalog(client=client)

    assert document == CATALOG_FIXTURE
    assert len(requests) == 1
    assert str(requests[0].url) == CATALOG_EXPORT_URL
    assert requests[0].method == "GET"
    assert "cookie" not in requests[0].headers
    assert "harryjia.com/projects/taiwan-moto-auction" in requests[0].headers["user-agent"]


@pytest.mark.asyncio
async def test_watch_returns_warning_without_network_or_database_side_effects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=OFFICIAL_DOWNLOAD_HEADERS, content=CATALOG_FIXTURE, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await watch_official_catalog(
            published_after=date(2026, 8, 10),
            checked_at=datetime(2026, 8, 21, 10, tzinfo=UTC),
            client=client,
            min_entries=1,
        )

    assert result.status == "warning"
    assert result.scanned_entries == 8
    assert result.undated_matching_entries == 0
    assert len(result.document_sha256) == 64


@pytest.mark.asyncio
async def test_cross_host_redirect_is_rejected_before_contacting_target() -> None:
    contacted_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted_hosts.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://example.invalid/catalog.json"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DataGovCatalogValidationError, match="exact official HTTPS"):
            await download_official_catalog(client=client)

    assert contacted_hosts == ["data.gov.tw"]


@pytest.mark.asyncio
async def test_caller_redirect_default_cannot_bypass_exact_endpoint_validation() -> None:
    contacted_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted_hosts.append(request.url.host)
        if request.url.host == "data.gov.tw":
            return httpx.Response(
                302,
                headers={"location": "https://example.invalid/catalog.json"},
                request=request,
            )
        return httpx.Response(200, headers=OFFICIAL_DOWNLOAD_HEADERS, content=CATALOG_FIXTURE, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(DataGovCatalogValidationError, match="exact official HTTPS"):
            await download_official_catalog(client=client)

    assert contacted_hosts == ["data.gov.tw"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsafe_location",
    [
        "https://data.gov.tw/not-the-export?format=json",
        "https://data.gov.tw/api/front/dataset/export?format=json&format=json",
        "https://user:password@data.gov.tw/api/front/dataset/export?format=json",
        "https://data.gov.tw:444/api/front/dataset/export?format=json",
    ],
)
async def test_same_host_unsafe_redirect_variants_are_rejected(unsafe_location: str) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(302, headers={"location": unsafe_location}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DataGovCatalogValidationError, match="exact official HTTPS"):
            await download_official_catalog(client=client)

    assert requests == [CATALOG_EXPORT_URL]


@pytest.mark.asyncio
async def test_non_json_mime_without_json_attachment_name_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"[]", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DataGovCatalogValidationError, match="supported JSON"):
            await download_official_catalog(client=client)


@pytest.mark.asyncio
async def test_declared_oversize_response_is_rejected_before_body_acceptance() -> None:
    headers = {
        "content-type": "application/json",
        "content-length": "11",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=headers, content=b"[]", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DataGovCatalogValidationError, match="declared response-size"):
            await download_official_catalog(client=client, max_bytes=10)


@pytest.mark.asyncio
async def test_network_failure_is_wrapped_without_response_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("synthetic connection failure", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DataGovCatalogNetworkError, match="network request failed"):
            await download_official_catalog(client=client)


def test_taipei_cutoff_is_timezone_stable_and_bounded() -> None:
    now = datetime(2026, 8, 20, 16, 30, tzinfo=UTC)  # 2026-08-21 in Asia/Taipei

    assert taipei_catalog_cutoff(lookback_days=14, now=now) == date(2026, 8, 7)
    with pytest.raises(ValueError, match="between 1 and 90"):
        taipei_catalog_cutoff(lookback_days=0, now=now)


def test_github_warning_contains_only_dataset_id_and_official_metadata_url() -> None:
    result = evaluate_catalog(CATALOG_FIXTURE, published_after=date(2026, 8, 10), min_entries=1)

    warnings = github_warning_lines(result.candidates)

    assert len(warnings) == 4
    assert all("https://data.gov.tw/dataset/" in line for line in warnings)
    assert all("汽機車拍賣資料" not in line for line in warnings)


def test_undated_semantic_match_is_counted_but_not_emitted_as_new_candidate() -> None:
    undated = {
        "資料集識別碼": 900009,
        "資料集名稱": "公務機車標售資料",
        "資料集描述": "政府機關機車拍賣 metadata。",
        "提供機關": "範例市政府財政局",
    }
    irrelevant = {
        "資料集識別碼": 900010,
        "資料集名稱": "公園清冊",
        "資料集描述": "公共設施盤點。",
        "提供機關": "範例市政府管理處",
        "上架日期": "2026-08-20",
    }
    document = json.dumps([undated, irrelevant], ensure_ascii=False).encode()

    result = evaluate_catalog(document, published_after=date(2026, 8, 10), min_entries=1)

    assert result.status == "success"
    assert result.candidates == ()
    assert result.undated_matching_entries == 1


def test_structural_validation_rejects_small_or_non_array_catalogs() -> None:
    with pytest.raises(DataGovCatalogValidationError, match="unexpectedly few"):
        evaluate_catalog(b"[]", published_after=date(2026, 8, 10), min_entries=1)
    with pytest.raises(DataGovCatalogValidationError, match="root was not an array"):
        evaluate_catalog(b"{}", published_after=date(2026, 8, 10), min_entries=1)
