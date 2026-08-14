import hashlib
from datetime import UTC, datetime

import httpx
import pytest

from ingest.models import RawArtifact
from ingest.storage import LocalArtifactStorage, SupabaseArtifactStorage


def artifact_for(content: bytes = b"official artifact") -> RawArtifact:
    return RawArtifact(
        official_url="https://shwoo.gov.taipei/shwoo/example",
        fetched_at=datetime.now(UTC),
        mime_type="text/html",
        content=content,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )


@pytest.mark.asyncio
async def test_checksum_addressed_local_storage_round_trip(tmp_path) -> None:
    artifact = artifact_for()
    storage = LocalArtifactStorage(str(tmp_path))
    first_path = await storage.put(artifact)
    second_path = await storage.put(artifact)
    assert first_path == second_path
    assert first_path.startswith(artifact.checksum_sha256[:2])
    assert await storage.get(first_path) == artifact.content


@pytest.mark.asyncio
async def test_local_storage_deletes_only_inside_configured_root(tmp_path) -> None:
    artifact = artifact_for()
    storage = LocalArtifactStorage(str(tmp_path))
    stored_path = await storage.put(artifact)
    await storage.delete(stored_path)
    with pytest.raises(FileNotFoundError):
        await storage.get(stored_path)
    with pytest.raises(ValueError, match="escapes"):
        await storage.delete("../outside.txt")


@pytest.mark.asyncio
async def test_supabase_storage_accepts_exact_duplicate_response() -> None:
    artifact = artifact_for()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "statusCode": "409",
                "error": "Duplicate",
                "message": "The resource already exists",
                "code": "KeyAlreadyExists",
            },
        )

    storage = SupabaseArtifactStorage(
        "http://supabase.test",
        "local-test-key",
        transport=httpx.MockTransport(handler),
    )
    path = await storage.put(artifact)
    assert path.startswith(artifact.checksum_sha256[:2])


@pytest.mark.asyncio
async def test_supabase_storage_does_not_hide_other_bad_requests() -> None:
    artifact = artifact_for()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"statusCode": "400", "error": "Bad Request", "message": "invalid bucket"})

    storage = SupabaseArtifactStorage(
        "http://supabase.test",
        "local-test-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RuntimeError, match=r"HTTP 400, Bad Request.*invalid bucket"):
        await storage.put(artifact)


@pytest.mark.asyncio
async def test_supabase_storage_accepts_missing_object_during_retention_delete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        return httpx.Response(404)

    storage = SupabaseArtifactStorage("http://supabase.test", "local-test-key", transport=httpx.MockTransport(handler))
    await storage.delete("aa/missing.html")
