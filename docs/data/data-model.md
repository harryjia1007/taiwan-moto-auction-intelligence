# Data Model

The database separates source provenance from normalized auction entities.

- Collection: `sources`, `source_endpoints`, `sync_runs`, `source_records`, `raw_artifacts`, `snapshots`
- Auction: `auction_cases`, `auction_events`, `lots`
- Vehicle: `vehicles`, `vehicle_identifiers`, `vehicle_observations`, `photos`, `documents`
- Trust: `field_evidence`, `cross_source_links`, `probable_duplicates`
- Normalization: `vehicle_brands`, `vehicle_models`, `vehicle_model_aliases`
- User: `favorites`, `saved_searches`

Cases contain rounds; rounds contain lots; lots may contain one or many vehicles. Prices belong to events or snapshots and are never overwritten. Source records and artifacts are append-oriented.

The `motorcycle_marketplace_listing` owner-only read model exposes normalized `county`, `display_price`, `has_cached_photo`, and `search_text` columns. These support database-side filtering, exact result counts, and stable sort-aware keyset pagination. A cached-photo flag is distinct from an official remote image URL.

`photos` stores one row per official source image with its source URL, immutable artifact reference, private storage path, checksum, availability, and source order. A row belongs to exactly one `vehicle` or one inseparable bulk `lot`. Marketplace reads sign every available ordered storage path; the list endpoint must not collapse the collection to its cover image.
