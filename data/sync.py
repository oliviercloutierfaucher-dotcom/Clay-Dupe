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


def run_sync(coro: Coroutine[Any, Any, Any], timeout: float = 30.0) -> Any:
    """Execute an async coroutine synchronously and return its result.

    Parameters
    ----------
    coro : Coroutine
        The async coroutine to execute.
    timeout : float
        Maximum seconds to wait before aborting.  Defaults to 30.
        Pass ``None`` to disable the timeout.

    Raises
    ------
    TimeoutError
        If the coroutine does not complete within *timeout* seconds.
    """
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    try:
        if timeout is not None:
            return _loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
        return _loop.run_until_complete(coro)
    except asyncio.TimeoutError:
        raise TimeoutError(
            f"run_sync: coroutine did not complete within {timeout}s timeout"
        ) from None
