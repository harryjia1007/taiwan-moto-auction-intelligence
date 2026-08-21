# Source Registry

Statuses are `PLANNED`, `PARTIAL`, `ACTIVE`, `DEGRADED`, or `DISABLED`. `ACTIVE` means a live run completed successfully; code presence alone is insufficient.

| Family | Coverage | Status | Automation |
|---|---|---:|---|
| Taipei Shwoo | Nationwide participating public organizations | PARTIAL until first live sync | `ALLOW`; private form/detail collection within `/shwoo/` |
| Judicial auctions | Judicial Yuan plus all 22 district courts | PARTIAL / MANUAL_ONLY | Human-reviewed official PDF manifests can be imported without querying or mirroring the blocked central site; unattended discovery awaits a replacement official feed |
| Court asset disposal | District-court public asset disposal notices distributed through PCC | PARTIAL | Covered only when dataset 7263 explicitly identifies a car, motorcycle, or vehicle; this is public asset disposal, not judicial execution |
| Administrative enforcement central search | Nationwide central index | PARTIAL / MANUAL_ONLY | Human completes the official CAPTCHA and exports verified detail URLs; no CAPTCHA automation |
| Administrative enforcement branch CMS | 13 branches | PARTIAL until a successful all-branch run | `ALLOW`; each branch robots + sitemap is rechecked, then bounded recent public announcement lists are read |
| Government e-Procurement asset sales | Nationwide public organizations; official feed contains the latest week | PARTIAL until first successful scheduled run | `ALLOW`; dataset 7263 XML discovery, exact same-host HTTPS detail matching, twice-daily checks against a working-day daily feed |
| Prosecutors / seized property | MOJ centralized portal plus 22 offices | PARTIAL | Central public vehicle category, announcement, attachment, and private photo caching; hosted sync twice daily. Photos are not republished anonymously. Legacy rows that redirect to an unreviewed agency host retain their exact central-list summary and remain visibly partial instead of disappearing or broadening the allowlist. |
| Police and traffic | Dynamically discovered | PLANNED | Procurement-first, direct enrichment |
| Customs | Keelung, Taipei, Taichung, Kaohsiung | PARTIAL until first successful scheduled run | `ALLOW` for official HTML; `/download/` attachments are official outbound links and are not fetched or mirrored |
| Paid vehicle registry enrichment | Owner-authorized per-record enrichment, not discovery coverage | PLANNED (enrichment only) | Manual login and explicit charge confirmation; no motorcycle mileage |

Organization rows are seeded independently of adapter status so future sources can link to canonical agencies without changing application logic.

The database `source_access_policies` registry is the operational gate. Every row records a decision (`ALLOW`, `MANUAL_ONLY`, `REVIEW_REQUIRED`, or `DISABLED`), robots and terms locations, photo rights, personal-data risk, rationale, and review date. Adapters check the matching code policy before discovery and fail closed for every non-`ALLOW` decision. A healthcheck proving that a page is readable never changes this authorization decision. Access permission and republication permission are evaluated separately: Judicial Yuan's OGL declaration supports attributed reuse and ordinary linking, but it does not authorize automation against a path whose access policy disallows robots, nor does it cover excluded third-party media or remove Personal Data Protection Act duties.

The MOJ `ALLOW` decision is host-scoped to `auction.moj.gov.tw`. Some historical central rows redirect to individual prosecutor-office hosts whose `robots.txt` endpoints currently redirect to ordinary HTML rather than publishing a usable robots policy. Those hosts are not inherited into the central allowlist. The collector does not contact them: it stores the exact vehicle row bytes already returned by the approved central list, publishes only fields proven by that row, and records a partial-detail warning. A changed list row that cannot be preserved fails explicitly.

`Government e-Procurement` is a nationwide distribution channel, not a disposal-origin label. A court selling its own obsolete scooter through PCC is `SCRAP_DISPOSAL`, not `JUDICIAL_EXECUTION`; a police notice for unclaimed impounded scooters is `IMPOUNDED_UNCLAIMED`. The implemented Judicial Yuan adapter is the authoritative `JUDICIAL_EXECUTION` channel. Administrative execution remains separate so the dashboard does not conflate legally different auctions.

The PCC `ALLOW` decision is based specifically on the Public Construction Commission's published dataset 7263: free OGDL 1.0 XML updated each working day, not on an inference from the website's robots response. Discovery reads that feed once and filters only explicit vehicle terms. Exact detail resolution stays on `web.pcc.gov.tw` over HTTPS and must match all five published identity fields; ambiguous matches are rejected.

Administrative Enforcement branch CMS is a separate source from the central CAPTCHA search. Its allowlist contains exactly 13 named `*.moj.gov.tw` hosts, not a wildcard. Each run fetches that branch's robots file and declared same-host sitemap before following bounded homepage announcement links. A partial branch outage is reported as partial coverage, not as zero auctions.

Customs collection covers the four official announcement lists and their HTML detail pages. Because the current robots policy excludes `/download/`, the collector records those attachment URLs as official links but does not request or mirror their bytes. A vehicle mentioned only inside an attachment remains an explicit coverage gap.

The dashboard translates source states into user-facing Chinese: `ACTIVE` is `正式同步`, `PARTIAL` is `試運轉`, `DEGRADED` is `需注意`, `DISABLED` is `已停用`, and `PLANNED` is `未實作`. A source is never presented as formally online merely because adapter code exists. Administrative Enforcement central search remains manual-only; its 13-branch CMS source stays `PARTIAL` until every branch has completed a healthy scheduled run, because branch outages and CAPTCHA-gated central discovery prevent a claim of continuous nationwide coverage.
