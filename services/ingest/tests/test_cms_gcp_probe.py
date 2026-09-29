"""Offline tests for the secret-free Cloud Run branch-CMS canary."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest

from ingest.adapters.moj_enforcement_cms import EnforcementBranch, MojEnforcementCmsAdapter
from ingest.cms_gcp_probe import ProbeReport, main, run_probe
from ingest.models import SourceHealth


BRANCH = EnforcementBranch("tcy", "法務部行政執行署臺中分署")


@pytest.mark.asyncio
async def test_probe_only_visits_official_preflight_paths() -> None:
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == BRANCH.host
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(302, headers={"location": "/robots"})
        if request.url.path == "/robots":
            return httpx.Response(
                200,
                text=f"User-agent: *\nDisallow:\nSitemap: {BRANCH.origin}/sitemap\n",
                headers={"content-type": "text/plain"},
            )
        if request.url.path == "/sitemap":
            return httpx.Response(
                200,
                text=f"<urlset><url><loc>{BRANCH.origin}/</loc></url></urlset>",
                headers={"content-type": "application/xml"},
            )
        if request.url.path == "/":
            return httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"})
        raise AssertionError("Probe must not discover notices or fetch detail pages")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = MojEnforcementCmsAdapter(branches=(BRANCH,), client=client, request_interval=0)
        report = await run_probe(adapter)

    assert report.result == "PASS"
    assert report.passed == report.total == 1
    assert requested == ["/robots.txt", "/robots", "/sitemap", "/"]


@pytest.mark.asyncio
async def test_probe_redacts_raw_transport_warning() -> None:
    class FailedAdapter:
        branches = (BRANCH,)

        async def healthcheck(self) -> SourceHealth:
            return SourceHealth(
                source="moj_enforcement_cms",
                status="DEGRADED",
                checked_at=datetime.now(UTC),
                message="0/1 branch CMS preflights succeeded; centralized CAPTCHA search was not used",
                warnings=[
                    "tcy: ConnectTimeout https://www.tcy.moj.gov.tw/post?plate=TEST-1234 "
                    "token=secret-value"
                ],
            )

    report = await run_probe(FailedAdapter())  # type: ignore[arg-type]
    payload = report.to_json()
    assert report.result == "FAIL"
    assert report.failed_or_unchecked_branches == ["tcy"]
    assert "TEST-1234" not in payload
    assert "secret-value" not in payload
    assert "https://" not in payload


@pytest.mark.asyncio
async def test_probe_blocks_before_network_if_reviewed_policy_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    class ShouldNotRun:
        branches = (BRANCH,)

        async def healthcheck(self) -> SourceHealth:
            nonlocal called
            called = True
            raise AssertionError("policy must be checked before network")

    def block(_: str) -> None:
        raise RuntimeError("policy denied")

    monkeypatch.setattr("ingest.cms_gcp_probe.require_live_access", block)
    report = await run_probe(ShouldNotRun())  # type: ignore[arg-type]
    assert report.result == "FAIL"
    assert report.reason == "source_policy_blocked"
    assert called is False


@pytest.mark.asyncio
async def test_probe_has_strict_overall_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    class HangingAdapter:
        branches = (BRANCH,)

        async def healthcheck(self) -> SourceHealth:
            await asyncio.sleep(10)
            raise AssertionError("deadline should cancel this")

    monkeypatch.setattr("ingest.cms_gcp_probe.TOTAL_DEADLINE_SECONDS", 0.01)
    report = await run_probe(HangingAdapter())  # type: ignore[arg-type]
    assert report.result == "FAIL"
    assert report.reason == "overall_deadline_exceeded"


@pytest.mark.parametrize("result, expected_exit", [("PASS", 0), ("FAIL", 1)])
def test_probe_cli_emits_one_bounded_json_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], result: str, expected_exit: int,
) -> None:
    async def fake_run_probe() -> ProbeReport:
        return ProbeReport(
            source="moj_enforcement_cms", mode="official_preflight_only", result=result,
            passed=13 if result == "PASS" else 0, total=13,
            failed_or_unchecked_branches=[] if result == "PASS" else ["tcy"],
            reason="all_preflights_passed" if result == "PASS" else "preflight_incomplete",
        )

    monkeypatch.setattr("ingest.cms_gcp_probe.run_probe", fake_run_probe)
    assert main() == expected_exit
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["result"] == result


def test_probe_cli_redacts_unexpected_runtime_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    async def failing_probe() -> ProbeReport:
        raise RuntimeError("TEST-1234 token=secret-value")

    monkeypatch.setattr("ingest.cms_gcp_probe.run_probe", failing_probe)
    assert main() == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["reason"] == "probe_runtime_failure"
    assert output.err == ""
    assert "TEST-1234" not in output.out
