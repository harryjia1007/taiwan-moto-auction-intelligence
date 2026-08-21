# First Production Slice

## Deliverables

- [x] Repository and durable documentation
- [x] Supabase schema, policies, registry seed, and fixtures implemented
- [x] Shwoo adapter, storage, persistence, health, reprocessing, and tests
- [x] Government e-Procurement nationwide public-asset adapter and bulk-lot read model
- [x] Judicial Yuan human-reviewed manifest import for all 22 district courts, retaining official PDF links without querying or mirroring the blocked central site
- [x] Private zh-TW dashboard and API
- [ ] Verification and completion record

The plan moves to `completed` only after deterministic tests and builds pass. Live smoke status is recorded separately because live official availability is not a deterministic test dependency.

## Historical verification record — 2026-08-11

These observations predate the current source-access policy and are not evidence of present automated coverage. The 2026-08-15 review changed Judicial discovery to `MANUAL_ONLY`; health/readability never overrides that decision.

- Python: 24 fixture, parser, adapter, and storage tests pass.
- TypeScript: 11 shared/web unit tests pass; workspace typecheck/lint and the Next production build pass.
- Playwright: 6 desktop/mobile owner, source-filter, evidence, favorite, health, and responsive scenarios pass.
- Historical Shwoo observation: a read-only smoke run found 12 completed motorcycle results and parsed AUID `937754` with 5 artifacts and 7 evidence fields. Current source status must come from a later completed sync run.
- Historical Government e-Procurement observation: the endpoint was readable. Readability alone does not promote the source to `ACTIVE`; current status requires a completed official-feed sync.
- Superseded Judicial observation: a former automated query returned 7 motorcycle notices. Current robots policy disallows unattended discovery, so this result must not be repeated or presented as current coverage. Only human-reviewed official links may be imported, without downloading or mirroring the PDF.
- Historical fixture dashboard: 12 sanitized examples were visible and URL-backed source and disposal-origin filters were verified. Fixtures demonstrate UI behavior and are not current source coverage.

## Current verification record — 2026-08-21

- Python ingestion suite: 126 tests pass.
- Workspace TypeScript lint/typecheck passes.
- Local migrations `202608210001_public_plate_retention_backfill.sql` and `202608210002_public_personal_data_redaction.sql` apply forward without resetting the database.
- Local pgTAP: 56 assertions pass, including plate retention, public personal-data and public-photo invariants.
- Hosted migration ledger is verified through `202608210002`; follow-up aggregate checks found zero Taiwan IDs in public text, zero unknown/expired public plates and zero public photo URLs.
- Remaining completion gates are the coordinated production build/E2E run and a successful policy-approved scheduled sync. Until those pass, this plan remains in `active`.
