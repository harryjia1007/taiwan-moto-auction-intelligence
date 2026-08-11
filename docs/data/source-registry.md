# Source Registry

Statuses are `PLANNED`, `PARTIAL`, `ACTIVE`, `DEGRADED`, or `DISABLED`. `ACTIVE` means a live run completed successfully; code presence alone is insufficient.

| Family | Coverage | Status | Automation |
|---|---|---:|---|
| Taipei Shwoo | Nationwide participating public organizations | PARTIAL until first live sync | Public form/detail collection |
| Judicial auctions | Judicial Yuan central query plus all 22 district courts | PARTIAL until first DB-backed live sync | Public structured search plus official PDF preservation |
| Court asset disposal | District-court public asset disposal notices | PARTIAL through Government e-Procurement | Procurement discovery; direct court pages remain enrichment |
| Administrative enforcement | 13 branches | PLANNED | CAPTCHA-safe/manual fallback |
| Government e-Procurement asset sales | Nationwide public organizations | PARTIAL until first DB-backed live sync | Public keyword search and detail collection; agency documents retained for registered-domain enrichment |
| Prosecutors | 22 local prosecutors offices | PLANNED | Reusable MOJ CMS adapter |
| Police and traffic | Dynamically discovered | PLANNED | Procurement-first, direct enrichment |
| Customs | Keelung, Taipei, Taichung, Kaohsiung | PLANNED | Announcement and attachment parsing |
| Paid vehicle registry | Owner-authorized per-record enrichment | PLANNED | Manual login and explicit charge confirmation; no motorcycle mileage |

Organization rows are seeded independently of adapter status so future sources can link to canonical agencies without changing application logic.

`Government e-Procurement` is a nationwide distribution channel, not a disposal-origin label. A court selling its own obsolete scooter through PCC is `SCRAP_DISPOSAL`, not `JUDICIAL_EXECUTION`; a police notice for unclaimed impounded scooters is `IMPOUNDED_UNCLAIMED`. The implemented Judicial Yuan adapter is the authoritative `JUDICIAL_EXECUTION` channel. Administrative execution remains separate so the dashboard does not conflate legally different auctions.
