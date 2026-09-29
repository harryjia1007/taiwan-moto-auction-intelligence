# Product Specification

## Outcome

A private, one-person dashboard answers what a motorcycle is, why it is sold, who is selling it, when and where the auction occurs, price and eligibility, road-use risk, condition facts, fees, supporting evidence, and auction history within roughly 30 seconds.

## Principles

1. Prefer official sources and cite the precise artifact behind important facts.
2. Preserve raw input before normalization and retain historical snapshots.
3. Leave missing data missing. Negative, unknown, conflicting, and untestable are different states.
4. Separate facts from interpretations and system calculations.
5. Favor conservative identity resolution over record count.

## Current full-fidelity product and two public surfaces

Taipei Shwoo has the photo-preserving vertical slice, the MOJ centralized portal has a host-scoped adapter, and Government e-Procurement uses official dataset 7263 XML with exact same-host detail matching. Administrative Enforcement now has a separate, fail-closed adapter for the 13 public branch CMS sites; its CAPTCHA-gated central search remains `MANUAL_ONLY`. Customs covers the four official HTML announcement channels and links restricted attachments without downloading them. The central aomp109 Judicial source remains `MANUAL_ONLY` with zero adapter network requests, while a separate `judicial_notices` adapter performs a bounded robots-first search of the Judicial Yuan main site's other-notices section. The supplemental source does not imply nationwide 22-court coverage. Paid vehicle-registry data is a separate owner-authorized enrichment workflow rather than an auction source.

The repository `/demo` is an independent synthetic portfolio surface. It contains only invented cases and project-owned illustrative visuals, has no Supabase or official-source dependency, and never exposes official attachment deep links. It must not be described as a live auction feed.

The harryjia.com marketplace is a different public surface: it may read only active, sanitized rows from `public_live_motorcycle_listings` and aggregate rows from `public_source_health`. It can show minimized real official facts and validated official outbound links, but never full identifiers, people, private addresses, source photos, cached artifacts, evidence text, owner favorites, or operational metadata. A deployed UI does not prove that its backend release or scheduled sources are operational.

`/motorcycles`, `/sources`, their APIs, server-side favorites, evidence and signed media remain owner-only.

The full-fidelity product scope remains owner-only. Ordinary light, ordinary heavy, large heavy, and electric motorcycles are included. Official wording that says only “heavy motorcycle” remains `HEAVY_UNSPECIFIED`; displacement alone is never used to invent a class. Scrap-only and licensed-recycler records remain preserved but are excluded from every normal marketplace view and appear only in the dedicated scrap/recycler area.

The application is read-only with respect to auction sources: it never logs in, bids, or circumvents restrictions. Favorites are the only server-side user mutation. The private two-to-three vehicle comparison list is browser-local state, is not synchronized to Supabase, and is never sent to an external service.
