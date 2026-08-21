# Architecture

Taiwan Moto Auction Intelligence is a read-only intelligence system for official Taiwanese motorcycle auctions. It separates collection from presentation and retains enough source material to reproduce every normalized fact.

```text
Source authorization registry -> policy preflight -> discovery -> fetch
-> private raw artifact storage -> parse -> conservative normalization
-> evidence resolution -> Supabase PostgreSQL -> authenticated API -> private zh-TW dashboard

Independent synthetic data -> public `/demo` portfolio surface
```

The Next.js application never calls official auction sites. Scheduled Python workers own all network access. Each source adapter is independently testable and records its own sync health. PostgreSQL stores normalized, historical entities; private Supabase Storage keeps checksum-addressed raw artifacts and cached images.

## Trust boundaries

- Official HTML, documents, and images are untrusted input.
- Only registered HTTPS hosts may be fetched.
- Browser clients receive only authenticated, row-level-security-filtered data.
- Service-role and database credentials exist only in ingestion or server environments.
- Missing, negative, conflicting, inferred, and calculated values remain distinguishable.
- Public Demo and legal pages have no Supabase, official-source, private API, or artifact dependency.
- Every live adapter is denied by default unless its reviewed policy is `ALLOW`; manual manifests never authorize CAPTCHA automation.

## Source coverage and authorization

Seven independent source adapters exist. The hosted schedule covers the MOJ centralized portal, PCC dataset 7263, Customs four-office HTML, and the 13 Administrative Enforcement branch CMS sites. Shwoo remains an approved Taiwan-network batch source because GitHub-hosted full discovery repeatedly timed out. Judicial discovery and the separate Administrative Enforcement central CAPTCHA search are manual-only; the system never submits, recognizes, reuses, or bypasses a CAPTCHA. Each automated source is host-scoped, preflighted, rate-limited, and failure-isolated.
