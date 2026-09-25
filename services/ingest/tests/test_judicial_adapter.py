import json
from pathlib import Path

import httpx
import pytest

from ingest.adapters.judicial import JudicialMovableAdapter
from ingest.adapters.base import SourceAccessDenied
from ingest.models import DiscoveredItem

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_judicial_central_discovery_and_healthcheck_make_zero_requests() -> None:
    requests: list[httpx.Request] = []

    def no_network(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise AssertionError(f"blocked Judicial adapter must not request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_network)) as client:
        adapter = JudicialMovableAdapter(client=client, request_interval=0)
        with pytest.raises(SourceAccessDenied, match="discovery is disabled"):
            await adapter.discover()
        health = await adapter.healthcheck()

    assert health.status == "DEGRADED"
    assert requests == []


@pytest.mark.asyncio
async def test_unregistered_judicial_host_is_blocked() -> None:
    adapter = JudicialMovableAdapter(request_interval=0)
    with pytest.raises(ValueError, match="Blocked"):
        adapter._validate_url("https://example.com/")
    await adapter.close()


@pytest.mark.asyncio
async def test_human_manifest_import_never_queries_or_downloads_the_blocked_site() -> None:
    row = json.loads((FIXTURES / "judicial_motorcycle.json").read_text())
    item = DiscoveredItem(
        source_record_id="manual-test",
        official_url="https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02/DO_VIEWPDF.htm?filenm=%2Fsld%2F11508%2Ffixture.pdf",
        discovery_url=JudicialMovableAdapter.INDEX_URL,
        title=row["ttitle"],
        metadata={**row, "rowid": "manual-test", "filenm": "/sld/11508/fixture.pdf"},
    )

    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"manual Judicial import must not make a network request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_network)) as client:
        adapter = JudicialMovableAdapter([item], client=client, request_interval=0)
        discovered = await adapter.discover()
        artifacts = await adapter.fetch(discovered[0])
        parsed = await adapter.parse(discovered[0], artifacts)

    assert len(artifacts) == 1
    assert artifacts[0].mime_type == "application/json"
    assert artifacts[0].http_headers["x-artifact-provenance"] == "human-reviewed-manifest-row"
    assert parsed.official_url == item.official_url
    assert parsed.disposal_origin == "JUDICIAL_EXECUTION"
    assert all(evidence.trust in {"UNKNOWN", "SYSTEM_CALCULATED"} for evidence in parsed.evidence)
