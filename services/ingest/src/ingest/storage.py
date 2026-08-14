from __future__ import annotations

import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from ingest.models import RawArtifact


class ArtifactStorage(ABC):
    @abstractmethod
    async def put(self, artifact: RawArtifact) -> str:
        """Persist bytes by checksum and return the immutable storage path."""

    @abstractmethod
    async def get(self, path: str) -> bytes:
        """Read immutable bytes previously stored at path."""

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete expired private bytes while append-only metadata remains."""


class LocalArtifactStorage(ArtifactStorage):
    def __init__(self, root: str = "/data/raw-artifacts") -> None:
        self.root = Path(root)

    async def put(self, artifact: RawArtifact) -> str:
        suffix = mimetypes.guess_extension(artifact.mime_type) or ".bin"
        relative = Path(artifact.checksum_sha256[:2]) / f"{artifact.checksum_sha256}{suffix}"
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(artifact.content)
        return relative.as_posix()

    async def get(self, path: str) -> bytes:
        return (self.root / path).read_bytes()

    async def delete(self, path: str) -> None:
        target = (self.root / path).resolve()
        root = self.root.resolve()
        if root not in target.parents:
            raise ValueError("Artifact path escapes the configured storage root")
        target.unlink(missing_ok=True)


class SupabaseArtifactStorage(ArtifactStorage):
    DUPLICATE_CODES = {"KeyAlreadyExists", "ResourceAlreadyExists"}

    def __init__(
        self,
        url: str,
        service_role_key: str,
        bucket: str = "raw-artifacts",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.key = service_role_key
        self.bucket = bucket
        self.transport = transport

    async def put(self, artifact: RawArtifact) -> str:
        suffix = mimetypes.guess_extension(artifact.mime_type) or ".bin"
        path = f"{artifact.checksum_sha256[:2]}/{artifact.checksum_sha256}{suffix}"
        endpoint = f"{self.url}/storage/v1/object/{self.bucket}/{path}"
        headers = {
            "Authorization": f"Bearer {self.key}", "apikey": self.key,
            "Content-Type": artifact.mime_type, "x-upsert": "false",
        }
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            response = await client.post(endpoint, headers=headers, content=artifact.content)
            if response.status_code in (200, 201):
                return path
            try:
                problem = response.json()
            except ValueError:
                problem = {}
            duplicate = (
                response.status_code in (400, 409)
                and problem.get("code") in self.DUPLICATE_CODES
                and str(problem.get("statusCode")) == "409"
                and problem.get("error") == "Duplicate"
            )
            if not duplicate:
                code = str(problem.get("code") or problem.get("error") or "unknown")
                message = str(problem.get("message") or "Storage rejected the artifact")[:240]
                raise RuntimeError(f"Supabase Storage upload failed (HTTP {response.status_code}, {code}): {message}")
        return path

    async def get(self, path: str) -> bytes:
        endpoint = f"{self.url}/storage/v1/object/authenticated/{self.bucket}/{path}"
        headers = {"Authorization": f"Bearer {self.key}", "apikey": self.key}
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            response = await client.get(endpoint, headers=headers)
            response.raise_for_status()
            return response.content

    async def delete(self, path: str) -> None:
        endpoint = f"{self.url}/storage/v1/object/{self.bucket}/{path}"
        headers = {"Authorization": f"Bearer {self.key}", "apikey": self.key}
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            response = await client.delete(endpoint, headers=headers)
            if response.status_code not in (200, 204, 404):
                response.raise_for_status()
