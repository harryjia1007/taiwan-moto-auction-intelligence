# Claude Design Handoff

This directory is a self-contained design brief for redesigning the authenticated Taiwan motorcycle-auction intelligence dashboard. It is intentionally separate from raw artifacts and secrets.

## Give these files to Claude Design

1. `claude-design-prompt.md` — paste this first as the primary instruction.
2. `sample-marketplace-data.json` — sanitized, representative UI states.
3. `data-contract.md` — field meanings and non-negotiable auction semantics.
4. `design-tokens.json` — the current premium editorial/utility direction.
5. `acceptance-checklist.md` — responsive and product acceptance criteria.
6. `implementation-map.md` — routes, APIs and safe component boundaries.

Ask for desktop list, mobile list, desktop detail, mobile detail, and source-health screens in that order. The generated design may change layout and presentation, but must not rename enum values, infer missing facts, or turn a passed deadline into a sale.

The live implementation remains Next.js and uses URL-backed filters. Treat generated code as a design proposal until it passes the repository tests and accessibility review.
