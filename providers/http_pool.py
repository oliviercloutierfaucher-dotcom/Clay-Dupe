"""Shared httpx.AsyncClient singleton for all providers.

Reuses TLS connections and avoids per-provider client creation.
"""
from __future__ import annotations

import httpx

_shared_client: httpx.AsyncClient | None = None


def get_shared_client() -> httpx.AsyncClient:
    """Return the module-level shared AsyncClient, creating it lazily."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=30,
            ),
        )
    return _shared_client


async def close_shared_client() -> None:
    """Close the shared client (call at shutdown)."""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None
