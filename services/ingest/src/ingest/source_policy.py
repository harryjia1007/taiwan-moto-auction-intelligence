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
        "moj_auction", AccessDecision.ALLOW, "https://auction.moj.gov.tw/robots.txt", date(2026, 8, 18),
        "Access is approved only for the central auction.moj.gov.tw portal. A central redirect does not extend "
        "that approval to an agency subdomain; unreviewed detail hosts remain uncontacted and the exact central "
        "list-row evidence is retained as a partial record.",
    ),
    "moj_enforcement": SourceAccessPolicy(
        "moj_enforcement", AccessDecision.MANUAL_ONLY, "https://www.tpkonsale.moj.gov.tw/", date(2026, 8, 15),
        "Discovery requires a human-completed CAPTCHA; only validated detail manifests may be processed.",
    ),
    "moj_enforcement_cms": SourceAccessPolicy(
        "moj_enforcement_cms", AccessDecision.ALLOW,
        "https://www.tpy.moj.gov.tw/robots.txt", date(2026, 8, 20),
        "ALLOW is limited to the explicitly registered 13 Administrative Enforcement branch CMS hosts. "
        "Every run rechecks each same-host robots.txt and declared sitemap before reading bounded public "
        "announcement lists. This decision does not extend to the CAPTCHA-gated central search.",
    ),
    "pcc": SourceAccessPolicy(
        "pcc", AccessDecision.ALLOW, "https://web.pcc.gov.tw/robots.txt", date(2026, 8, 18),
        "ALLOW is based on the published machine-readable asset-sale dataset 7263, not an inference from "
        "an ambiguous robots response. The dataset is free under OGDL 1.0 and updated each working day; "
        "exact matched detail pages remain limited to HTTPS on web.pcc.gov.tw.",
    ),
    "customs": SourceAccessPolicy(
        "customs", AccessDecision.ALLOW, "https://web.customs.gov.tw/robots.txt", date(2026, 8, 19),
        "The four Customs announcement lists and HTML detail pages are public and not disallowed. "
        "The robots policy excludes /download/; attachments are therefore linked as official evidence "
        "but never downloaded or mirrored.",
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
