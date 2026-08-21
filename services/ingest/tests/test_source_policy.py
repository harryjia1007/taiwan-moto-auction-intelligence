import pytest
import httpx

from ingest.adapters.base import SourceAccessDenied, SourceRateLimited, enforce_http_status
from ingest.repository import source_status_after_run
from ingest.source_policy import AccessDecision, SourceAccessBlocked, policy_for, require_live_access


def test_judicial_requires_a_human_reviewed_official_manifest() -> None:
    assert policy_for("judicial").decision == AccessDecision.MANUAL_ONLY
    with pytest.raises(SourceAccessBlocked, match="MANUAL_ONLY"):
        require_live_access("judicial")
    assert require_live_access("judicial", human_manifest=True).decision == AccessDecision.MANUAL_ONLY


def test_pcc_machine_readable_open_data_access_is_allowed() -> None:
    policy = require_live_access("pcc")
    assert policy.decision == AccessDecision.ALLOW
    assert "dataset 7263" in policy.reason


def test_human_manifest_is_required_for_manual_enforcement_source() -> None:
    with pytest.raises(SourceAccessBlocked, match="MANUAL_ONLY"):
        require_live_access("moj_enforcement")
    assert require_live_access("moj_enforcement", human_manifest=True).decision == AccessDecision.MANUAL_ONLY


def test_reviewed_sources_are_allowed() -> None:
    assert require_live_access("shwoo").decision == AccessDecision.ALLOW
    assert require_live_access("moj_auction").decision == AccessDecision.ALLOW
    assert require_live_access("pcc").decision == AccessDecision.ALLOW
    assert require_live_access("customs").decision == AccessDecision.ALLOW
    assert require_live_access("moj_enforcement_cms").decision == AccessDecision.ALLOW


@pytest.mark.parametrize(
    ("decision", "run_status", "expected"),
    [
        (AccessDecision.ALLOW, "SUCCEEDED", "ACTIVE"),
        (AccessDecision.ALLOW, "PARTIAL", "PARTIAL"),
        (AccessDecision.ALLOW, "FAILED", "DEGRADED"),
        (AccessDecision.MANUAL_ONLY, "SUCCEEDED", "PARTIAL"),
        (AccessDecision.MANUAL_ONLY, "PARTIAL", "PARTIAL"),
        (AccessDecision.MANUAL_ONLY, "FAILED", "DEGRADED"),
        (AccessDecision.REVIEW_REQUIRED, "SUCCEEDED", "DEGRADED"),
        (AccessDecision.DISABLED, "SUCCEEDED", "DISABLED"),
    ],
)
def test_source_status_cannot_override_access_policy(
    decision: AccessDecision,
    run_status: str,
    expected: str,
) -> None:
    assert source_status_after_run(decision, run_status) == expected


def test_403_stops_live_access_without_transient_retry() -> None:
    with pytest.raises(SourceAccessDenied, match="policy review"):
        enforce_http_status(httpx.Response(403))


def test_429_retains_bounded_retry_after_instruction() -> None:
    with pytest.raises(SourceRateLimited) as error:
        enforce_http_status(httpx.Response(429, headers={"Retry-After": "120"}))
    assert error.value.retry_after_seconds == 120
