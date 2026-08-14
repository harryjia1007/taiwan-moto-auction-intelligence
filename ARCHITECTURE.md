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

Five source adapters exist, but only Taipei Shwoo and the MOJ centralized seized-property portal currently have `ALLOW` policies for private scheduled ingestion. Judicial live discovery is `DISABLED`; its existing private artifacts may only be reprocessed offline. Government e-Procurement is `REVIEW_REQUIRED` and excluded from schedules. Administrative Enforcement is `MANUAL_ONLY`: a human may provide validated detail URLs after completing the official CAPTCHA, but the system never submits, recognizes, or reuses that CAPTCHA. Direct police/traffic and Customs remain explicit planning records.
