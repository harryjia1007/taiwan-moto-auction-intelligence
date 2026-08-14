import os
from abc import ABC, abstractmethod

import httpx

from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SourceHealth


def contact_user_agent(version: str) -> str:
    contact = os.getenv("INGEST_CONTACT_URL", "https://harryjia.com/projects/taiwan-moto-auction")
    return f"TaiwanMotoAuctionIntelligence/{version} (+{contact})"


class SourceAccessDenied(RuntimeError):
    """The official source refused automated access; do not retry the run."""


class SourceRateLimited(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Source rate limited this run; retry after {retry_after_seconds} seconds")


def enforce_http_status(response: httpx.Response) -> None:
    """Fail closed on policy responses instead of retrying them as transient errors."""
    if response.status_code == 403:
        raise SourceAccessDenied("Source returned HTTP 403; live access stopped pending policy review")
    if response.status_code == 429:
        raw = response.headers.get("retry-after", "1").strip()
        seconds = int(raw) if raw.isdigit() else 60
        raise SourceRateLimited(max(1, min(seconds, 3600)))
    response.raise_for_status()


class SourceAdapter(ABC):
    @abstractmethod
    async def close(self) -> None:
        """Release network resources owned by the adapter."""

    @abstractmethod
    async def discover(self) -> list[DiscoveredItem]:
        """Return stable official record identities without fetching full records."""

    @abstractmethod
    async def fetch(self, item: DiscoveredItem) -> list[RawArtifact]:
        """Fetch and preserve official artifacts before parsing."""

    @abstractmethod
    async def parse(self, item: DiscoveredItem, artifacts: list[RawArtifact]) -> ParsedAuctionRecord:
        """Normalize a record while retaining field-level evidence."""

    @abstractmethod
    async def healthcheck(self) -> SourceHealth:
        """Perform a bounded read-only check of the public source."""
