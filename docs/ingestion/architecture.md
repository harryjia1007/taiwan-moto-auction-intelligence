# Ingestion Architecture

Adapters implement independent asynchronous discovery, fetch, parse, and healthcheck stages. A failed item is recorded without rolling back successful items, while a failed source never changes prior auction statuses.

Network safeguards include an HTTPS host allowlist, one-request-per-second pacing, two retries with bounded backoff, 20-second timeouts, a 25 MiB artifact limit, checksum-addressed writes, and MIME validation. Downloads are treated as bytes; scripts and macros are never executed.

`python -m ingest sync --source shwoo`, `--source pcc`, and `--source judicial` run isolated discovery and persistence. `healthcheck` performs a bounded public-page check without ingestion. Reprocessing consumes stored artifacts with an explicit parser version. Repository source IDs and evidence parser names are selected per adapter rather than hard-coded to Shwoo.

The marketplace read model unions identified vehicles with inseparable official lots. A bulk notice without separable identities remains a lot and may be displayed, but it cannot be favorited as a made-up vehicle.
