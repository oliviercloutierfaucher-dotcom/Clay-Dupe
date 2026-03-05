"""Synchronous wrapper for async Database methods.

Usage::

    from data.sync import run_sync

    db = Database("clay_dupe.db")
    stats = run_sync(db.get_dashboard_stats())
    campaigns = run_sync(db.get_recent_campaigns(limit=5))

Works safely whether or not an event loop is already running
(e.g. inside Streamlit or Jupyter).
"""
from __future__ import annotations

import asyncio
from typing import Any, Coroutine

import nest_asyncio

# Patch asyncio so run_until_complete works inside an already-running loop
# (Streamlit, Jupyter, etc.).
nest_asyncio.apply()

_loop: asyncio.AbstractEventLoop | None = None


def run_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    """Execute an async coroutine synchronously and return its result."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)
