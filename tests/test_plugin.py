"""Unit tests for the Pride plugin."""

from unittest.mock import patch

import pytest

from plugins.pride import FLAGS, ROTATION_ORDER, PridePlugin
from plugins.pride import _load_history


class TestPridePlugin:
    """Tests for PridePlugin."""

    def test_plugin_id(self, sample_manifest):
        plugin = PridePlugin(sample_manifest)
        assert plugin.plugin_id == "pride"

    def test_validate_config_accepts_defaults(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        assert plugin.validate_config(sample_config) == []

    def test_validate_config_rejects_unknown_flag(self, sample_manifest):
        plugin = PridePlugin(sample_manifest)
        errors = plugin.validate_config({"flag": "definitely-not-a-flag"})
        assert any("flag" in e.lower() for e in errors)

    def test_validate_config_rejects_bad_device_type(self, sample_manifest):
        plugin = PridePlugin(sample_manifest)
        errors = plugin.validate_config({"device_type": "billboard"})
        assert any("device" in e.lower() for e in errors)

    def test_validate_config_rejects_short_refresh(self, sample_manifest):
        plugin = PridePlugin(sample_manifest)
        errors = plugin.validate_config({"refresh_seconds": 10})
        assert any("refresh" in e.lower() for e in errors)

    def test_validate_config_rejects_long_message(self, sample_manifest):
        plugin = PridePlugin(sample_manifest)
        errors = plugin.validate_config({"message": "x" * 30})
        assert any("message" in e.lower() for e in errors)

    def test_rainbow_flagship_has_six_distinct_color_rows(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "flag": "rainbow"}
        result = plugin.fetch_data()
        assert result.available
        rows = result.data["art"].split("\n")
        assert len(rows) == 6
        expected = ["{red}", "{orange}", "{yellow}", "{green}", "{blue}", "{violet}"]
        for row, marker in zip(rows, expected):
            assert row.count(marker) == 22, f"row {row!r} should be 22 {marker}"
            assert row == marker * 22

    def test_note_device_returns_three_rows(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "flag": "rainbow", "device_type": "note"}
        result = plugin.fetch_data()
        assert result.available
        rows = result.data["art"].split("\n")
        assert len(rows) == 3
        # Each row is one color marker repeated 15 times
        for row in rows:
            assert len(row) > 0
            marker = row.split("}")[0] + "}"
            assert row == marker * 15

    def test_rotate_is_deterministic_for_same_window(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "flag": "rotate", "rotate_seconds": 600}
        with patch("plugins.pride.time.time", return_value=1_700_000_000):
            first = plugin.fetch_data().data["flag_name"]
        with patch("plugins.pride.time.time", return_value=1_700_000_000 + 599):
            second = plugin.fetch_data().data["flag_name"]
        assert first == second

    def test_rotate_advances_across_windows(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "flag": "rotate", "rotate_seconds": 600}
        seen = set()
        for window in range(len(ROTATION_ORDER)):
            with patch("plugins.pride.time.time", return_value=window * 600):
                seen.add(plugin.fetch_data().data["flag_name"])
        assert seen == {FLAGS[f]["name"] for f in ROTATION_ORDER}

    def test_every_flag_renders_without_error(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        for flag_id in FLAGS:
            plugin.config = {**sample_config, "flag": flag_id}
            result = plugin.fetch_data()
            assert result.available, f"{flag_id} should render"
            assert result.data["flag_name"] == FLAGS[flag_id]["name"]
            assert len(result.data["art"].split("\n")) == 6

    def test_message_overlays_on_center_row(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "flag": "rainbow", "message": "Hello"}
        result = plugin.fetch_data()
        rows = result.data["art"].split("\n")
        # Center row of a 6-row board is index 3 (rows // 2)
        center = rows[3]
        assert "HELLO" in center
        # Letters replaced their tiles, so the center row is no longer pure green
        assert center.count("{green}") < 22

    def test_history_data_loads(self):
        history = _load_history()
        assert isinstance(history, list)
        assert len(history) > 20
        for entry in history:
            assert "date" in entry
            assert "text" in entry

    def test_history_picks_today(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "mode": "history"}

        class _FakeDatetime:
            @classmethod
            def now(cls):
                from datetime import datetime
                return datetime(2026, 6, 28, 12, 0, 0)

        with patch("plugins.pride.datetime", _FakeDatetime):
            result = plugin.fetch_data()
        assert result.available
        assert result.data["mode"] == "history"
        # 06-28 has a Stonewall entry
        assert "STONEWALL" in result.data["art"].upper() or "1969" in result.data["art"]

    def test_history_fallback_when_no_entry(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "mode": "history"}

        history = _load_history()
        used_dates = {e["date"] for e in history}
        # Pick a date that exists in every year but isn't in the dataset.
        fallback_date = next(
            f"{m:02d}-{d:02d}"
            for m in range(1, 13)
            for d in (1, 5, 7, 11, 13)
            if f"{m:02d}-{d:02d}" not in used_dates
        )
        month, day = (int(p) for p in fallback_date.split("-"))

        class _FakeDatetime:
            @classmethod
            def now(cls):
                from datetime import datetime
                return datetime(2026, month, day, 12, 0, 0)

        with patch("plugins.pride.datetime", _FakeDatetime):
            result = plugin.fetch_data()
        assert result.available
        assert "HAPPY PRIDE" in result.data["art"]
        assert result.data["mode"] == "history"
