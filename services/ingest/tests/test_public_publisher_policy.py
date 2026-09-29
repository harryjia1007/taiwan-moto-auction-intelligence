from __future__ import annotations

from typing import Any

import pytest

from ingest.public_publisher import PUBLISHER_SCHEMA_COLUMNS, SupabasePublicPublisher
from ingest.source_policy import SourceAccessBlocked


@pytest.mark.asyncio
async def test_hosted_publisher_starts_only_with_unique_allow_policy() -> None:
    publisher = SupabasePublicPublisher(
        "https://example.supabase.co", "test-only-key",
        source_adapter="moj_enforcement_cms",
    )
    calls: list[tuple[str, str]] = []

    async def fake_json(method: str, path: str, **kwargs: Any) -> Any:
        calls.append((method, path))
        if path.startswith("/rest/v1/sources?"):
            return [{"id": "source-id"}]
        if path.startswith("/rest/v1/source_access_policies?"):
            return [{"decision": "ALLOW"}]
        if any(path.startswith(f"/rest/v1/{table}?") for table, _ in PUBLISHER_SCHEMA_COLUMNS):
            return []
        if method == "POST" and path == "/rest/v1/sync_runs":
            return [{"id": "run-id"}]
        raise AssertionError(f"Unexpected publisher call: {method} {path}")

    publisher._json = fake_json  # type: ignore[method-assign]
    try:
        assert await publisher.start() == "run-id"
    finally:
        await publisher.close()

    assert calls == [
        ("GET", "/rest/v1/sources?adapter_name=eq.moj_enforcement_cms&select=id&limit=2"),
        ("GET", "/rest/v1/source_access_policies?source_id=eq.source-id&select=decision&limit=2"),
        *[
            ("GET", f"/rest/v1/{table}?select={','.join(columns)}&limit=0")
            for table, columns in PUBLISHER_SCHEMA_COLUMNS
        ],
        ("POST", "/rest/v1/sync_runs"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policies",
    [
        [],
        [{"decision": "MANUAL_ONLY"}],
        [{"decision": "DISABLED"}],
        [{"decision": "ALLOW"}, {"decision": "ALLOW"}],
    ],
)
async def test_hosted_publisher_blocks_missing_denied_or_duplicate_policy_without_write(
    policies: list[dict[str, str]],
) -> None:
    publisher = SupabasePublicPublisher(
        "https://example.supabase.co", "test-only-key",
        source_adapter="moj_enforcement_cms",
    )
    calls: list[tuple[str, str]] = []

    async def fake_json(method: str, path: str, **kwargs: Any) -> Any:
        calls.append((method, path))
        if path.startswith("/rest/v1/sources?"):
            return [{"id": "source-id"}]
        if path.startswith("/rest/v1/source_access_policies?"):
            return policies
        raise AssertionError(f"Unexpected publisher call: {method} {path}")

    publisher._json = fake_json  # type: ignore[method-assign]
    try:
        with pytest.raises(SourceAccessBlocked, match="public discovery was blocked"):
            await publisher.start()
    finally:
        await publisher.close()

    assert all(method == "GET" for method, _ in calls)
    assert publisher.run_id is None


@pytest.mark.asyncio
async def test_hosted_publisher_blocks_duplicate_source_before_policy_lookup() -> None:
    publisher = SupabasePublicPublisher(
        "https://example.supabase.co", "test-only-key",
        source_adapter="moj_enforcement_cms",
    )
    calls: list[tuple[str, str]] = []

    async def fake_json(method: str, path: str, **kwargs: Any) -> Any:
        calls.append((method, path))
        return [{"id": "first"}, {"id": "second"}]

    publisher._json = fake_json  # type: ignore[method-assign]
    try:
        with pytest.raises(SourceAccessBlocked, match="no unique"):
            await publisher.start()
    finally:
        await publisher.close()

    assert len(calls) == 1
    assert calls[0][0] == "GET"
    assert publisher.run_id is None


@pytest.mark.asyncio
async def test_hosted_publisher_policy_query_error_never_creates_run() -> None:
    publisher = SupabasePublicPublisher(
        "https://example.supabase.co", "test-only-key",
        source_adapter="moj_enforcement_cms",
    )
    calls: list[tuple[str, str]] = []

    async def fake_json(method: str, path: str, **kwargs: Any) -> Any:
        calls.append((method, path))
        if path.startswith("/rest/v1/sources?"):
            return [{"id": "source-id"}]
        raise RuntimeError("test-only policy lookup failure")

    publisher._json = fake_json  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="policy lookup failure"):
            await publisher.start()
    finally:
        await publisher.close()

    assert [method for method, _ in calls] == ["GET", "GET"]
    assert publisher.run_id is None
