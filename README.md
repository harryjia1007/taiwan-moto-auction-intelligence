# Taiwan Vehicle Auction Intelligence

[![CI](https://github.com/harryjia1007/taiwan-moto-auction-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/harryjia1007/taiwan-moto-auction-intelligence/actions/workflows/ci.yml)
[![CodeQL](https://github.com/harryjia1007/taiwan-moto-auction-intelligence/actions/workflows/codeql.yml/badge.svg)](https://github.com/harryjia1007/taiwan-moto-auction-intelligence/actions/workflows/codeql.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

把分散在臺灣政府網站與官方文件中的汽車、機車拍賣資訊，整理成可搜尋、可追溯、可重現的開源資料管線與唯讀儀表板。

The project turns fragmented Taiwanese public-sector car-and-motorcycle auction notices into a searchable, evidence-preserving dataset. It is designed for buyers, civic technologists, journalists, and researchers who need to trace every normalized fact back to an official source.

> **Project status:** private pre-1.0 system with a separate synthetic public Demo. Only Shwoo and the MOJ centralized portal are eligible for unattended schedules; Judicial records require a human-reviewed official PDF manifest and Government e-Procurement is paused for authorization review. Code presence never implies authorized or active coverage.

## Why this exists

Official auction information is split across structured search pages, PDFs, procurement notices, images, and agency-specific sites. Field names and legal contexts differ, old rounds can disappear from the easiest-to-find page, and missing data is easy to misread as a negative fact.

This project provides:

- a registry of official sources and explicit coverage status;
- independent, failure-isolated Python adapters;
- immutable raw-artifact and checksum support;
- conservative normalization and vehicle identity resolution;
- fact-level evidence links and historical auction snapshots;
- an authenticated zh-TW Next.js dashboard and API;
- sanitized fixtures and repeatable parser tests.

## Implemented source coverage

| Source family | Implemented capability | Current status |
|---|---|---|
| [Judicial Yuan movable-property auctions](docs/ingestion/judicial.md) | Human-reviewed official PDF links and structured fields can be imported without querying or mirroring the blocked central site | `PARTIAL / MANUAL_ONLY` |
| [Government e-Procurement asset sales](docs/ingestion/pcc.md) | Adapter retained but unattended access is paused pending written confirmation | `DEGRADED` |
| [Taipei Shwoo](docs/ingestion/shwoo.md) | Search, detail, auction-round, evidence, and photo-preserving ingestion | `PARTIAL` |
| [MOJ seized-property auctions](docs/ingestion/moj-auction.md) | Central vehicle-category discovery, announcement, attachment, and image preservation | `PARTIAL` |
| [Administrative Enforcement](docs/ingestion/moj-enforcement.md) | Human CAPTCHA search followed by validated detail, document, and photo ingestion | `PARTIAL` |

Customs and direct police/traffic sources remain `PLANNED`. Administrative Enforcement is not scheduled because discovery requires a human-completed CAPTCHA. See the [source registry](docs/data/source-registry.md) for the exact distinction between implemented code and verified live coverage.

## Architecture

```text
official source registry
  -> discovery and rate-limited fetch
  -> immutable raw artifacts + checksums
  -> parse and normalize
  -> conservative identity resolution
  -> evidence-linked Supabase PostgreSQL
  -> authenticated API and zh-TW dashboard
```

Collection is asynchronous. The web application never scrapes an official source during a user request. Adapters stop rather than bypassing login, CAPTCHA, anti-bot controls, or paid-query confirmation.

Read [ARCHITECTURE.md](ARCHITECTURE.md) for trust boundaries and [docs/data/evidence.md](docs/data/evidence.md) for provenance rules.

## Quick start

### Prerequisites

- Node.js 24 and pnpm 11
- Python 3.12 for ingestion development
- Docker Desktop
- Supabase CLI (installed by `pnpm install`)

Run `pnpm run doctor` before bootstrapping. It checks Node, the project-scoped Supabase CLI, a running Docker-compatible container runtime, configuration, and the committed pgTAP suite. A missing runtime affects the real local Supabase stack; the fixture dashboard and deterministic parser/UI tests can still run. The explicit `run` is required because pnpm also has an unrelated built-in command named `doctor`.

### Run the fixture dashboard

```bash
pnpm install
cp .env.example apps/web/.env.local
cp .env.example services/ingest/.env
node scripts/local-web-server.mjs start
```

Open `http://127.0.0.1:3000`. The owner dashboard fixture mode is private development data and does not imply that a nationwide production sync has completed. The public portfolio-safe surface is `http://127.0.0.1:3000/demo` and uses only synthetic cases.

### Run the local stack

```bash
pnpm db:verify
pnpm dev
```

`db:verify` starts Supabase, rebuilds the database from committed migrations and seed data, and executes pgTAP. Local email links are visible in Supabase Mailpit. Production builds reject fixture-mode authentication bypasses.

### Verify a change

```bash
pnpm test
pnpm lint
pnpm build
pnpm test:e2e
python -m pytest services/ingest/tests
```

The complete verification matrix also includes Supabase database tests in CI. The committed `database-tests.yml` workflow runs migrations, seed, and pgTAP in an isolated Linux environment with Docker, so database behavior is still verified when a developer's Mac lacks a compatible runtime.

## Run read-only ingestion

After placing local development credentials in `services/ingest/.env`:

```bash
pnpm ingest:health
pnpm ingest
```

Run an authorized scheduled source with `pnpm ingest:shwoo` or `pnpm ingest:moj-auction`. `pnpm ingest:pcc` intentionally fails closed while its policy is `REVIEW_REQUIRED`. Judicial records use a private, human-reviewed official-link manifest:

```bash
python -m ingest sync --source judicial --manifest ./private/judicial-official-links.json
```

The synthetic shape-only example is in `services/ingest/examples/judicial-manifest.example.json`; never commit a real manifest. Administrative Enforcement uses the documented private manifest and `pnpm ingest:moj-enforcement`; no CAPTCHA is automated. Reprocess stored artifacts without contacting a live source with:

```bash
pnpm ingest:reprocess -- --from-parser-version 1.0.0
```

The project does not store source-site passwords, automate bidding, bypass access controls, or trigger paid vehicle-registry queries without explicit human authorization.

## Contributing

Good first contributions include sanitized parser fixtures, source-health diagnostics, accessibility improvements, translation, documentation, and research on public official sources. Start with [CONTRIBUTING.md](CONTRIBUTING.md), the [roadmap](ROADMAP.md), or a GitHub issue.

Every data-source contribution must document provenance, access constraints, request-rate expectations, and failure behavior. Unknown data stays unknown; absence is never silently converted to `NO`.

## Governance and security

- [GOVERNANCE.md](GOVERNANCE.md) explains decision-making and maintainer responsibilities.
- [SECURITY.md](SECURITY.md) explains private vulnerability reporting and supported versions.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) sets community expectations.
- [docs/impact.md](docs/impact.md) records adoption evidence without inflating project status.

## License

Licensed under the [Apache License 2.0](LICENSE). Official-source content and linked government documents remain subject to their original terms; the license covers this repository's code and original documentation, not third-party source material.
