"""Pytest fixtures for the Pride plugin."""

import pytest


@pytest.fixture
def sample_manifest():
    """Minimal manifest for instantiating PridePlugin in tests."""
    return {
        "id": "pride",
        "name": "Pride",
        "version": "0.2.0",
        "description": "Pride flags, patterns, hearts, and LGBTQ+ history for the board",
        "author": "FiestaBoard Team",
        "settings_schema": {},
        "variables": {
            "simple": [
                "art", "art_note", "piece_id", "piece_name", "piece_category",
                "tagline", "mode", "history_year", "history_text",
            ]
        },
    }


@pytest.fixture
def sample_config():
    """Default configuration matching the manifest defaults."""
    return {
        "enabled": True,
        "mode": "art",
        "selection": "pick",
        "piece": "rainbow",
        "pool": [],
        "rotate_seconds": 600,
        "message": "",
        "refresh_seconds": 300,
    }
