# Ingestion Architecture

Adapters implement independent asynchronous discovery, fetch, parse, and healthcheck stages. A failed item is recorded without rolling back successful items, while a failed source never changes prior auction statuses.

Run health is explicit: a fully successful automated run promotes the source to `ACTIVE`, a mixed successful/failed run sets `PARTIAL`, and a run with no parsed records and one or more failures sets `DEGRADED`. `last_successful_at` advances only on a fully successful run (or a completed human-assisted Administrative Enforcement import), so a partial run cannot hide staleness.

Network safeguards include an HTTPS host allowlist, one-request-per-second pacing, two retries with bounded backoff, 20-second timeouts, a 25 MiB artifact limit, checksum-addressed writes, and MIME validation. Downloads are treated as bytes; scripts and macros are never executed. Storage writes are idempotent only when Supabase returns its exact duplicate-object signature (`409` / `Duplicate` / `KeyAlreadyExists`); authorization, bucket, and all other upload failures remain run failures.

`python -m ingest sync --source shwoo`, `--source pcc`, `--source judicial`, and `--source moj_auction` run isolated discovery and persistence. `moj_enforcement` accepts only a human-exported manifest of official `/Detail/Chattel?NO=` URLs; it never submits or solves the official CAPTCHA. `healthcheck` performs a bounded public-page check without ingestion. Reprocessing consumes stored artifacts with an explicit parser version. Repository source IDs and evidence parser names are selected per adapter rather than hard-coded to Shwoo.

The marketplace read model unions identified vehicles with inseparable official lots. A bulk notice without separable identities remains a lot and may be displayed, but it cannot be favorited as a made-up vehicle.
