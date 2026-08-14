# Source Registry

Statuses are `PLANNED`, `PARTIAL`, `ACTIVE`, `DEGRADED`, or `DISABLED`. `ACTIVE` means a live run completed successfully; code presence alone is insufficient.

| Family | Coverage | Status | Automation |
|---|---|---:|---|
| Taipei Shwoo | Nationwide participating public organizations | PARTIAL until first live sync | `ALLOW`; private form/detail collection within `/shwoo/` |
| Judicial auctions | Judicial Yuan plus all 22 district courts | PARTIAL / MANUAL_ONLY | Human-reviewed official PDF manifests can be imported without querying or mirroring the blocked central site; unattended discovery awaits a replacement official feed |
| Court asset disposal | District-court public asset disposal notices | REVIEW_REQUIRED | No unattended procurement discovery pending written clarification |
| Administrative enforcement | 13 branches | PARTIAL | Human completes official CAPTCHA and exports detail URLs; detail, document, and photo ingestion is automated |
| Government e-Procurement asset sales | Nationwide public organizations | DEGRADED / REVIEW_REQUIRED | Unattended access paused pending written confirmation |
| Prosecutors / seized property | MOJ centralized portal plus 22 offices | PARTIAL until first DB-backed live sync | Central public vehicle category, announcement, attachment, and photo collection |
| Police and traffic | Dynamically discovered | PLANNED | Procurement-first, direct enrichment |
| Customs | Keelung, Taipei, Taichung, Kaohsiung | PLANNED | Announcement and attachment parsing |
| Paid vehicle registry enrichment | Owner-authorized per-record enrichment, not discovery coverage | PLANNED (enrichment only) | Manual login and explicit charge confirmation; no motorcycle mileage |

Organization rows are seeded independently of adapter status so future sources can link to canonical agencies without changing application logic.

The database `source_access_policies` registry is the operational gate. Every row records a decision (`ALLOW`, `MANUAL_ONLY`, `REVIEW_REQUIRED`, or `DISABLED`), robots and terms locations, photo rights, personal-data risk, rationale, and review date. Adapters check the matching code policy before discovery and fail closed for every non-`ALLOW` decision. A healthcheck proving that a page is readable never changes this authorization decision. Access permission and republication permission are evaluated separately: Judicial Yuan's OGL declaration supports attributed reuse and ordinary linking, but it does not authorize automation against a path whose access policy disallows robots, nor does it cover excluded third-party media or remove Personal Data Protection Act duties.

`Government e-Procurement` is a nationwide distribution channel, not a disposal-origin label. A court selling its own obsolete scooter through PCC is `SCRAP_DISPOSAL`, not `JUDICIAL_EXECUTION`; a police notice for unclaimed impounded scooters is `IMPOUNDED_UNCLAIMED`. The implemented Judicial Yuan adapter is the authoritative `JUDICIAL_EXECUTION` channel. Administrative execution remains separate so the dashboard does not conflate legally different auctions.

The dashboard translates source states into user-facing Chinese: `ACTIVE` is `正式同步`, `PARTIAL` is `試運轉`, `DEGRADED` is `需注意`, `DISABLED` is `已停用`, and `PLANNED` is `未實作`. A source is never presented as formally online merely because adapter code exists. Administrative Enforcement remains `PARTIAL` after successful manual imports because CAPTCHA-gated discovery cannot claim continuous nationwide coverage.
