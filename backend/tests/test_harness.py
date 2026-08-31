"""The QA harness page is served, unauthenticated, at the root.

What the page then does in a browser is browser work, not pytest's: this asserts
only that the file reaches a client that presents no token at all.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.anyio


async def test_harness_page_is_served_without_a_token(serve_url: str) -> None:
    async with httpx.AsyncClient(base_url=serve_url) as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>AgentQuilt harness</title>" in response.text
