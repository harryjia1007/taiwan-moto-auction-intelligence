import json
from pathlib import Path

import httpx
import pytest

from ingest.adapters.judicial import JudicialMovableAdapter

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_judicial_discovery_and_artifact_preservation() -> None:
    row = json.loads((FIXTURES / "judicial_motorcycle.json").read_text())
    form = (FIXTURES / "judicial_search_form.html").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("V1.htm"):
            return httpx.Response(200, content=b"<html>search</html>", headers={"content-type": "text/html"})
        if request.url.path.endswith("V2.htm"):
            return httpx.Response(200, content=form, headers={"content-type": "text/html"})
        if request.url.path.endswith("QUERY.htm"):
            assert request.headers["referer"].endswith("V2.htm")
            return httpx.Response(200, json={"data": [row], "total": 1})
        if request.url.path.endswith("DO_VIEWPDF.htm"):
            return httpx.Response(200, content=b"%PDF-1.4 fixture", headers={"content-type": "application/pdf;charset=UTF-8"})
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = JudicialMovableAdapter(client=client, request_interval=0)
        items = await adapter.discover()
        assert len(items) == 1
        assert items[0].source_record_id == str(row["rowid"])
        artifacts = await adapter.fetch(items[0])
        parsed = await adapter.parse(items[0], artifacts)

    assert [artifact.mime_type for artifact in artifacts] == ["application/json", "application/pdf"]
    assert parsed.disposal_origin == "JUDICIAL_EXECUTION"
    assert parsed.identifiers[0].original_value == "511-KND"


@pytest.mark.asyncio
async def test_unregistered_judicial_host_is_blocked() -> None:
    adapter = JudicialMovableAdapter(request_interval=0)
    with pytest.raises(ValueError, match="Blocked"):
        await adapter._request("GET", "https://example.com/")
    await adapter.close()
