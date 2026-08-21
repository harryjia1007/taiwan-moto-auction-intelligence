# Data Model

The database separates source provenance from normalized auction entities.

- Collection: `sources`, `source_endpoints`, `sync_runs`, `source_records`, `raw_artifacts`, `snapshots`
- Auction: `auction_cases`, `auction_events`, `lots`
- Vehicle: `vehicles`, `vehicle_identifiers`, `vehicle_observations`, `photos`, `documents`
- Trust: `field_evidence`, `cross_source_links`, `probable_duplicates`
- Normalization: `vehicle_brands`, `vehicle_models`, `vehicle_model_aliases`
- User: `favorites`, `saved_searches`
- Governance: `source_access_policies`, `data_subject_requests`, `artifact_tombstones`

Cases contain rounds; rounds contain lots; lots may contain one or many vehicles. Prices belong to events or snapshots and are never overwritten. Source records and artifacts are append-oriented.

The `vehicle_marketplace_listing` owner-only read model exposes normalized `county`, `display_price`, `has_cached_photo`, `vehicle_type`, `car_category`, and `search_text` columns. These support database-side filtering, exact result counts, and stable sort-aware keyset pagination. The older `motorcycle_marketplace_listing` view remains temporarily available for compatibility. A cached-photo flag is distinct from an official remote image URL.

The anonymous `public_live_motorcycle_listings` table is a separate least-privilege projection. It masks the final two or three characters of every plate, suppresses plates whose official end time is unknown, removes a plate 30 days after a verified end time, and excludes engine, frame and VIN identifiers entirely. Taiwan IDs, phone/email values and role-labelled names are redacted from every projected text field. An official URL containing personal data falls back to its source origin; an affected document URL is removed instead of being rewritten into a broken link. Full identifiers and unredacted source evidence remain only in owner-only normalized records, evidence and private artifacts.

Anonymous `photo_urls` remain empty for every current source because the present policies are private-cache-only or do not grant public photo redistribution. Owner-only `photos` rows and private Storage objects are unchanged. A future public image path requires both a source-specific rights decision and an exact-host HTTPS:443 allowlist.

`photos` stores one row per official source image with its source URL, immutable artifact reference, private storage path, checksum, availability, and source order. A row belongs to exactly one `vehicle` or one inseparable bulk `lot`. Marketplace reads sign every available ordered storage path; the list endpoint must not collapse the collection to its cover image.

`vehicle_category` uses `ORDINARY_LIGHT`, `ORDINARY_HEAVY`, `LARGE_HEAVY`, `ELECTRIC_MOTORCYCLE`, `HEAVY_UNSPECIFIED`, or `UNKNOWN` on both vehicles and inseparable lots. The value is normalized only from explicit official wording. It is not derived from displacement because derived class and official class are different claims.

`vehicle_type` separates `MOTORCYCLE`, `CAR`, `MIXED`, and `UNKNOWN`. Cars additionally use `car_category`: `PASSENGER`, `SUV`, `VAN`, `TRUCK`, `BUS`, `OTHER`, or `UNKNOWN`. An inseparable official lot containing both cars and motorcycles is `MIXED`; brand, model, displacement, motorcycle class, and car category remain unknown unless the official page provides separable per-vehicle identities.

`vehicles.displacement_cc` has a separate B-tree index for explicit CC filtering. Motorcycle shopping ranges 125-or-less, 126–150, 151–250, 251–550, and over-550 never overlap and apply only when `vehicle_type=MOTORCYCLE`; `UNKNOWN` matches only SQL `NULL`. Car engine displacement may be displayed as an official specification but is not placed into motorcycle shopping bands.

Private raw bytes receive a `retention_until` deadline based on the auction end time when known, otherwise fetch time, plus 12 months. Retention deletion removes only Storage bytes and appends an `artifact_tombstones` audit row; immutable checksum, source, and artifact metadata remain. Deletion is an explicit maintenance command and defaults to dry-run.
