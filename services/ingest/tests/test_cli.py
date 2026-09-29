import pytest

import ingest.cli as cli
from ingest.cli import record_discovery_warnings, record_partial_item, supabase_backend_key
from ingest.models import DiscoveredItem, SyncResult


def test_backend_key_prefers_current_secret_key(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_current")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "legacy")

    assert supabase_backend_key() == "sb_secret_current"


def test_backend_key_falls_back_to_legacy_service_role(monkeypatch) -> None:
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "legacy")

    assert supabase_backend_key() == "legacy"


def test_safely_retained_central_summary_is_reported_as_partial_failure() -> None:
    result = SyncResult(source="moj_auction", discovered=1, fetched=1, parsed=1, changed=1, failed=0)
    item = DiscoveredItem(
        source_record_id="node-13564",
        official_url="https://auction.moj.gov.tw/umbraco/surface/Ini/CountAndRedirectUrl?nodeId=13564",
        discovery_url="https://auction.moj.gov.tw/1724/1726/searchList",
        title="普通重型機車拍賣公告",
        metadata={"ingest_partial_failure": "Central summary retained"},
    )

    record_partial_item(result, item)

    assert result.failed == 1
    assert result.warnings == ["node-13564: Central summary retained"]


def test_branch_discovery_warnings_are_preserved_without_fake_item_failures() -> None:
    result = SyncResult(source="moj_enforcement_cms", discovered=2, fetched=0, parsed=0, changed=0, failed=0)

    class Adapter:
        discovery_warnings = ["tcy: timed out", "ily: robots changed"]

    record_discovery_warnings(result, Adapter())  # type: ignore[arg-type]

    assert result.failed == 0
    assert result.warnings == ["tcy: timed out", "ily: robots changed"]


@pytest.mark.asyncio
async def test_public_publisher_start_failure_closes_clients_without_finishing_run(monkeypatch) -> None:
    events: list[str] = []

    class FakeAdapter:
        async def discover(self) -> None:
            events.append("discover")
            raise AssertionError("Discovery must not run after publisher preflight fails")

        async def close(self) -> None:
            events.append("adapter.close")

    class FakePublisher:
        async def start(self) -> None:
            events.append("publisher.start")
            raise RuntimeError("test-only source policy denied")

        async def finish(self, result: SyncResult) -> None:
            events.append("publisher.finish")

        async def close(self) -> None:
            events.append("publisher.close")

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-only-key")
    monkeypatch.setattr(cli, "adapter_for", lambda source: FakeAdapter())
    monkeypatch.setattr(cli, "SupabasePublicPublisher", lambda *args, **kwargs: FakePublisher())

    with pytest.raises(RuntimeError, match="source policy denied"):
        await cli.run_publish_public("moj_enforcement_cms", None)

    assert events == ["publisher.start", "adapter.close", "publisher.close"]
