import pytest

import hashlib
from datetime import UTC, datetime

from ingest.models import (
    DiscoveredItem,
    EvidenceRef,
    FourState,
    ParsedAuctionRecord,
    ParsedVehicleUnit,
    RawArtifact,
    RegistrationStatus,
    VehicleIdentifier,
    VehicleType,
)
from ingest.official_documents import validated_official_document_url
from ingest.repository import (
    DatabaseRepository,
    evidence_artifact_id,
    retain_as_bulk_lot,
    validate_artifact_evidence,
    validate_vehicle_unit_cardinality,
    vehicle_facts_for_unit,
)
from ingest.source_policy import AccessDecision, SourceAccessBlocked


DETAIL_CHECKSUM = "1" * 64
INDEX_CHECKSUM = "2" * 64


def test_repository_maps_judicial_main_site_notices_to_the_seeded_source() -> None:
    repository = DatabaseRepository(
        "postgresql://unused",
        object(),  # type: ignore[arg-type]
        "judicial_notices",
    )

    assert repository.source_id == "20000000-0000-0000-0000-000000000009"


def evidence(checksum: str | None) -> EvidenceRef:
    return EvidenceRef(
        field_name="vehicle_scope",
        normalized_value="OFFICIAL_VEHICLE_BUCKET",
        source_text="種類：汽機車",
        artifact_checksum_sha256=checksum,
    )


def artifact(content: bytes, checksum: str) -> RawArtifact:
    return RawArtifact(
        official_url="https://www.tpkonsale.moj.gov.tw/Chattel",
        fetched_at=datetime.now(UTC),
        mime_type="text/html",
        content=content,
        checksum_sha256=checksum,
    )


def test_evidence_selects_detail_and_shared_index_artifacts_by_exact_checksum() -> None:
    artifacts = {
        DETAIL_CHECKSUM: "detail-artifact-id",
        INDEX_CHECKSUM: "shared-index-artifact-id",
    }

    assert evidence_artifact_id(
        evidence(DETAIL_CHECKSUM),
        primary_artifact_id="detail-artifact-id",
        artifacts_by_checksum=artifacts,
    ) == "detail-artifact-id"
    assert evidence_artifact_id(
        evidence(INDEX_CHECKSUM),
        primary_artifact_id="detail-artifact-id",
        artifacts_by_checksum=artifacts,
    ) == "shared-index-artifact-id"


def test_evidence_without_explicit_checksum_keeps_primary_artifact_compatibility() -> None:
    assert evidence_artifact_id(
        evidence(None),
        primary_artifact_id="detail-artifact-id",
        artifacts_by_checksum={DETAIL_CHECKSUM: "detail-artifact-id"},
    ) == "detail-artifact-id"


def test_evidence_rejects_unknown_artifact_checksum() -> None:
    with pytest.raises(ValueError, match="was not saved with this record"):
        evidence_artifact_id(
            evidence("3" * 64),
            primary_artifact_id="detail-artifact-id",
            artifacts_by_checksum={DETAIL_CHECKSUM: "detail-artifact-id"},
        )


def test_repository_preflight_rejects_unknown_evidence_before_persistence() -> None:
    detail_content = b"official detail"
    detail_checksum = hashlib.sha256(detail_content).hexdigest()

    with pytest.raises(ValueError, match="was not saved with this record"):
        validate_artifact_evidence(
            [artifact(detail_content, detail_checksum)],
            [evidence(INDEX_CHECKSUM)],
        )


def test_repository_preflight_rejects_a_forged_raw_artifact_checksum() -> None:
    with pytest.raises(ValueError, match="does not match its immutable content"):
        validate_artifact_evidence(
            [artifact(b"official detail", DETAIL_CHECKSUM)],
            [],
        )


def test_repository_preflight_requires_exact_evidence_artifact_when_multiple_exist() -> None:
    first = b"official detail"
    second = b"official index"
    with pytest.raises(ValueError, match="must name its artifact checksum"):
        validate_artifact_evidence(
            [
                artifact(first, hashlib.sha256(first).hexdigest()),
                artifact(second, hashlib.sha256(second).hexdigest()),
            ],
            [evidence(None)],
        )


def two_vehicle_record(*, identified_units: int = 2) -> ParsedAuctionRecord:
    units = [
        ParsedVehicleUnit(
            source_vehicle_key=f"plate:TEST{number}",
            identifiers=[VehicleIdentifier(
                identifier_type="PLATE",
                normalized_value=f"TEST{number}",
                original_value=f"TEST-{number}",
            )],
        )
        for number in range(1, identified_units + 1)
    ]
    return ParsedAuctionRecord(
        source_record_id="multi-vehicle-official-notice",
        official_url="https://web.pcc.gov.tw/notice/multi-vehicle-official-notice",
        official_title="普通重型機車 2 輛",
        organization="測試機關",
        title="普通重型機車 2 輛",
        lot_size=2,
        bulk_lot=True,
        vehicle_type=VehicleType.MOTORCYCLE,
        brand="SYM",
        model="未能對應車牌的車型",
        manufacture_year=2020,
        manufacture_month=3,
        displacement_cc=150,
        color="黑色",
        mileage_km=8000,
        has_key=FourState.YES,
        can_start=FourState.YES,
        registration_status=RegistrationStatus.NORMAL_TRANSFER,
        vehicle_units=units,
        photo_urls=["https://web.pcc.gov.tw/photos/shared-lot-image.jpg"],
        completeness=100,
        completeness_groups={
            "identity": 100, "auction": 100, "condition": 100,
            "registration": 100, "fees": 100, "media": 100,
        },
    )


def test_separate_vehicle_rows_keep_only_attributable_identifiers_and_facts() -> None:
    record = two_vehicle_record()
    projected = vehicle_facts_for_unit(record, record.vehicle_units[0])

    assert projected.vehicle_type == VehicleType.MOTORCYCLE
    assert projected.brand is None
    assert projected.model is None
    assert projected.manufacture_year is None
    assert projected.manufacture_month is None
    assert projected.displacement_cc is None
    assert projected.color is None
    assert projected.mileage_km is None
    assert projected.has_key == FourState.UNKNOWN
    assert projected.can_start == FourState.UNKNOWN
    assert projected.registration_status == RegistrationStatus.UNKNOWN
    assert projected.completeness == 40
    assert record.brand == "SYM"
    assert record.has_key == FourState.YES


def test_partly_identified_bulk_lot_remains_a_lot() -> None:
    assert retain_as_bulk_lot(two_vehicle_record(identified_units=1))
    assert not retain_as_bulk_lot(two_vehicle_record(identified_units=2))


def test_repository_rejects_vehicle_units_that_exceed_or_contradict_lot_count() -> None:
    too_many_units = two_vehicle_record()
    too_many_units.lot_size = 1
    with pytest.raises(ValueError, match="vehicle-unit count conflicts"):
        validate_vehicle_unit_cardinality(too_many_units)

    falsely_single = two_vehicle_record()
    falsely_single.bulk_lot = False
    with pytest.raises(ValueError, match="vehicle-unit count conflicts"):
        validate_vehicle_unit_cardinality(falsely_single)


@pytest.mark.asyncio
async def test_repository_assigns_shared_multi_vehicle_photo_and_evidence_to_lot() -> None:
    content = b"sanitized official multi-vehicle notice"
    checksum = hashlib.sha256(content).hexdigest()
    raw = artifact(content, checksum)
    record = two_vehicle_record()
    record.evidence = [EvidenceRef(
        field_name="model",
        normalized_value=record.model,
        source_text="官方公告的共同描述，未標明哪一面車牌",
        artifact_checksum_sha256=checksum,
    )]
    item = DiscoveredItem(
        source_record_id=record.source_record_id,
        official_url=record.official_url,
        title=record.official_title,
        discovery_url=record.official_url,
    )

    class RecordingConnection:
        def __init__(self) -> None:
            self.statements: list[tuple[str, tuple]] = []
            self.last_query = ""
            self.vehicle_count = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self):
            return self

        def execute(self, query: str, parameters: tuple = ()) -> None:
            self.last_query = " ".join(query.split()).lower()
            self.statements.append((self.last_query, parameters))

        def fetchall(self) -> list[dict]:
            return []

        def fetchone(self) -> dict:
            query = self.last_query
            if "insert into source_records" in query:
                return {"id": "source-record-id", "inserted": True}
            if "insert into vehicles" in query:
                self.vehicle_count += 1
                return {"id": f"vehicle-{self.vehicle_count}"}
            for table, identifier in (
                ("organizations", "organization-id"),
                ("raw_artifacts", "artifact-id"),
                ("snapshots", "snapshot-id"),
                ("auction_cases", "case-id"),
                ("auction_events", "event-id"),
                ("lots", "lot-id"),
            ):
                if f"insert into {table}" in query:
                    return {"id": identifier}
            raise AssertionError(f"Unexpected fetchone after {query}")

    class InMemoryStorage:
        async def put(self, _: RawArtifact) -> str:
            return "private/checksum.html"

    connection = RecordingConnection()
    repository = object.__new__(DatabaseRepository)
    repository.source = "pcc"
    repository.source_id = "source-id"
    repository.storage = InMemoryStorage()
    repository._connect = lambda: connection

    assert await repository.save("run-id", item, [raw], record)
    assert connection.vehicle_count == 2
    photo = next(parameters for query, parameters in connection.statements if "insert into photos" in query)
    assert photo[:3] == (None, "lot-id", "source-record-id")
    evidence_row = next(parameters for query, parameters in connection.statements if "insert into field_evidence" in query)
    assert evidence_row[:2] == ("lot", "lot-id")
    vehicle_rows = [parameters for query, parameters in connection.statements if "insert into vehicles" in query]
    assert all(parameters[4:7] == (None, None, None) for parameters in vehicle_rows)


class FakePolicyCursor:
    def __init__(self, row: dict[str, str] | None) -> None:
        self.row = row
        self.executed: list[tuple[str, tuple[str]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query: str, parameters: tuple[str]) -> None:
        self.executed.append((query, parameters))

    def fetchone(self) -> dict[str, str] | None:
        return self.row


class FakePolicyConnection:
    def __init__(self, cursor: FakePolicyCursor) -> None:
        self.policy_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self) -> FakePolicyCursor:
        return self.policy_cursor


def repository_with_policy(row: dict[str, str] | None) -> tuple[DatabaseRepository, FakePolicyCursor]:
    repository = object.__new__(DatabaseRepository)
    repository.source = "pcc"
    repository.source_id = "source-id"
    cursor = FakePolicyCursor(row)
    repository._connect = lambda: FakePolicyConnection(cursor)  # type: ignore[method-assign]
    return repository, cursor


def test_repository_requires_persisted_allow_policy_before_automated_discovery() -> None:
    repository, cursor = repository_with_policy({"decision": "ALLOW"})

    assert repository.require_access({AccessDecision.ALLOW}) == AccessDecision.ALLOW
    assert cursor.executed[0][1] == ("source-id",)


@pytest.mark.parametrize("row", [None, {"decision": "MANUAL_ONLY"}, {"decision": "DISABLED"}])
def test_repository_fails_closed_when_automated_policy_is_missing_or_not_allow(
    row: dict[str, str] | None,
) -> None:
    repository, _ = repository_with_policy(row)

    with pytest.raises(SourceAccessBlocked, match="discovery was blocked|requires ALLOW"):
        repository.require_access({AccessDecision.ALLOW})


def test_repository_manual_import_requires_persisted_manual_only_policy() -> None:
    repository, _ = repository_with_policy({"decision": "MANUAL_ONLY"})

    assert repository.require_access({AccessDecision.MANUAL_ONLY}) == AccessDecision.MANUAL_ONLY

    repository, _ = repository_with_policy({"decision": "REVIEW_REQUIRED"})
    with pytest.raises(SourceAccessBlocked, match="requires MANUAL_ONLY"):
        repository.require_access({AccessDecision.MANUAL_ONLY})


@pytest.mark.asyncio
async def test_retention_uses_every_evidence_reference_to_a_shared_artifact() -> None:
    class CaptureCursor:
        def __init__(self) -> None:
            self.query = ""

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query: str, parameters: tuple[str]) -> None:
            self.query = query
            assert parameters == ("source-id",)

        def fetchall(self) -> list[dict]:
            return []

    class CaptureConnection:
        def __init__(self, cursor: CaptureCursor) -> None:
            self.capture_cursor = cursor

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self) -> CaptureCursor:
            return self.capture_cursor

    cursor = CaptureCursor()
    repository = object.__new__(DatabaseRepository)
    repository.source_id = "source-id"
    repository._connect = lambda: CaptureConnection(cursor)  # type: ignore[method-assign]

    assert await repository.purge_expired_artifacts() == []
    assert "from source_record_artifacts" in cursor.query
    assert "from snapshots" in cursor.query
    assert "from documents" in cursor.query
    assert "from photos" in cursor.query
    assert "from field_evidence" in cursor.query
    assert "from auction_events" in cursor.query
    assert "max(" in cursor.query
    assert "reference.referenced_at" in cursor.query


@pytest.mark.parametrize(
    ("source", "url"),
    [
        (
            "judicial",
            "https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02/DO_VIEWPDF.htm?filenm=notice.pdf",
        ),
        (
            "judicial_notices",
            "https://www.judicial.gov.tw/tw/dl-12345-01234567-89ab-cdef-0123-456789abcdef.html",
        ),
        (
            "moj_enforcement",
            "https://www.tpkonsale.moj.gov.tw/File/Download?"
            "PATH=11111111-1111-4111-8111-111111111111&NAME=notice.pdf",
        ),
        ("customs", "https://web.customs.gov.tw/download/auction-notice.pdf"),
        (
            "moj_enforcement_cms",
            "https://www.tcy.moj.gov.tw/media/12345/auction.pdf?mediaDL=true",
        ),
        ("moj_auction", "https://auction.moj.gov.tw/media/auction-notice.pdf"),
    ],
)
def test_link_only_document_validator_accepts_exact_official_shapes(
    source: str,
    url: str,
) -> None:
    assert validated_official_document_url(source, url) == url


@pytest.mark.parametrize(
    ("source", "url"),
    [
        ("customs", "http://web.customs.gov.tw/download/notice.pdf"),
        ("customs", "https://person@example.com@web.customs.gov.tw/download/notice.pdf"),
        ("customs", "https://web.customs.gov.tw:444/download/notice.pdf"),
        ("customs", "https://www.tcy.moj.gov.tw/download/notice.pdf"),
        ("judicial", "https://aomp109.judicial.gov.tw/robots.txt?filenm=notice.pdf"),
        (
            "judicial_notices",
            "https://www.judicial.gov.tw/tw/cp-1913-12345-abcdef.html",
        ),
        (
            "judicial_notices",
            "https://www.judicial.gov.tw/tw/dl-12345-abcdef.html?download=1",
        ),
        (
            "judicial_notices",
            "https://aomp109.judicial.gov.tw/tw/dl-12345-abcdef.html",
        ),
        (
            "moj_enforcement",
            "https://www.tpkonsale.moj.gov.tw/File/Download?PATH=not-a-uuid&NAME=notice.pdf",
        ),
        (
            "moj_enforcement",
            "https://www.tpkonsale.moj.gov.tw/File/Download?"
            "PATH=11111111111141118111111111111111&NAME=notice.pdf",
        ),
        ("moj_enforcement_cms", "https://www.tcy.moj.gov.tw/news/12345"),
        ("moj_enforcement_cms", "https://www.tcy.moj.gov.tw/news/12345?next=notice.pdf"),
        ("moj_enforcement_cms", "https://www.tcy.moj.gov.tw/media/notice.pdf#page=1"),
        ("pcc", "https://web.customs.gov.tw/download/notice.pdf"),
    ],
)
def test_link_only_document_validator_rejects_unsafe_or_cross_source_urls(
    source: str,
    url: str,
) -> None:
    assert validated_official_document_url(source, url) is None
