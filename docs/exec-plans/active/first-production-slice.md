# First Production Slice

## Deliverables

- [x] Repository and durable documentation
- [x] Supabase schema, policies, registry seed, and fixtures implemented
- [x] Shwoo adapter, storage, persistence, health, reprocessing, and tests
- [x] Government e-Procurement nationwide public-asset adapter and bulk-lot read model
- [x] Judicial Yuan central movable-property adapter for all 22 district courts, including official PDF preservation
- [x] Private zh-TW dashboard and API
- [ ] Verification and completion record

The plan moves to `completed` only after deterministic tests and builds pass. Live smoke status is recorded separately because live official availability is not a deterministic test dependency.

## Verification record — 2026-08-11

- Python: 24 fixture, parser, adapter, and storage tests pass.
- TypeScript: 11 shared/web unit tests pass; workspace typecheck/lint and the Next production build pass.
- Playwright: 6 desktop/mobile owner, source-filter, evidence, favorite, health, and responsive scenarios pass.
- Live Shwoo source: official healthcheck returned `ACTIVE`; discover → fetch → parse found 12 completed motorcycle results and parsed AUID `937754` with 5 artifacts and 7 evidence fields.
- Live Government e-Procurement source: official nationwide asset-sale healthcheck returned `ACTIVE`.
- Live Judicial Yuan source: official healthcheck returned `ACTIVE`; discovery found 7 current motorcycle auctions across Taipei, Taichung, Tainan, Kaohsiung, and Ciaotou (橋頭) district courts. A sampled case preserved JSON plus the official PDF and produced 9 evidence references.
- Fixture dashboard: 12 sanitized real official examples are visible, including all 7 motorcycles returned by the verified Judicial Yuan query plus Shwoo and Government e-Procurement examples; URL-backed source and disposal-origin filters are verified.
- Pending environment check: local Supabase migration, seed, pgTAP, and persisted live sync require Docker Desktop, which is not installed on the verification host. Until that check passes, this plan intentionally remains in `active`.
