import pytest
from pydantic import ValidationError

from ingest.models import EvidenceRef, ExtractionMethod, RawArtifact, SourceTrust


def test_evidence_enums_match_the_database_contract_and_serialize_as_strings() -> None:
    evidence = EvidenceRef(
        field_name="vehicle_type",
        normalized_value="MOTORCYCLE",
        source_text="種類：機車",
        extraction_method="HTML",
        trust="OFFICIAL_EXPLICIT",
    )

    assert evidence.extraction_method is ExtractionMethod.HTML
    assert evidence.trust is SourceTrust.OFFICIAL_EXPLICIT
    assert evidence.model_dump(mode="json")["extraction_method"] == "HTML"
    assert evidence.model_dump(mode="json")["trust"] == "OFFICIAL_EXPLICIT"


@pytest.mark.parametrize(
    ("field", "value"),
    [("extraction_method", "HTML_LINK"), ("trust", "UNREVIEWED")],
)
def test_evidence_rejects_values_that_postgres_cannot_store(field: str, value: str) -> None:
    values = {
        "field_name": "official_attachment_url",
        "normalized_value": "https://example.invalid/file.pdf",
        "source_text": "fixture",
        field: value,
    }

    with pytest.raises(ValidationError):
        EvidenceRef(**values)


def test_evidence_artifact_reference_requires_a_lowercase_sha256_checksum() -> None:
    with pytest.raises(ValidationError):
        EvidenceRef(
            field_name="vehicle_scope",
            normalized_value="OFFICIAL_VEHICLE_BUCKET",
            source_text="種類：汽機車",
            artifact_checksum_sha256="not-a-checksum",
        )


def test_raw_artifact_requires_a_lowercase_sha256_checksum() -> None:
    with pytest.raises(ValidationError):
        RawArtifact(
            official_url="https://example.invalid/notice",
            fetched_at="2026-08-23T00:00:00Z",
            mime_type="text/html",
            content=b"official bytes",
            checksum_sha256="not-a-checksum",
        )
