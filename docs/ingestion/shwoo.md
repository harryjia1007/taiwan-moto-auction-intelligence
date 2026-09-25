# Taipei Shwoo Adapter

Official source: <https://shwoo.gov.taipei/shwoo/browse/browse00/>

The adapter freshly loads and validates `https://shwoo.gov.taipei/robots.txt` at the start of every discovery, then obtains a persistent session from the public browse page and submits keyword searches for both unrestricted and recycler-only listings. A verified policy is cached only for that operation; a failed refresh never reuses a prior allow result. The adapter separately submits the official completed-result form because its AUID links and titles are server-rendered only after POST. Every redirect target remains exact-host HTTPS and must pass the loaded robots policy before contact. AUIDs are deduplicated before the adapter fetches detail HTML and official images, then parses normalized fields with exact evidence text. If one active keyword/category query times out after bounded retries, or the completed-result query fails, already discovered records are retained but a discovery warning makes the run `PARTIAL`; the last successful timestamp must not advance. HTTP 403/429 and robots denial still stop collection rather than being downgraded to partial keyword results.

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

Auction status is derived only from explicit official outcome text and a parsed deadline. A current listing whose deadline is missing remains `ANNOUNCED` (date unknown), not `SCHEDULED`; a disappeared page is never interpreted as sold.

`publish-public-shwoo` is the hosted scheduler path. It uses server-only Supabase credentials, writes official HTML/images to the private checksum-addressed bucket, retains private normalized snapshots, and updates the backward-compatible `public_live_motorcycle_listings` table with explicit `vehicle_type` and `car_category` fields. The public projection includes only partially masked plates for 30 days after auction end; the final two or three characters are hidden. It excludes people, phone numbers, complete plates, engine/frame/VIN identifiers, evidence text, cached artifact paths, and service credentials. Mixed car/motorcycle lots remain bulk listings and do not inherit one vehicle's specifications as another's.

Shwoo is currently excluded from the GitHub-hosted workflow because full discovery repeatedly timed out from hosted runner addresses, even though health checks and Taiwan-network publishing succeeded. In the 2026-08-16 failed GitHub Actions runs, the first browse-page GET reached an HTTP read timeout after three 60-second attempts; this is not evidence that no listings existed, and the exact underlying network/server cause is unproven. A bounded read-only request from the Taiwan Mac on 2026-09-25 returned the same official browse page with HTTP 200 in 2.1 seconds. It remains a separately runnable approved source, not a twice-daily hosted source. A Shwoo failure never cancels the other scheduled sources, never clears prior records, and is shown separately in public source freshness. Restoring unattended operation requires a Taiwan-network batch worker with protected credentials, an awake/available host, independent run/freshness checks, and a rollback switch; merely adding it back to the GitHub-hosted matrix would repeat the known failure.
