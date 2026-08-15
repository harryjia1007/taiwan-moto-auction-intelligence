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

The `motorcycle_marketplace_listing` owner-only read model exposes normalized `county`, `display_price`, `has_cached_photo`, and `search_text` columns. These support database-side filtering, exact result counts, and stable sort-aware keyset pagination. A cached-photo flag is distinct from an official remote image URL.

`photos` stores one row per official source image with its source URL, immutable artifact reference, private storage path, checksum, availability, and source order. A row belongs to exactly one `vehicle` or one inseparable bulk `lot`. Marketplace reads sign every available ordered storage path; the list endpoint must not collapse the collection to its cover image.

`vehicle_category` uses `ORDINARY_LIGHT`, `ORDINARY_HEAVY`, `LARGE_HEAVY`, `ELECTRIC_MOTORCYCLE`, `HEAVY_UNSPECIFIED`, or `UNKNOWN` on both vehicles and inseparable lots. The value is normalized only from explicit official wording. It is not derived from displacement because derived class and official class are different claims.

`vehicles.displacement_cc` has a separate B-tree index for explicit CC filtering. `UNKNOWN` matches only SQL `NULL`; the shopping ranges 125-or-less, 126–150, 151–250, 251–550, and over-550 never overlap. These ranges do not replace the separate official motorcycle class.

Private raw bytes receive a `retention_until` deadline based on the auction end time when known, otherwise fetch time, plus 12 months. Retention deletion removes only Storage bytes and appends an `artifact_tombstones` audit row; immutable checksum, source, and artifact metadata remain. Deletion is an explicit maintenance command and defaults to dry-run.
