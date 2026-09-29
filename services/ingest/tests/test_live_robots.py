import httpx
import pytest

from ingest.adapters.base import LiveRobotsPolicy, SourceAccessDenied
from ingest.adapters.customs import CustomsAuctionAdapter
from ingest.adapters.moj_auction import MojAuctionAdapter
from ingest.adapters.pcc import PccAssetSaleAdapter
from ingest.adapters.shwoo import ShwooAdapter


ROBOTS_URL = "https://official.example/robots.txt"
TARGET_URL = "https://official.example/auction/list"


@pytest.mark.asyncio
async def test_live_robots_policy_is_cached_only_until_explicit_run_reset() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        return httpx.Response(
            200,
            content=b"User-agent: *\nAllow: /auction/\n",
            headers={"content-type": "text/plain; charset=utf-8"},
        )

    policy = LiveRobotsPolicy(
        ROBOTS_URL,
        allowed_host="official.example",
        user_agent="FixtureBot/1.0",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await policy.ensure_allowed(client, TARGET_URL)
        await policy.ensure_allowed(client, TARGET_URL)
        assert contacted == [ROBOTS_URL]

        policy.reset()
        await policy.ensure_allowed(client, TARGET_URL)

    assert contacted == [ROBOTS_URL, ROBOTS_URL]


@pytest.mark.asyncio
async def test_live_robots_policy_never_uses_stale_allow_after_refresh_failure() -> None:
    responses = iter(
        (
            httpx.Response(
                200,
                content=b"User-agent: *\nAllow: /\n",
                headers={"content-type": "text/plain"},
            ),
            httpx.Response(503, content=b"unavailable", headers={"content-type": "text/plain"}),
        )
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return next(responses)

    policy = LiveRobotsPolicy(
        ROBOTS_URL,
        allowed_host="official.example",
        user_agent="FixtureBot/1.0",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await policy.ensure_allowed(client, TARGET_URL)
        policy.reset()
        with pytest.raises(SourceAccessDenied, match="failed closed"):
            await policy.ensure_allowed(client, TARGET_URL)

    with pytest.raises(SourceAccessDenied, match="not loaded"):
        policy.require_allowed(TARGET_URL)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "content_type", "message"),
    [
        (b"<html>gateway</html>", "text/html", "unexpected MIME"),
        (b"Allow: /\n", "text/plain", "no explicit User-agent"),
        (b"User-agent: *\nDisallow: /auction/\n", "text/plain", "disallows"),
    ],
)
async def test_live_robots_policy_fails_closed_on_unusable_or_disallowing_policy(
    content: bytes,
    content_type: str,
    message: str,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, headers={"content-type": content_type})

    policy = LiveRobotsPolicy(
        ROBOTS_URL,
        allowed_host="official.example",
        user_agent="FixtureBot/1.0",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceAccessDenied, match=message):
            await policy.ensure_allowed(client, TARGET_URL)


@pytest.mark.asyncio
async def test_live_robots_redirect_never_crosses_the_reviewed_host() -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://attacker.example/robots.txt"})

    policy = LiveRobotsPolicy(
        ROBOTS_URL,
        allowed_host="official.example",
        user_agent="FixtureBot/1.0",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceAccessDenied, match="Cross-host"):
            await policy.ensure_allowed(client, TARGET_URL)

    assert contacted == [ROBOTS_URL]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "adapter_type",
    [ShwooAdapter, MojAuctionAdapter, CustomsAuctionAdapter, PccAssetSaleAdapter],
)
async def test_allow_adapters_stop_discovery_after_live_robots_disallow(
    adapter_type: type,
) -> None:
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        if request.url.path != "/robots.txt":
            raise AssertionError(f"disallowed discovery target was contacted: {request.url}")
        return httpx.Response(
            200,
            content=b"User-agent: *\nDisallow: /\n",
            headers={"content-type": "text/plain"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = adapter_type(client=client, request_interval=0)
        with pytest.raises(SourceAccessDenied, match="disallows"):
            await adapter.discover()

    assert contacted == [adapter_type.ROBOTS_URL]
