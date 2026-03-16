"""Shared resource singletons for sub-pages.

Extracted from app.py so that page imports never trigger UI side effects.
"""
from __future__ import annotations

import streamlit as st

from config.settings import load_settings, Settings, ProviderName
from data.database import Database
from ui.validation import validate_api_keys


@st.cache_resource
def get_database() -> Database:
    """Return a singleton Database instance (WAL-mode, thread-safe reads)."""
    settings = get_settings()
    return Database(db_path=settings.db_path)


@st.cache_resource
def get_settings() -> Settings:
    """Return a singleton Settings instance loaded from environment."""
    return load_settings()


@st.cache_data(ttl=300)
def _cached_validate_api_keys() -> dict[str, bool]:
    """Run API key validation with 5-minute cache."""
    return validate_api_keys(get_settings())


def get_key_validation_status() -> dict[str, bool]:
    """Get current API key validation status (cached)."""
    return _cached_validate_api_keys()
