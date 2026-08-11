# Contributing

Thank you for helping make Taiwanese public auction information easier to verify and reuse.

## Before opening a change

1. Search existing issues and discussions.
2. Open an issue before a large architectural change or a new live-source adapter.
3. Never include credentials, personal data that is not necessary for the official record, or unsanitized downloaded artifacts in a pull request.
4. Do not bypass CAPTCHA, login, anti-bot controls, robots restrictions, paywalls, or explicit rate limits.

## Good first contributions

- Improve zh-TW or English documentation.
- Add accessibility tests or keyboard-navigation fixes.
- Add a sanitized parser fixture reproducing a public source format.
- Improve error messages, source-health reporting, or evidence links.
- Research an official public source and document its access constraints without implementing a fetcher.

Use the issue forms so the maintainer can help scope the work.

## Development workflow

```bash
pnpm install
cp .env.example apps/web/.env.local
cp .env.example services/ingest/.env
pnpm test
pnpm lint
pnpm build
```

For ingestion work, use Python 3.12 and run:

```bash
python -m pip install -r services/ingest/requirements-dev.lock
python -m pip install --no-deps -e services/ingest
python -m pytest services/ingest/tests
```

Parser tests must use sanitized, minimal fixtures. Network calls do not belong in unit tests.

## Data integrity requirements

- Preserve exact source URLs, retrieval timestamps, checksums, and raw-artifact references.
- Keep `UNKNOWN`, `NO`, conflicting, inferred, and calculated values distinct.
- Do not merge uncertain vehicle identities to improve apparent coverage.
- Preserve auction rounds and historical snapshots.
- Treat official HTML, PDFs, images, and filenames as untrusted input.
- Update source status only after the documented success condition is met.

Read `AGENTS.md`, `ARCHITECTURE.md`, and the relevant page under `docs/` before changing domain behavior.

## Pull requests

Keep pull requests focused. Explain the user-visible outcome, provenance implications, tests run, and any change to source coverage. CI must pass before merge. A maintainer may ask for a smaller fixture or a safer failure mode even when the parser works on the current source page.

By contributing, you agree that your contribution is licensed under Apache-2.0.
