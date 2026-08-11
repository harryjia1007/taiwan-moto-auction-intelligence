# Product Specification

## Outcome

A private, one-person dashboard answers what a motorcycle is, why it is sold, who is selling it, when and where the auction occurs, price and eligibility, road-use risk, condition facts, fees, supporting evidence, and auction history within roughly 30 seconds.

## Principles

1. Prefer official sources and cite the precise artifact behind important facts.
2. Preserve raw input before normalization and retain historical snapshots.
3. Leave missing data missing. Negative, unknown, conflicting, and untestable are different states.
4. Separate facts from interpretations and system calculations.
5. Favor conservative identity resolution over record count.

## Current production slice

Taipei Shwoo has the complete photo-preserving vertical slice. Judicial Yuan central movable-property discovery across 22 district courts and nationwide Government e-Procurement asset-sale discovery are implemented as `PARTIAL` until their first successful database-backed live sync. Enforcement, prosecutors, direct police/traffic pages, Customs, and paid vehicle-registry enrichment remain explicitly `PLANNED`.

The application is read-only with respect to auction sources: it never logs in, bids, or circumvents restrictions. Favorites are the only user mutation.
