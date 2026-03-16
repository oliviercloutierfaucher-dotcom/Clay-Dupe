"""Shared httpx.AsyncClient singleton for all providers.

Reuses TLS connections and avoids per-provider client creation.
"""
from __future__ import annotations

import asyncio

import httpx

_shared_client: httpx.AsyncClient | None = None
_init_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    """Lazily create the init lock (must be created inside a running loop)."""
    global _init_lock
    if _init_lock is None:
        _init_lock = asyncio.Lock()
    return _init_lock


async def get_shared_client() -> httpx.AsyncClient:
    """Return the module-level shared AsyncClient, creating it lazily.

    Thread-safe within a single event loop via asyncio.Lock.
    """
    global _shared_client
    # Fast path: client already exists and is open
    if _shared_client is not None and not _shared_client.is_closed:
        return _shared_client

    async with _get_lock():
        # Double-check after acquiring lock
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
