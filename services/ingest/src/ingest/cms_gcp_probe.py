"""Secret-free, read-only network probe for the branch CMS source.

Run with ``python -m ingest.cms_gcp_probe`` in the same image used by ingestion.
This intentionally calls only the adapter's bounded healthcheck, never sync or
discovery, and prints no source response body, URL, notice, or raw exception.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass

from ingest.adapters.moj_enforcement_cms import ENFORCEMENT_BRANCHES, MojEnforcementCmsAdapter
from ingest.models import SourceHealth
from ingest.source_policy import require_live_access


SOURCE = "moj_enforcement_cms"
TOTAL_DEADLINE_SECONDS = 210
BRANCH_DEADLINE_SECONDS = 15
_HEALTH_MESSAGE = re.compile(
    r"^(\d+)/(\d+) branch CMS preflights succeeded; centralized CAPTCHA search was not used$"
)


@dataclass(frozen=True)
class ProbeReport:
    source: str
    mode: str
    result: str
    passed: int
    total: int
    failed_or_unchecked_branches: list[str]
    reason: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def _failure(total: int, reason: str) -> ProbeReport:
    return ProbeReport(
        source=SOURCE,
        mode="official_preflight_only",
        result="FAIL",
        passed=0,
        total=total,
        failed_or_unchecked_branches=[],
        reason=reason,
    )


def _report_from_health(health: SourceHealth, branch_codes: tuple[str, ...]) -> ProbeReport:
    total = len(branch_codes)
    match = _HEALTH_MESSAGE.fullmatch(health.message)
    if health.source != SOURCE or match is None:
        return _failure(total, "health_contract_changed")

    passed, reported_total = map(int, match.groups())
    if reported_total != total or passed < 0 or passed > total:
        return _failure(total, "health_contract_changed")

    # Only fixed, reviewed branch codes may leave the process. Warnings may
    # include URLs or raw transport errors and must never be serialized.
    failed_codes = tuple(
        code for code in branch_codes
        if any(warning.startswith(f"{code}:") for warning in health.warnings)
    )
    if len(failed_codes) != total - passed:
        return _failure(total, "health_contract_changed")

    success = passed == total and health.status == "ACTIVE"
    if not success and health.status == "ACTIVE":
        return _failure(total, "health_contract_changed")
    return ProbeReport(
        source=SOURCE,
        mode="official_preflight_only",
        result="PASS" if success else "FAIL",
        passed=passed,
        total=total,
        failed_or_unchecked_branches=list(failed_codes),
        reason="all_preflights_passed" if success else "preflight_incomplete",
    )


async def run_probe(adapter: MojEnforcementCmsAdapter | None = None) -> ProbeReport:
    """Check reviewed source policy, then robots/sitemap/homepage only.

    ``adapter`` injection exists solely for deterministic, offline tests. A
    production invocation always uses the 13 fixed official branch hosts.
    """
    try:
        require_live_access(SOURCE)
    except Exception:
        return _failure(len(ENFORCEMENT_BRANCHES), "source_policy_blocked")

    owned_adapter = adapter is None
    if adapter is None:
        adapter = MojEnforcementCmsAdapter(
            branches=ENFORCEMENT_BRANCHES,
            request_interval=1.0,
            request_timeout_seconds=5.0,
            max_request_attempts=1,
            branch_deadline_seconds=BRANCH_DEADLINE_SECONDS,
        )

    total = len(adapter.branches)
    branch_codes = tuple(branch.code for branch in adapter.branches)
    try:
        async with asyncio.timeout(TOTAL_DEADLINE_SECONDS):
            health = await adapter.healthcheck()
        result = _report_from_health(health, branch_codes)
    except TimeoutError:
        result = _failure(total, "overall_deadline_exceeded")
    except Exception:
        result = _failure(total, "preflight_internal_failure")
    finally:
        if owned_adapter:
            try:
                await adapter.close()
            except Exception:
                result = _failure(total, "client_close_failed")
    return result


def main() -> int:
    try:
        report = asyncio.run(run_probe())
    except Exception:
        # Adapter construction or loop setup can fail before run_probe's own
        # sanitization. Do not let a traceback reach Cloud Logging.
        report = _failure(len(ENFORCEMENT_BRANCHES), "probe_runtime_failure")
    print(report.to_json())
    return 0 if report.result == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
