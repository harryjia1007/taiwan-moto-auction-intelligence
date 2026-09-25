import hashlib
from datetime import UTC, datetime

import pytest

from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SyncResult
from ingest.public_publisher import SupabasePublicPublisher
from ingest.source_policy import SourceAccessBlocked


def publisher_without_network() -> SupabasePublicPublisher:
    publisher = object.__new__(SupabasePublicPublisher)
    publisher.source_adapter = "pcc"
    publisher.source_id = None
    publisher.run_id = None
    publisher.headers = {"Authorization": "Bearer test"}
    return publisher


@pytest.mark.asyncio
async def test_start_requires_hosted_allow_policy_before_creating_run() -> None:
    publisher = publisher_without_network()
    calls: list[tuple[str, str, dict]] = []

    async def fake_json(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))
        if path.startswith("/rest/v1/sources?"):
            return [{"id": "source-id"}]
        if path.startswith("/rest/v1/source_access_policies?"):
            return [{"decision": "ALLOW"}]
        if path == "/rest/v1/sync_runs":
            return [{"id": "run-id"}]
        raise AssertionError(f"unexpected publisher request: {method} {path}")

    publisher._json = fake_json

    assert await publisher.start() == "run-id"
    assert publisher.source_id == "source-id"
    assert [path.split("?", 1)[0] for _, path, _ in calls] == [
        "/rest/v1/sources",
        "/rest/v1/source_access_policies",
        "/rest/v1/sync_runs",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["MANUAL_ONLY", "REVIEW_REQUIRED", "DISABLED", ""])
async def test_start_blocks_non_allow_hosted_policy_without_creating_run(decision: str) -> None:
    publisher = publisher_without_network()
    calls: list[tuple[str, str]] = []

    async def fake_json(method: str, path: str, **kwargs):
        calls.append((method, path))
        if path.startswith("/rest/v1/sources?"):
            return [{"id": "source-id"}]
        if path.startswith("/rest/v1/source_access_policies?"):
            return [{"decision": decision}]
        raise AssertionError("a blocked policy must not create a sync run")

    publisher._json = fake_json

    with pytest.raises(SourceAccessBlocked, match="not ALLOW"):
        await publisher.start()

    assert publisher.source_id is None
    assert publisher.run_id is None
    assert not any(path == "/rest/v1/sync_runs" for _, path in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("policies", [[], [{"decision": "ALLOW"}, {"decision": "ALLOW"}]])
async def test_start_blocks_missing_or_ambiguous_hosted_policy(policies: list[dict[str, str]]) -> None:
    publisher = publisher_without_network()

    async def fake_json(method: str, path: str, **kwargs):
        if path.startswith("/rest/v1/sources?"):
            return [{"id": "source-id"}]
        if path.startswith("/rest/v1/source_access_policies?"):
            return policies
        raise AssertionError("a missing or ambiguous policy must not create a sync run")

    publisher._json = fake_json

    with pytest.raises(SourceAccessBlocked, match="no unique policy"):
        await publisher.start()

    assert publisher.source_id is None
    assert publisher.run_id is None


@pytest.mark.asyncio
async def test_start_blocks_duplicate_adapter_sources_before_policy_or_run() -> None:
    publisher = publisher_without_network()
    calls: list[str] = []

    async def fake_json(method: str, path: str, **kwargs):
        calls.append(path)
        if path.startswith("/rest/v1/sources?"):
            return [{"id": "source-one"}, {"id": "source-two"}]
        raise AssertionError("ambiguous source identity must stop before policy/run access")

    publisher._json = fake_json

    with pytest.raises(RuntimeError, match="exactly one pcc source"):
        await publisher.start()

    assert len(calls) == 1
    assert "limit=2" in calls[0]


@pytest.mark.asyncio
async def test_hosted_publish_upserts_cached_official_document_and_public_link() -> None:
    publisher = object.__new__(SupabasePublicPublisher)
    publisher.source_adapter = "moj_auction"
    publisher.source_name = "法務部查扣物集中拍賣"
    publisher.source_id = "source-id"
    publisher.run_id = "run-id"
    publisher.headers = {"Authorization": "Bearer test"}

    class FakeStorage:
        async def put(self, artifact: RawArtifact) -> str:
            return f"moj/{artifact.checksum_sha256}"

    publisher.storage = FakeStorage()
    document_url = "https://auction.moj.gov.tw/media/auction-notice.pdf"
    content = b"%PDF fixture"
    artifact = RawArtifact(
        official_url=document_url,
        fetched_at=datetime.now(UTC),
        mime_type="application/pdf",
        filename="auction-notice.pdf",
        content=content,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )
    item = DiscoveredItem(
        source_record_id="notice-1",
        official_url="https://auction.moj.gov.tw/1724/1726/notice-1/post",
        title="普通重型機車拍賣公告",
        discovery_url="https://auction.moj.gov.tw/1724/1726/searchList",
    )
    record = ParsedAuctionRecord(
        source_record_id=item.source_record_id,
        official_url=item.official_url,
        official_title=item.title,
        organization="臺灣測試地方檢察署",
        title=item.title,
    )
    calls: list[tuple[str, str, dict]] = []

    async def fake_json(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))
        if path.startswith("/rest/v1/source_records?"):
            return [{"id": "source-record-id"}]
        if path.startswith("/rest/v1/raw_artifacts?"):
            return [{"id": "artifact-id"}]
        if path.startswith("/rest/v1/snapshots?"):
            return [{"id": "snapshot-id"}]
        return None

    publisher._json = fake_json

    assert await publisher.publish(item, [artifact], record) is True
    document_call = next(call for call in calls if call[1].startswith("/rest/v1/documents?"))
    assert document_call[2]["json"]["artifact_id"] == "artifact-id"
    assert document_call[2]["json"]["official_url"] == document_url
    assert "resolution=merge-duplicates" in document_call[2]["headers"]["Prefer"]
    public_call = next(
        call for call in calls if call[1].startswith("/rest/v1/public_live_motorcycle_listings?")
    )
    assert public_call[2]["json"]["documents"] == [
        {"label": "官方完整全文", "url": document_url}
    ]


@pytest.mark.asyncio
async def test_hosted_publish_does_not_report_an_idempotent_snapshot_as_changed() -> None:
    publisher = object.__new__(SupabasePublicPublisher)
    publisher.source_adapter = "pcc"
    publisher.source_name = "政府電子採購網財物變賣"
    publisher.source_id = "source-id"
    publisher.run_id = "run-id"
    publisher.headers = {"Authorization": "Bearer test"}

    class FakeStorage:
        async def put(self, artifact: RawArtifact) -> str:
            return f"pcc/{artifact.checksum_sha256}"

    publisher.storage = FakeStorage()
    content = b"official fixture"
    artifact = RawArtifact(
        official_url="https://web.pcc.gov.tw/notice-1",
        fetched_at=datetime.now(UTC),
        mime_type="text/html",
        content=content,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )
    item = DiscoveredItem(
        source_record_id="notice-1",
        official_url=artifact.official_url,
        title="機車變賣公告",
        discovery_url="https://web.pcc.gov.tw/",
    )
    record = ParsedAuctionRecord(
        source_record_id=item.source_record_id,
        official_url=item.official_url,
        official_title=item.title,
        organization="測試機關",
        title=item.title,
    )

    async def fake_json(method: str, path: str, **kwargs):
        if path.startswith("/rest/v1/source_records?"):
            return [{"id": "source-record-id"}]
        if path.startswith("/rest/v1/raw_artifacts?"):
            return [{"id": "artifact-id"}]
        if path.startswith("/rest/v1/snapshots?"):
            assert "return=representation" in kwargs["headers"]["Prefer"]
            return []
        return None

    publisher._json = fake_json

    assert await publisher.publish(item, [artifact], record) is False


@pytest.mark.asyncio
async def test_hosted_publish_rejects_forged_artifact_before_any_write() -> None:
    publisher = object.__new__(SupabasePublicPublisher)
    publisher.source_adapter = "pcc"
    publisher.source_name = "政府電子採購網財物變賣"
    publisher.source_id = "source-id"
    publisher.run_id = "run-id"
    publisher.headers = {"Authorization": "Bearer test"}
    writes: list[str] = []

    class FakeStorage:
        async def put(self, artifact: RawArtifact) -> str:
            writes.append("storage")
            return "unexpected"

    async def fake_json(method: str, path: str, **kwargs):
        writes.append(path)
        raise AssertionError("forged bytes must be rejected before REST access")

    publisher.storage = FakeStorage()
    publisher._json = fake_json
    item = DiscoveredItem(
        source_record_id="notice-forged",
        official_url="https://web.pcc.gov.tw/notice-forged",
        title="汽車標售公告",
        discovery_url="https://web.pcc.gov.tw/",
    )
    record = ParsedAuctionRecord(
        source_record_id=item.source_record_id,
        official_url=item.official_url,
        official_title=item.title,
        organization="測試機關",
        title=item.title,
    )
    artifact = RawArtifact.model_construct(
        official_url=item.official_url,
        fetched_at=datetime.now(UTC),
        mime_type="text/html",
        filename=None,
        content=b"actual official bytes",
        http_status=200,
        http_headers={},
        checksum_sha256="0" * 64,
    )

    with pytest.raises(ValueError, match="checksum does not match"):
        await publisher.publish(item, [artifact], record)

    assert writes == []


@pytest.mark.asyncio
async def test_finish_cannot_promote_source_after_policy_changes_to_disabled() -> None:
    publisher = publisher_without_network()
    publisher.source_id = "source-id"
    publisher.run_id = "run-id"
    calls: list[tuple[str, str, dict]] = []

    async def no_plate_cleanup(now: datetime) -> None:
        assert now.tzinfo is not None

    async def fake_json(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))
        if path.startswith("/rest/v1/source_access_policies?"):
            return [{"decision": "DISABLED"}]
        return None

    publisher._enforce_public_plate_retention = no_plate_cleanup
    publisher._json = fake_json
    result = SyncResult(
        source="pcc",
        discovered=1,
        fetched=1,
        parsed=1,
        changed=1,
        failed=0,
    )

    await publisher.finish(result)

    run_call = next(call for call in calls if call[1] == "/rest/v1/sync_runs?id=eq.run-id")
    source_call = next(call for call in calls if call[1] == "/rest/v1/sources?id=eq.source-id")
    deactivation_call = next(
        call for call in calls
        if call[1].startswith("/rest/v1/public_live_motorcycle_listings?source_adapter=eq.pcc")
    )
    assert run_call[2]["json"]["status"] == "PARTIAL"
    assert deactivation_call[2]["json"] == {"active": False}
    assert calls.index(deactivation_call) < calls.index(source_call)
    assert source_call[2]["json"]["status"] == "DISABLED"
    assert "last_successful_at" not in source_call[2]["json"]


def test_public_health_payload_exposes_only_derived_warning_codes() -> None:
    publisher = publisher_without_network()
    publisher.source_adapter = "customs"
    publisher.source_name = "財政部關務署四關標售公告"
    completed_at = datetime.now(UTC)
    result = SyncResult(
        source="customs",
        discovered=4,
        fetched=4,
        parsed=3,
        changed=2,
        failed=1,
        warnings=["private upstream URL and parser details must not be published"],
    )

    payload = publisher._public_health_payload(
        result,
        completed_at=completed_at,
        status="PARTIAL",
        access_decision=None,
    )

    assert payload["status"] == "DEGRADED"
    assert payload["parse_success_rate"] == 75.0
    assert payload["stale_after_hours"] == 72
    assert payload["warning_codes"] == [
        "PARSE_BELOW_90",
        "POLICY_BLOCKED",
        "PARTIAL_COVERAGE",
    ]
    assert "warnings" not in payload
    assert "last_successful_at" not in payload
