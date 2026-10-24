"""Board-geometry conformance for the Pride plugin.

Imports the shared suite from FiestaBoard core so the definition of "supports
every board" is the same one core holds its own plugins to, and moves in one
edit. Core is on ``PYTHONPATH`` in this repo's CI.
"""

import json
from datetime import datetime as real_datetime
from pathlib import Path
from unittest.mock import patch

from src.plugins.geometry_conformance import assert_board_conformance

from plugins.pride import ART, PridePlugin

MANIFEST = json.loads(
    (Path(__file__).resolve().parent.parent / "manifest.json").read_text()
)

BASE_CONFIG = {
    "enabled": True,
    "mode": "art",
    "selection": "pick",
    "piece": "rainbow",
    "pool": [],
    "rotate_seconds": 600,
    "message": "",
    "refresh_seconds": 300,
}

# A date the bundled dataset has an entry for, so history mode is exercised on
# its real path rather than its no-entry fallback.
HISTORY_DATE = real_datetime(2026, 6, 28, 12, 0, 0)


class _FixedDatetime:
    """`datetime` stand-in pinned to :data:`HISTORY_DATE`."""

    @classmethod
    def now(cls):
        return HISTORY_DATE


def make_plugin(**overrides):
    """A fresh, configured Pride plugin.

    Nothing to stub: the plugin's only data source is the JSON dataset
    bundled in ``data/history.json``, so it never touches the network.
    """
    plugin = PridePlugin(MANIFEST)
    plugin.config = {**BASE_CONFIG, **overrides}
    return plugin


def test_renders_on_every_board_shape():
    """Art mode: one full-board picture, so it must fill any board exactly."""
    report = assert_board_conformance(
        make_plugin,
        manifest=MANIFEST,
        strict_growth=True,
        require_note_array_preview=True,
    )
    # Art is whole-board content, so every row of every board is used.
    assert report.rows_by_geometry["max array 120x24"] == 24, report.summary()
    assert report.rows_by_geometry["note 15x3"] == 3, report.summary()


def test_renders_on_every_board_shape_in_history_mode():
    """History mode: text, so growth is content-bound rather than guaranteed.

    ``strict_growth`` is off here because how many lines today's entry wraps
    to depends on the entry, not the board — the bounds, unbound-board and
    declared-length checks all still apply.
    """
    with patch("plugins.pride.datetime", _FixedDatetime):
        assert_board_conformance(
            lambda: make_plugin(mode="history"),
            manifest=MANIFEST,
            require_note_array_preview=True,
        )


def test_manifest_previews_fit_the_boards_they_claim():
    """Preview rows are literal board text: never taller or wider than the board."""
    from src.devices import NOTE_COLS, NOTE_ROWS, get_dimensions
    from src.text_to_board import count_tiles

    previews = MANIFEST["previews"]
    assert any(p["device_type"] == "note_array" for p in previews), previews

    for preview in previews:
        device = preview["device_type"]
        if device == "note_array":
            wide, tall = preview["notes_wide"], preview["notes_tall"]
            assert 1 <= wide <= 4 and 1 <= tall <= 4, preview
            rows, cols = tall * NOTE_ROWS, wide * NOTE_COLS
        else:
            rows, cols = get_dimensions(device)
        assert len(preview["rows"]) <= rows, preview["label"]
        for row in preview["rows"]:
            assert count_tiles(row) <= cols, (preview["label"], row)


def test_every_piece_conforms_on_every_board_shape():
    """Run the suite once per catalog entry: each has its own renderer."""
    for piece_id in ART:
        with patch("plugins.pride.time.time", return_value=1_700_000_000):
            assert_board_conformance(
                lambda pid=piece_id: make_plugin(piece=pid),
                manifest=MANIFEST,
                strict_growth=True,
                require_note_array_preview=True,
            )
