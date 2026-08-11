# Engineering Guide

- Read the relevant `/docs` pages before changing architecture or domain behavior.
- Update documentation whenever behavior, data contracts, or source coverage changes.
- Official sources are the source of truth; preserve raw artifacts and exact evidence.
- Never invent missing auction data. `UNKNOWN` is not `NO`.
- Never bypass CAPTCHA, authentication, anti-bot controls, or access restrictions.
- Never scrape during a frontend request; collection is asynchronous.
- Preserve every auction round and snapshot; a missing page is not evidence of a sale.
- Keep adapters independent and failure-isolated.
- Write parser tests against sanitized fixtures.
- Never silently merge uncertain vehicle identities.
- Run relevant tests before declaring a milestone complete.
