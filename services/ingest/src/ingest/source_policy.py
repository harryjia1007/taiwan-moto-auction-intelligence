from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class AccessDecision(StrEnum):
    ALLOW = "ALLOW"
    MANUAL_ONLY = "MANUAL_ONLY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DISABLED = "DISABLED"


class SourceAccessBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceAccessPolicy:
    source: str
    decision: AccessDecision
    robots_url: str
    checked_on: date
    reason: str


SOURCE_POLICIES = {
    "shwoo": SourceAccessPolicy(
        "shwoo", AccessDecision.ALLOW, "https://shwoo.gov.taipei/robots.txt", date(2026, 8, 15),
        "Official robots rules allow the /shwoo/ application path; redistribution remains private-only.",
    ),
    "moj_auction": SourceAccessPolicy(
        "moj_auction", AccessDecision.ALLOW, "https://auction.moj.gov.tw/robots.txt", date(2026, 8, 15),
        "Official robots rules do not disallow the public auction portal.",
    ),
    "moj_enforcement": SourceAccessPolicy(
        "moj_enforcement", AccessDecision.MANUAL_ONLY, "https://www.tpkonsale.moj.gov.tw/", date(2026, 8, 15),
        "Discovery requires a human-completed CAPTCHA; only validated detail manifests may be processed.",
    ),
    "pcc": SourceAccessPolicy(
        "pcc", AccessDecision.REVIEW_REQUIRED, "https://web.pcc.gov.tw/robots.txt", date(2026, 8, 15),
        "The robots endpoint redirects to the site rather than publishing a usable policy; unattended collection is paused pending review.",
    ),
    "judicial": SourceAccessPolicy(
        "judicial", AccessDecision.MANUAL_ONLY, "https://aomp109.judicial.gov.tw/robots.txt", date(2026, 8, 15),
        "The central query currently disallows automated paths. Judicial site material is generally OGL v1 with attribution, "
        "but the former movable-auction dataset 49107 was permanently withdrawn and its legacy JSON is unavailable; "
        "human-reviewed official PDF manifests may be imported without querying or mirroring the blocked site. "
        "Unattended discovery stays disabled until a replacement official feed or written access path exists.",
    ),
}


def policy_for(source: str) -> SourceAccessPolicy:
    try:
        return SOURCE_POLICIES[source]
    except KeyError as exc:
        raise SourceAccessBlocked(f"No reviewed source-access policy exists for {source}") from exc


def require_live_access(source: str, *, human_manifest: bool = False) -> SourceAccessPolicy:
    policy = policy_for(source)
    if policy.decision == AccessDecision.ALLOW:
        return policy
    if policy.decision == AccessDecision.MANUAL_ONLY and human_manifest:
        return policy
    raise SourceAccessBlocked(
        f"Live access to {source} is {policy.decision}: {policy.reason} "
        "Stored artifacts may still be reprocessed offline."
    )
