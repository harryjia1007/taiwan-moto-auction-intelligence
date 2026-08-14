# Product Specification

## Outcome

A private, one-person dashboard answers what a motorcycle is, why it is sold, who is selling it, when and where the auction occurs, price and eligibility, road-use risk, condition facts, fees, supporting evidence, and auction history within roughly 30 seconds.

## Principles

1. Prefer official sources and cite the precise artifact behind important facts.
2. Preserve raw input before normalization and retain historical snapshots.
3. Leave missing data missing. Negative, unknown, conflicting, and untestable are different states.
4. Separate facts from interpretations and system calculations.
5. Favor conservative identity resolution over record count.

## Current private production slice and public Demo

Taipei Shwoo has the complete photo-preserving vertical slice and the MOJ centralized portal has an authorized private adapter. Judicial live discovery is `DISABLED` by current robots policy and Government e-Procurement is `REVIEW_REQUIRED`; neither may run unattended. Administrative Enforcement detail, attachment, and photo ingestion is `MANUAL_ONLY` because official discovery requires CAPTCHA. Direct police/traffic pages and Customs remain `PLANNED`; paid vehicle-registry data is a separate manual enrichment workflow rather than an auction source.

`/demo` is an independent public portfolio surface. It contains only synthetic cases and project-owned illustrative visuals, has no Supabase or official-source dependency, and never exposes official attachment deep links. `/motorcycles`, `/sources`, their APIs, favorites, evidence and signed media remain owner-only.

The owner selected a private-only product scope. Ordinary light, ordinary heavy, large heavy, and electric motorcycles are included. Official wording that says only “heavy motorcycle” remains `HEAVY_UNSPECIFIED`; displacement alone is never used to invent a class. Scrap-only and licensed-recycler records remain preserved but are excluded from every normal marketplace view and appear only in the dedicated scrap/recycler area.

The application is read-only with respect to auction sources: it never logs in, bids, or circumvents restrictions. Favorites are the only user mutation.
