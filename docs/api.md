# Authenticated API

All routes require a valid Supabase session belonging to `OWNER_EMAIL`. Unauthenticated requests return `401`. Ingestion does not use these routes; it connects with server-only database and service-role credentials.

## `GET /api/motorcycles`

Returns `{ items, nextCursor, total }`. `total` is the exact count before pagination. `nextCursor` is an opaque, versioned keyset cursor bound to the selected sort and should be passed back unchanged. Invalid or sort-mismatched cursors restart from the first page. The default page size is 24 and `limit` is clamped to 1–100.

| Query | Type | Meaning |
| --- | --- | --- |
| `cursor` | string | Cursor returned by the previous page |
| `limit` | integer | Page size |
| `keyword` | string | Normalized title, brand, model, plate, agency, and location search |
| `source` | string | Adapter key: `judicial`, `moj_auction`, `moj_enforcement`, `pcc`, or `shwoo` |
| `origin` | enum | Shared `DisposalOrigin` value |
| `county` | string | Taiwan county/city label |
| `brand` | string | Normalized brand |
| `eligibility` | enum | Shared `BidEligibility` value |
| `registration` | enum | Shared `RegistrationStatus` value |
| `vehicleClass` | enum | Official class: ordinary light/heavy, large heavy, electric, heavy-unspecified, or unknown |
| `cc` | repeatable enum | `le-50`, `51-125`, `126-250`, `251-550`, `gt-550`, or `unknown`; repeat the key for multi-select |
| `hasPhotos` | boolean | Require an available cached photo |
| `singleVehicle` | boolean | Exclude bulk lots |
| `excludeScrap` | boolean | Exclude scrap-only and non-relicensable records |
| `within` | integer | Auction occurs within N days |
| `minPrice` | integer | Inclusive minimum TWD price |
| `maxPrice` | integer | Inclusive maximum TWD price |
| `view` | enum | `active` (default), `ended`, `favorites`, `scrap`, or `all`; every non-scrap view excludes scrap/recycler records |
| `sort` | enum | `auction_asc` (default), `auction_desc`, `price_asc`, `price_desc`, or `completeness_desc` |

`within` is future-only: an unknown auction date never matches it. The ended view ignores `within` while preserving compatible filters. A passed deadline places a record in the ended view but never changes it to `SOLD` without an official result. CC ranges have non-overlapping inclusive boundaries, and do not infer the official `vehicleClass`.

## `GET /api/motorcycles/[id]`

Returns the normalized listing, observations used for price/snapshot history, and exact official field evidence. Returns `404` when the owner cannot access the record.

## `POST /api/favorites/[id]`

Creates the authenticated owner's favorite. The operation is idempotent.

## `DELETE /api/favorites/[id]`

Deletes only the authenticated owner's favorite. The operation is idempotent.

## `GET /api/sources`

Returns source implementation state, latest run metrics, and deterministic warnings for zero discovery, parse success below 90%, failed runs, and successful sync age over 36 hours.
