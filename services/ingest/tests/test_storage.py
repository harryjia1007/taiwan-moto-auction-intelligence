import hashlib
from datetime import UTC, datetime

import pytest

from ingest.models import RawArtifact
from ingest.storage import LocalArtifactStorage


@pytest.mark.asyncio
async def test_checksum_addressed_local_storage_round_trip(tmp_path) -> None:
    content = b"official artifact"
    checksum = hashlib.sha256(content).hexdigest()
    artifact = RawArtifact(
        official_url="https://shwoo.gov.taipei/shwoo/example",
        fetched_at=datetime.now(UTC),
        mime_type="text/html",
        content=content,
        checksum_sha256=checksum,
    )
    storage = LocalArtifactStorage(str(tmp_path))
    first_path = await storage.put(artifact)
    second_path = await storage.put(artifact)
    assert first_path == second_path
    assert first_path.startswith(checksum[:2])
    assert await storage.get(first_path) == content
