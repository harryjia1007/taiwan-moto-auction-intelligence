import os
import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

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


class LiveRobotsPolicy:
    """Fail-closed, run-scoped robots policy for an exact official host.

    A successful policy is cached only inside the current adapter operation so
    detail/image requests do not refetch ``robots.txt``. ``reset`` is called at
    the beginning of every discovery; a later robots failure never falls back
    to a policy loaded by an earlier discovery.
    """

    MAX_BYTES = 256 * 1024
    MAX_REDIRECTS = 3

    def __init__(
        self,
        robots_url: str,
        *,
        allowed_host: str,
        user_agent: str,
        timeout_seconds: float = 10,
    ) -> None:
        self.robots_url = robots_url
        self.allowed_host = allowed_host.lower()
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self._parser: RobotFileParser | None = None
        self.loaded_at: datetime | None = None

    def reset(self) -> None:
        self._parser = None
        self.loaded_at = None

    def _validate_policy_url(self, value: str) -> None:
        parsed = urlparse(value)
        try:
            port = parsed.port
        except ValueError as exc:
            raise SourceAccessDenied(f"Malformed robots URL was blocked: {value}") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname != self.allowed_host
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
        ):
            raise SourceAccessDenied(f"Cross-host robots URL was blocked: {value}")

    async def _load(self, client: httpx.AsyncClient) -> None:
        current_url = self.robots_url
        self._validate_policy_url(current_url)
        try:
            for _ in range(self.MAX_REDIRECTS + 1):
                response = await client.get(
                    current_url,
                    follow_redirects=False,
                    timeout=self.timeout_seconds,
                )
                if not response.is_redirect:
                    break
                location = response.headers.get("location")
                if not location:
                    raise SourceAccessDenied("robots redirect omitted Location")
                current_url = urljoin(str(response.url), location)
                self._validate_policy_url(current_url)
            else:
                raise SourceAccessDenied("robots redirect limit exceeded")
            enforce_http_status(response)
        except (SourceAccessDenied, SourceRateLimited):
            raise
        except (httpx.HTTPError, TimeoutError) as exc:
            raise SourceAccessDenied(
                f"Live robots preflight failed closed: {type(exc).__name__}"
            ) from exc

        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "text/plain":
            raise SourceAccessDenied(
                f"robots.txt returned unexpected MIME type: {content_type or 'missing'}"
            )
        if len(response.content) > self.MAX_BYTES:
            raise SourceAccessDenied(f"robots.txt exceeded {self.MAX_BYTES} bytes")
        try:
            text = response.content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SourceAccessDenied("robots.txt was not valid UTF-8 text") from exc
        if not re.search(r"(?im)^\s*user-agent\s*:", text):
            raise SourceAccessDenied("robots.txt had no explicit User-agent directive")

        parser = RobotFileParser()
        parser.set_url(current_url)
        parser.parse(text.splitlines())
        self._parser = parser
        self.loaded_at = datetime.now(UTC)

    async def ensure_allowed(self, client: httpx.AsyncClient, url: str) -> None:
        if self._parser is None:
            await self._load(client)
        self.require_allowed(url)

    def require_allowed(self, url: str) -> None:
        if self._parser is None:
            raise SourceAccessDenied("Live robots policy was not loaded")
        parsed = urlparse(url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise SourceAccessDenied(f"Malformed source URL was blocked by robots policy: {url}") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname != self.allowed_host
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
        ):
            raise SourceAccessDenied(f"Source URL is outside the live robots policy host: {url}")
        if not self._parser.can_fetch(self.user_agent, url):
            raise SourceAccessDenied(f"robots.txt disallows live collection: {url}")


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
