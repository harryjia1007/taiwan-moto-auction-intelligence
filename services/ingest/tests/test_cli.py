import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

import ingest.cli as cli_module
from ingest.adapters.base import SourceAccessDenied, SourceRateLimited
from ingest.cli import (
    app,
    emit_safe_discovery_diagnostics,
    load_enforcement_manifest,
    load_moj_enforcement_reprocessable,
    record_discovery_warnings,
    record_partial_item,
    run_healthcheck,
    run_publish_public,
    run_reprocess,
    run_sync,
    supabase_backend_key,
)
from ingest.data_gov_catalog import CatalogCandidate, CatalogWatchResult, DataGovCatalogNetworkError
from ingest.models import DiscoveredItem, SyncResult
from ingest.source_policy import SourceAccessBlocked

FIXTURES = Path(__file__).parent / "fixtures"
RUNNER = CliRunner()


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

    Adapter.discovery_warnings.append("late attachment warning")
    record_discovery_warnings(result, Adapter())  # type: ignore[arg-type]

    assert result.warnings == ["tcy: timed out", "ily: robots changed", "late attachment warning"]


def test_discovery_failure_logs_branch_reason_without_official_url_query_or_log_injection(capsys) -> None:
    emit_safe_discovery_diagnostics(
        "moj_enforcement_cms",
        ["tpy: robots redirect blocked https://www.tpy.moj.gov.tw/robots?token=private\n::warning::injected"],
    )

    logged = capsys.readouterr().err
    assert "tpy: robots redirect blocked" in logged
    assert "token=private" not in logged
    assert logged.count("\n") == 1
    assert not logged.startswith("::warning")


def test_enforcement_manifest_accepts_offline_official_html_export() -> None:
    items = load_enforcement_manifest(FIXTURES / "moj_enforcement_exported_index.html")

    assert len(items) == 1
    assert items[0].source_record_id == "11111111-1111-4111-8111-111111111111"
    assert items[0].metadata["index_provenance"] == "MANUAL_OFFICIAL_HTML_EXPORT"
    assert any("additional result pages" in warning for warning in items[0].metadata["manifest_warnings"])


def test_enforcement_manifest_accepts_directory_of_exported_pages(tmp_path: Path) -> None:
    export_directory = tmp_path / "moj-enforcement-export"
    export_directory.mkdir()
    (export_directory / "page-1.html").write_bytes(
        (FIXTURES / "moj_enforcement_exported_index.html").read_bytes()
    )

    items = load_enforcement_manifest(export_directory)

    assert [item.source_record_id for item in items] == ["11111111-1111-4111-8111-111111111111"]


def test_json_enforcement_manifest_does_not_promote_unevidenced_metadata(tmp_path: Path) -> None:
    manifest = tmp_path / "manual.json"
    manifest.write_text(
        """[{
          "official_url": "https://www.tpkonsale.moj.gov.tw/Detail/Chattel?NO=11111111-1111-4111-8111-111111111111",
          "title": "人工輸入品牌與車牌",
          "organization": "人工輸入分署",
          "auction_round": 99
        }]""",
        encoding="utf-8",
    )

    loaded = load_enforcement_manifest(manifest)

    assert loaded[0].metadata == {
        "manifest_provenance": "HUMAN_VALIDATED_DETAIL_URL_ONLY",
    }


def test_catalog_watch_candidate_warns_but_does_not_fail(monkeypatch) -> None:
    async def fake_watch(*, published_after: date) -> CatalogWatchResult:
        assert published_after <= date.today()
        return CatalogWatchResult(
            checked_at=datetime(2026, 8, 21, tzinfo=UTC),
            published_after=date(2026, 8, 7),
            scanned_entries=53_094,
            recent_entries=91,
            undated_matching_entries=0,
            document_sha256="a" * 64,
            candidates=(CatalogCandidate(900001, date(2026, 8, 20), "JUDICIAL"),),
        )

    monkeypatch.setattr(cli_module, "watch_official_catalog", fake_watch)
    result = RUNNER.invoke(app, ["watch-data-catalog", "--lookback-days", "14"], env={"GITHUB_ACTIONS": "true"})

    assert result.exit_code == 0
    assert '"candidate_count": 1' in result.output
    assert "::warning title=data.gov.tw 官方資料集候選::" in result.output
    assert "https://data.gov.tw/dataset/900001" in result.output


def test_catalog_watch_network_failure_fails_closed(monkeypatch) -> None:
    async def fake_watch(*, published_after: date) -> CatalogWatchResult:
        raise DataGovCatalogNetworkError("catalog unavailable")

    monkeypatch.setattr(cli_module, "watch_official_catalog", fake_watch)
    result = RUNNER.invoke(app, ["watch-data-catalog"])

    assert result.exit_code == 1
    assert '"status": "error"' in result.output
    assert "catalog unavailable" in result.output


def test_enforcement_reprocess_requires_database_for_stored_artifacts() -> None:
    result = RUNNER.invoke(app, ["reprocess", "--source", "moj_enforcement"], env={"DATABASE_URL": ""})

    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
    assert "DATABASE_URL is required" in str(result.exception)


@pytest.mark.asyncio
async def test_enforcement_reprocess_restores_complete_explicit_artifact_links() -> None:
    record_id = "11111111-1111-4111-8111-111111111111"
    detail_url = f"https://www.tpkonsale.moj.gov.tw/Detail/Chattel?NO={record_id}"
    detail = (FIXTURES / "moj_enforcement_detail.html").read_bytes()
    index = (FIXTURES / "moj_enforcement_exported_index.html").read_bytes()
    document = b"%PDF-1.4 linked supporting fixture"
    fetched_at = datetime(2026, 8, 21, tzinfo=UTC)
    base = {
        "source_record_uuid": "record-uuid",
        "source_record_id": record_id,
        "official_url": detail_url,
        "original_title": "stored title is only a fallback",
        "fetched_at": fetched_at,
        "http_status": 200,
        "http_headers": {"content-type": "text/html"},
        "artifact_role": "SUPPORTING",
        "sort_order": 1,
        "parser_version": "0.6.0",
        "last_sync_run_id": "sync-run-uuid",
        "last_seen_at": fetched_at,
    }
    rows = [
        {
            **base,
            "artifact_id": "detail-artifact",
            "artifact_url": detail_url,
            "mime_type": "text/html",
            "filename": "detail.html",
            "checksum_sha256": hashlib.sha256(detail).hexdigest(),
            "storage_path": "detail-path",
            "artifact_role": "PRIMARY",
            "sort_order": 0,
        },
        {
            **base,
            "artifact_id": "index-artifact",
            "artifact_url": "https://www.tpkonsale.moj.gov.tw/Chattel",
            "mime_type": "text/html",
            "filename": "index.html",
            "checksum_sha256": hashlib.sha256(index).hexdigest(),
            "storage_path": "index-path",
        },
        {
            **base,
            "artifact_id": "document-artifact",
            "artifact_url": (
                "https://www.tpkonsale.moj.gov.tw/File/Download?"
                f"PATH={record_id}&NAME=notice.pdf"
            ),
            "mime_type": "application/pdf",
            "filename": "notice.pdf",
            "checksum_sha256": hashlib.sha256(document).hexdigest(),
            "storage_path": "document-path",
            "sort_order": 2,
        },
    ]
    executed: list[tuple[str, tuple[object, ...]]] = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

        def execute(self, query: str, parameters: tuple[object, ...]) -> None:
            executed.append((query, parameters))

        def fetchall(self):
            return rows

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

        def cursor(self) -> Cursor:
            return Cursor()

    class Storage:
        async def get(self, path: str) -> bytes:
            return {
                "detail-path": detail,
                "index-path": index,
                "document-path": document,
            }[path]

    class Repository:
        source_id = "source-uuid"
        storage = Storage()

        def _connect(self) -> Connection:
            return Connection()

    queued, warnings = await load_moj_enforcement_reprocessable(
        Repository(),  # type: ignore[arg-type]
        "0.6.0",
        1,
    )

    assert len(queued) == 1
    item, artifacts = queued[0]
    assert item.source_record_id == record_id
    assert item.metadata["index_provenance"] == "MANUAL_OFFICIAL_HTML_EXPORT"
    assert item.discovery_artifacts[0].checksum_sha256 == hashlib.sha256(index).hexdigest()
    assert [artifact.checksum_sha256 for artifact in artifacts] == [
        hashlib.sha256(detail).hexdigest(),
        hashlib.sha256(index).hexdigest(),
        hashlib.sha256(document).hexdigest(),
    ]
    assert any("additional result pages" in warning for warning in warnings)
    query, parameters = executed[0]
    assert "join source_record_artifacts link" in query
    assert "field_evidence" not in query
    assert parameters == (
        "source-uuid",
        "0.6.0",
        1,
        "https://www.tpkonsale.moj.gov.tw/Chattel",
    )


@pytest.mark.asyncio
async def test_live_healthcheck_requires_persisted_allow_before_adapter_creation(monkeypatch) -> None:
    lifecycle = {"adapter_created": False}

    class Repository:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def require_access(self, decisions) -> None:
            raise SourceAccessBlocked("persisted policy is REVIEW_REQUIRED")

    def create_adapter(source: str):
        lifecycle["adapter_created"] = True
        raise AssertionError("adapter must not be created before persisted policy approval")

    monkeypatch.setenv("DATABASE_URL", "postgresql://fixture")
    monkeypatch.setattr(cli_module, "DatabaseRepository", Repository)
    monkeypatch.setattr(cli_module, "adapter_for", create_adapter)

    with pytest.raises(SourceAccessBlocked, match="REVIEW_REQUIRED"):
        await run_healthcheck("shwoo")

    assert lifecycle["adapter_created"] is False


@pytest.mark.asyncio
async def test_sync_finishes_run_even_when_adapter_close_fails(monkeypatch) -> None:
    lifecycle = {"finished": False}

    class Repository:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def require_access(self, decisions) -> None:
            pass

        def start_run(self) -> str:
            return "run-id"

        def finish_run(self, run_id: str, result: SyncResult) -> None:
            assert run_id == "run-id"
            lifecycle["finished"] = True

    class Adapter:
        discovery_warnings: list[str] = []

        async def discover(self):
            return []

        async def close(self) -> None:
            raise RuntimeError("close failed")

    monkeypatch.setenv("DATABASE_URL", "postgresql://fixture")
    monkeypatch.setattr(cli_module, "DatabaseRepository", Repository)
    monkeypatch.setattr(cli_module, "adapter_for", lambda source, manifest=None: Adapter())

    with pytest.raises(RuntimeError, match="close failed"):
        await run_sync("shwoo", None)

    assert lifecycle["finished"] is True


@pytest.mark.asyncio
async def test_reprocess_finishes_run_even_when_adapter_close_fails(monkeypatch) -> None:
    lifecycle = {"finished": False}

    class Repository:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def start_run(self) -> str:
            return "run-id"

        async def load_reprocessable(self, from_parser_version, limit):
            return []

        def finish_run(self, run_id: str, result: SyncResult) -> None:
            assert run_id == "run-id"
            lifecycle["finished"] = True

    class Adapter:
        async def close(self) -> None:
            raise RuntimeError("close failed")

    monkeypatch.setenv("DATABASE_URL", "postgresql://fixture")
    monkeypatch.setattr(cli_module, "DatabaseRepository", Repository)
    monkeypatch.setattr(cli_module, "adapter_for", lambda source: Adapter())

    with pytest.raises(RuntimeError, match="close failed"):
        await run_reprocess("shwoo", None, None)

    assert lifecycle["finished"] is True


@pytest.mark.asyncio
async def test_public_adapter_constructor_failure_never_creates_a_hosted_run(monkeypatch) -> None:
    lifecycle = {"started": False, "closed": False}

    class FakePublisher:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def start(self) -> str:
            lifecycle["started"] = True
            return "run-id"

        async def close(self) -> None:
            lifecycle["closed"] = True

    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(cli_module, "SupabasePublicPublisher", FakePublisher)
    monkeypatch.setattr(
        cli_module,
        "adapter_for",
        lambda source: (_ for _ in ()).throw(ValueError("invalid request interval")),
    )

    with pytest.raises(ValueError, match="invalid request interval"):
        await run_publish_public("pcc", None)

    assert lifecycle == {"started": False, "closed": True}


@pytest.mark.asyncio
async def test_public_zero_discovery_is_persisted_but_fails_the_scheduler(monkeypatch) -> None:
    lifecycle = {"finished": False, "closed": False}

    class FakePublisher:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def start(self) -> str:
            return "run-id"

        async def finish(self, result: SyncResult) -> None:
            lifecycle["finished"] = True
            assert result.discovered == 0
            assert result.warnings == ["Discovery returned zero records; prior public data was preserved"]

        async def close(self) -> None:
            lifecycle["closed"] = True

    class Adapter:
        discovery_warnings: list[str] = []

        async def discover(self):
            return []

        async def close(self) -> None:
            return None

    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(cli_module, "SupabasePublicPublisher", FakePublisher)
    monkeypatch.setattr(cli_module, "adapter_for", lambda source: Adapter())

    with pytest.raises(typer.Exit) as raised:
        await run_publish_public("pcc", None)

    assert raised.value.exit_code == 1
    assert lifecycle == {"finished": True, "closed": True}


@pytest.mark.asyncio
async def test_public_health_publication_failure_cannot_leave_actions_green(monkeypatch) -> None:
    class FakePublisher:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def start(self) -> str:
            return "run-id"

        async def publish(self, item, artifacts, record) -> bool:
            return True

        async def finish(self, result: SyncResult) -> None:
            result.failed += 1
            result.warnings.append("Sanitized public source-health publication failed")

        async def close(self) -> None:
            return None

    class Adapter:
        discovery_warnings: list[str] = []

        async def discover(self):
            return [
                DiscoveredItem(
                    source_record_id="fixture",
                    official_url="https://web.pcc.gov.tw/fixture",
                    discovery_url="https://web.pcc.gov.tw/",
                    title="機車變賣",
                )
            ]

        async def fetch(self, item):
            return [object()]

        async def parse(self, item, artifacts):
            return object()

        async def close(self) -> None:
            return None

    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(cli_module, "SupabasePublicPublisher", FakePublisher)
    monkeypatch.setattr(cli_module, "adapter_for", lambda source: Adapter())

    with pytest.raises(typer.Exit) as raised:
        await run_publish_public("pcc", None)

    assert raised.value.exit_code == 1


@pytest.mark.asyncio
async def test_local_sync_stops_after_official_access_is_denied(monkeypatch) -> None:
    checked: list[str] = []
    completed: list[SyncResult] = []

    class Repository:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def require_access(self, decisions) -> None:
            pass

        def start_run(self) -> str:
            return "run-id"

        def finish_run(self, run_id: str, result: SyncResult) -> None:
            assert run_id == "run-id"
            completed.append(result)

    class Adapter:
        discovery_warnings: list[str] = []

        async def discover(self):
            return [
                DiscoveredItem(
                    source_record_id=record_id,
                    official_url=f"https://web.pcc.gov.tw/{record_id}",
                    discovery_url="https://web.pcc.gov.tw/",
                    title="機車變賣",
                )
                for record_id in ("first", "second")
            ]

        async def fetch(self, item):
            checked.append(item.source_record_id)
            raise SourceAccessDenied("Source returned HTTP 403")

        async def close(self) -> None:
            pass

    monkeypatch.setenv("DATABASE_URL", "postgresql://fixture")
    monkeypatch.setattr(cli_module, "DatabaseRepository", Repository)
    monkeypatch.setattr(cli_module, "adapter_for", lambda source, manifest=None: Adapter())

    await run_sync("pcc", None)

    assert checked == ["first"]
    assert len(completed) == 1
    assert completed[0].discovered == 2
    assert completed[0].failed == 1
    assert "source access stopped" in completed[0].warnings[0]


@pytest.mark.asyncio
async def test_hosted_publisher_stops_after_rate_limit_and_fails_scheduler(monkeypatch) -> None:
    checked: list[str] = []
    completed: list[SyncResult] = []

    class Publisher:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def start(self) -> str:
            return "run-id"

        async def finish(self, result: SyncResult) -> None:
            completed.append(result)

        async def close(self) -> None:
            pass

    class Adapter:
        discovery_warnings: list[str] = []

        async def discover(self):
            return [
                DiscoveredItem(
                    source_record_id=record_id,
                    official_url=f"https://web.pcc.gov.tw/{record_id}",
                    discovery_url="https://web.pcc.gov.tw/",
                    title="機車變賣",
                )
                for record_id in ("first", "second")
            ]

        async def fetch(self, item):
            checked.append(item.source_record_id)
            raise SourceRateLimited(600)

        async def close(self) -> None:
            pass

    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(cli_module, "SupabasePublicPublisher", Publisher)
    monkeypatch.setattr(cli_module, "adapter_for", lambda source: Adapter())

    with pytest.raises(typer.Exit) as raised:
        await run_publish_public("pcc", None)

    assert raised.value.exit_code == 1
    assert checked == ["first"]
    assert len(completed) == 1
    assert completed[0].discovered == 2
    assert completed[0].failed == 1
    assert "retry after 600 seconds" in completed[0].warnings[0]


@pytest.mark.asyncio
async def test_hosted_discovery_failure_logs_safe_branch_diagnostics_and_finishes(monkeypatch, capsys) -> None:
    completed: list[SyncResult] = []

    class Publisher:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def start(self) -> str:
            return "run-id"

        async def finish(self, result: SyncResult) -> None:
            completed.append(result)

        async def close(self) -> None:
            pass

    class Adapter:
        discovery_warnings = [
            "tpy: robots preflight blocked https://www.tpy.moj.gov.tw/robots?token=private"
        ]

        async def discover(self):
            raise RuntimeError("No Administrative Enforcement branch CMS could be checked safely")

        async def close(self) -> None:
            pass

    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(cli_module, "SupabasePublicPublisher", Publisher)
    monkeypatch.setattr(cli_module, "adapter_for", lambda source: Adapter())

    with pytest.raises(RuntimeError, match="No Administrative Enforcement branch CMS"):
        await run_publish_public("moj_enforcement_cms", None)

    logged = capsys.readouterr().err
    assert "tpy: robots preflight blocked" in logged
    assert "token=private" not in logged
    assert len(completed) == 1
    assert completed[0].failed == 1
