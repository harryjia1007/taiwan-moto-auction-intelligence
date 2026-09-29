# Architecture

Taiwan Moto Auction Intelligence is a read-only intelligence system for official Taiwanese motorcycle auctions. It separates collection from presentation and retains enough source material to reproduce every normalized fact.

```text
Source authorization registry -> policy preflight -> discovery -> fetch
-> private raw artifact storage -> parse -> conservative normalization
-> evidence resolution -> Supabase PostgreSQL
   |-> authenticated API -> owner-only full-fidelity zh-TW dashboard
   `-> minimized public projection -> harryjia.com public marketplace

Independent synthetic data -> repository `/demo` portfolio surface
```

The Next.js application never calls official auction sites. Scheduled Python workers own all network access. Each source adapter is independently testable and records its own sync health. PostgreSQL stores normalized, historical entities; private Supabase Storage keeps checksum-addressed raw artifacts and cached images.

## Trust boundaries

- Official HTML, documents, and images are untrusted input.
- Only registered HTTPS hosts may be fetched.
- Owner browser clients receive authenticated, row-level-security-filtered operational data.
- Anonymous clients can read only active rows from the minimized listing projection and the sanitized source-health projection; they cannot read operational tables, evidence, artifacts, owner favorites, or settings.
- Service-role and database credentials exist only in ingestion or server environments.
- Missing, negative, conflicting, inferred, and calculated values remain distinguishable.
- The repository `/demo` and its legal pages have no Supabase, official-source, private API, or artifact dependency. The separate harryjia.com marketplace may read the two anonymous projections but never private tables or Storage.
- Every live adapter is denied by default unless its reviewed policy is `ALLOW`; manual manifests never authorize CAPTCHA automation.

## Source coverage and authorization

Eight independent source adapters exist: Shwoo, central Judicial manifest import, central Administrative Enforcement offline import, MOJ centralized auctions, PCC dataset 7263, Customs HTML, the 13 Administrative Enforcement branch CMS sites, and Judicial Yuan main-site supplemental notices. Five `ALLOW` sources are configured in the GitHub-hosted matrix: MOJ, PCC, Customs, branch CMS, and Judicial supplemental notices. Configuration is not proof of operation; a source is hosted-live only after the release migrations, secrets, workflow conclusion, matching `sync_runs` row, persisted artifacts/snapshots, and published health row are verified. Shwoo remains a separately operated Taiwan-network batch candidate. Central Judicial and the central Administrative Enforcement CAPTCHA search are manual-only; the system never submits, recognizes, reuses, or bypasses a CAPTCHA. Each automated source is host-scoped, preflighted, rate-limited, and failure-isolated.
