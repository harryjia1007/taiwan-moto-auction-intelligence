# Evidence Specification

Every consequential field may have multiple evidence rows containing the entity and field, normalized value, source record, artifact, exact source text, page/table location, parser and version, extraction method, trust level, confidence, and timestamp.

Authority order is `OFFICIAL_EXPLICIT`, `CROSS_SOURCE_CONFIRMED`, `OFFICIAL_INFERRED`, `SYSTEM_CALCULATED`, `LLM_EXTRACTED`, `THIRD_PARTY_REFERENCE`, then `UNKNOWN`. Lower-authority evidence is retained when a winner is selected. Conflicting explicit official values remain visible and set the normalized fact to `CONFLICTING` where applicable.
