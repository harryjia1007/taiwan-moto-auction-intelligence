from abc import ABC, abstractmethod

from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SourceHealth


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
