# Taipei Shwoo Adapter

Official source: <https://shwoo.gov.taipei/shwoo/browse/browse00/>

The adapter obtains a persistent session from the public browse page and submits keyword searches for both unrestricted and recycler-only listings. It separately submits the official completed-result form because its AUID links and titles are server-rendered only after POST. AUIDs are deduplicated before the adapter fetches detail HTML and official images, then parses normalized fields with exact evidence text.

Every official image URL discovered in the detail HTML is fetched before parsing, checksum-addressed in the private artifact bucket, and linked to the listing in source order. The artifact retains the URL written in the official HTML even when the image endpoint redirects; this keeps parsed photo references connected to their cached bytes. Reprocessing may update order and last-seen time but never clears an existing artifact/checksum/storage path merely because an offline reprocess has no image bytes.

Keywords: `機車`, `機器腳踏車`, `重機`, `電動機車`, `汽機車`. Results are deduplicated by AUID before fetching. No login, favorites, bidding, or CAPTCHA behavior is automated. If the public form contract becomes unavailable, the adapter reports `DEGRADED`; Playwright is a separately documented fallback and is not silently enabled.

Commands:

```bash
python -m ingest healthcheck --source shwoo
python -m ingest sync --source shwoo
python -m ingest reprocess --source shwoo --from-parser-version 1.0.0
```

`reprocess` reads checksum-addressed private artifacts and never performs a live source request. A zero-result or failed live run preserves all prior records and is surfaced through source health warnings.
