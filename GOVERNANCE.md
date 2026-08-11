# Governance

Taiwan Moto Auction Intelligence is currently a maintainer-led, pre-1.0 open-source project.

## Roles

- **Contributor:** anyone who submits code, documentation, research, design, testing, or issue triage.
- **Reviewer:** a trusted contributor who regularly reviews a defined area.
- **Core maintainer:** a contributor with sustained responsibility for review, triage, releases, and project direction.
- **Primary maintainer:** the person accountable for final release, security, and governance decisions.

Harry (`@harryjia1007`) is the current primary maintainer.

## Decisions

Routine changes are decided through issue and pull-request review. Significant changes—new source families, identity-resolution rules, data-retention behavior, security boundaries, licensing, or governance—require a public design issue and a documented decision before implementation.

Consensus is preferred. When consensus cannot be reached, the primary maintainer makes the decision and records the rationale, alternatives, and material objections. Decisions must not trade away provenance, access-control compliance, or the distinction between unknown and negative facts for faster apparent coverage.

## Becoming a maintainer

Maintainer access is based on sustained, high-quality contributions; respectful review and issue triage; sound judgment around public-source constraints; and willingness to share ongoing maintenance duties. There is no contribution-count threshold.

## Releases and deprecation

Until 1.0, breaking changes may occur but must be documented. Releases require passing CI, a reviewed change summary, known limitations, and accurate source-coverage status. A source adapter may be marked `DEGRADED` or `DISABLED` instead of silently returning stale or misleading data.

## Changes to governance

Governance changes use the same public issue and pull-request process. As the maintainer group grows, this document should evolve toward shared approval and an explicit conflict-resolution process.
