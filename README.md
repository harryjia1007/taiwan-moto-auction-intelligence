# Taiwan Moto Auction Intelligence

[![CI](https://github.com/harryjia1007/taiwan-moto-auction-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/harryjia1007/taiwan-moto-auction-intelligence/actions/workflows/ci.yml)
[![CodeQL](https://github.com/harryjia1007/taiwan-moto-auction-intelligence/actions/workflows/codeql.yml/badge.svg)](https://github.com/harryjia1007/taiwan-moto-auction-intelligence/actions/workflows/codeql.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

把分散在臺灣政府網站與官方文件中的機車拍賣資訊，整理成可搜尋、可追溯、可重現的開源資料管線與唯讀儀表板。

The project turns fragmented Taiwanese public-sector motorcycle-auction notices into a searchable, evidence-preserving dataset. It is designed for buyers, civic technologists, journalists, and researchers who need to trace every normalized fact back to an official source.

> **Project status:** pre-1.0 and seeking early contributors. Three public read-only adapters are implemented, but source coverage remains `PARTIAL` until database-backed live runs are completed. The project never claims planned coverage as active coverage.

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
| [Judicial Yuan movable-property auctions](docs/ingestion/judicial.md) | Central search across all 22 district courts; structured rows and official PDF preservation | `PARTIAL` |
| [Government e-Procurement asset sales](docs/ingestion/pcc.md) | Nationwide public asset-sale discovery and detail collection | `PARTIAL` |
| [Taipei Shwoo](docs/ingestion/shwoo.md) | Search, detail, auction-round, evidence, and photo-preserving ingestion | `PARTIAL` |

Administrative enforcement, prosecutors, Customs, and direct police/traffic sources are tracked as `PLANNED`. See the [source registry](docs/data/source-registry.md) for the exact distinction between implemented code and verified live coverage.

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

### Run the fixture dashboard

```bash
pnpm install
cp .env.example apps/web/.env.local
cp .env.example services/ingest/.env
node scripts/local-web-server.mjs start
```

Open `http://127.0.0.1:3000`. Fixture mode uses sanitized official examples and does not imply that a nationwide production sync has completed.

### Run the local stack

```bash
pnpm db:start
pnpm db:reset
pnpm dev
```

Local email links are visible in Supabase Mailpit. Production builds reject fixture-mode authentication bypasses.

### Verify a change

```bash
pnpm test
pnpm lint
pnpm build
pnpm test:e2e
python -m pytest services/ingest/tests
```

The complete verification matrix also includes Supabase database tests in CI.

## Run read-only ingestion

After placing local development credentials in `services/ingest/.env`:

```bash
pnpm ingest:health
pnpm ingest
```

Run a single source with `pnpm ingest:shwoo`, `pnpm ingest:pcc`, or `pnpm ingest:judicial`. Reprocess stored artifacts without contacting a live source with:

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
