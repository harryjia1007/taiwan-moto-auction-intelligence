# Taipei Shwoo Adapter

Official source: <https://shwoo.gov.taipei/shwoo/browse/browse00/>

The adapter obtains a persistent session from the public browse page and submits keyword searches for both unrestricted and recycler-only listings. It separately submits the official completed-result form because its AUID links and titles are server-rendered only after POST. AUIDs are deduplicated before the adapter fetches detail HTML and official images, then parses normalized fields with exact evidence text.

Every official image URL discovered in the detail HTML is fetched before parsing, checksum-addressed in the private artifact bucket, and linked to the listing in source order. The artifact retains the URL written in the official HTML even when the image endpoint redirects; this keeps parsed photo references connected to their cached bytes. Reprocessing may update order and last-seen time but never clears an existing artifact/checksum/storage path merely because an offline reprocess has no image bytes.

Keywords cover motorcycles (`機車`, `機器腳踏車`, `重機`, `電動機車`, `汽機車`) and cars (`汽車`, `小客車`, `貨車`, `客貨兩用車`, `休旅車`, `轎車`, `廂型車`). Results are deduplicated by AUID before fetching. No login, favorites, bidding, or CAPTCHA behavior is automated. If the public form contract becomes unavailable, the adapter reports `DEGRADED`; Playwright is a separately documented fallback and is not silently enabled.

Commands:

```bash
python -m ingest healthcheck --source shwoo
python -m ingest sync --source shwoo
python -m ingest publish-public-shwoo
python -m ingest reprocess --source shwoo --from-parser-version 1.0.0
```

`reprocess` reads checksum-addressed private artifacts and never performs a live source request. A zero-result or failed live run preserves all prior records and is surfaced through source health warnings.

`publish-public-shwoo` is the hosted scheduler path. It uses server-only Supabase credentials, writes official HTML/images to the private checksum-addressed bucket, retains private normalized snapshots, and updates the backward-compatible `public_live_motorcycle_listings` table with explicit `vehicle_type` and `car_category` fields. The public projection includes recent official plates for 30 days after auction end, but excludes people, phone numbers, engine/frame/VIN identifiers, evidence text, cached artifact paths, and service credentials. Mixed car/motorcycle lots remain bulk listings and do not inherit one vehicle's specifications as another's.
