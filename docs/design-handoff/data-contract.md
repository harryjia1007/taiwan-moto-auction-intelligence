# Design-facing data contract

## Core listing

| Field | UI meaning | Rules |
| --- | --- | --- |
| `id` | Internal listing identity | Never display as a vehicle fact. |
| `sourceName` / `sourceAuid` | Official source and source identity | Always retain source attribution. |
| `officialUrl` | Exact official notice or vehicle-specific court document | External primary action; never substitute a generic property-auction homepage. |
| `name`, `brand`, `model` | Normalized vehicle name | Missing brand/model remains explicit. |
| `auctionStatus` | Official lifecycle | A passed time archives the listing but does not create `SOLD`. |
| `auctionAt`, `auctionDatePrecision` | Auction deadline/date | Do not invent a time when precision is `DATE`. |
| `reservePrice`, `currentPrice`, `soldPrice` | Distinct price facts | Label the selected price type; never collapse history destructively. |
| `bidEligibility` | Who may bid | P0 decision fact. |
| `registrationStatus` | Transfer/re-registration/road-use state | P0 decision fact; winning is not proof of road legality. |
| `hasKey`, `canStart`, `canTest` | Independent four-state facts | “Cannot test” does not mean “cannot start”. |
| `bulkLot`, `lotSize` | Single vehicle or inseparable lot | Never invent vehicle rows for an opaque bulk lot. |
| `completeness` | Deterministic field coverage | Not confidence and not quality. |
| `evidence[]` | Exact official text supporting fields | Show field label, official excerpt, trust and source link. |
| `history[]` | Immutable observations | A later snapshot appends; it does not overwrite earlier prices. |

## Four-state facts

- `YES`: official evidence supports yes/can/has.
- `NO`: official evidence supports no/cannot/does not have.
- `UNKNOWN`: no authoritative answer is available.
- `CONFLICTING`: retained official observations disagree.

The design must visually distinguish all four. `UNKNOWN` cannot be rendered as an empty value or a negative fact.

## Registration states

- `NORMAL_TRANSFER`: normal transfer is explicitly supported.
- `RE_REGISTRATION_REQUIRED`: plate was cancelled/surrendered and a new registration is required.
- `INSPECTION_REQUIRED`: inspection or certification is explicitly required.
- `SCRAP_ONLY`: disposal is for scrap only.
- `CANNOT_RELICENSE`: official text says it cannot be relicensed.
- `REGISTRABILITY_UNKNOWN` / `UNKNOWN`: road-use outcome is not confirmed.

## Evidence and confidence

Completeness answers “how many expected fields are present.” Confidence answers “how strongly does evidence support this normalized value.” They must never be combined into one score. Exact official text remains visible even when a lower-authority observation conflicts.
