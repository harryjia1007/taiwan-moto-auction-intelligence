# Deduplication

Auto-linking uses, in order: exact frame/VIN, exact engine number, exact plate, exact official case plus lot, or an explicit official cross-link. A weighted combination of brand, model, year, location, and date can create a probable-duplicate candidate but cannot merge records.

Every relationship retains both source records, matching signals, score, algorithm version, and review state. The Shwoo AUID is the source-record identity; a repeated motorcycle may still receive a new AUID and is linked only when strong identifiers match.
