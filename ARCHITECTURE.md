# Architecture

Taiwan Moto Auction Intelligence is a read-only intelligence system for official Taiwanese motorcycle auctions. It separates collection from presentation and retains enough source material to reproduce every normalized fact.

```text
Source registry -> discovery -> fetch -> raw artifact storage -> parse
-> normalization -> conservative identity resolution -> evidence resolution
-> Supabase PostgreSQL -> authenticated API -> zh-TW dashboard
```

The Next.js application never calls official auction sites. Scheduled Python workers own all network access. Each source adapter is independently testable and records its own sync health. PostgreSQL stores normalized, historical entities; private Supabase Storage keeps checksum-addressed raw artifacts and cached images.

## Trust boundaries

- Official HTML, documents, and images are untrusted input.
- Only registered HTTPS hosts may be fetched.
- Browser clients receive only authenticated, row-level-security-filtered data.
- Service-role and database credentials exist only in ingestion or server environments.
- Missing, negative, conflicting, inferred, and calculated values remain distinguishable.

## Active source coverage

Three source adapters are implemented: Taipei Shwoo, nationwide Government e-Procurement asset sales, and the Judicial Yuan central movable-property auction search covering all 22 district courts. The latter preserves both structured query rows and official auction PDFs. Administrative enforcement, prosecutors, direct police/traffic, and Customs remain explicit planning records. Every adapter uses public read-only pages and stops if automation would require login, CAPTCHA, or bypass behavior.
