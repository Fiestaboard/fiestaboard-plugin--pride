"""Pytest fixtures for the Pride plugin."""

import pytest


@pytest.fixture
def sample_manifest():
    """Minimal manifest for instantiating PridePlugin in tests."""
    return {
        "id": "pride",
        "name": "Pride",
        "version": "0.1.0",
        "description": "Pride flags and LGBTQ+ history for the board",
        "author": "FiestaBoard Team",
        "settings_schema": {},
        "variables": {
            "simple": ["art", "flag_name", "tagline", "mode", "history_year", "history_text"]
        },
    }


@pytest.fixture
def sample_config():
    """Default configuration matching the manifest defaults."""
    return {
        "enabled": True,
        "mode": "flag",
        "flag": "rainbow",
        "device_type": "flagship",
        "rotate_seconds": 600,
        "message": "",
        "refresh_seconds": 300,
    }
