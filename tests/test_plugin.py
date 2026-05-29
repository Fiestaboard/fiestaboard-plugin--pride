"""Unit tests for the Pride plugin."""

from unittest.mock import patch

import pytest

from plugins.pride import (
    ART,
    CATEGORIES,
    ROTATION_ORDER,
    SPARKLE_MUTATION_SECONDS,
    PridePlugin,
    _load_history,
)


class TestPridePlugin:
    """Tests for PridePlugin."""

    # ------------------------------------------------------------ basics

    def test_plugin_id(self, sample_manifest):
        plugin = PridePlugin(sample_manifest)
        assert plugin.plugin_id == "pride"

    def test_rotation_order_covers_all_art(self):
        assert set(ROTATION_ORDER) == set(ART.keys())
        assert len(ROTATION_ORDER) == len(ART)

    def test_every_piece_has_required_fields(self):
        for piece_id, piece in ART.items():
            assert "name" in piece, piece_id
            assert "tagline" in piece, piece_id
            assert "category" in piece, piece_id
            assert "kind" in piece, piece_id
            assert piece["category"] in CATEGORIES, piece_id

    # ----------------------------------------------------------- validation

    def test_validate_config_accepts_defaults(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        assert plugin.validate_config(sample_config) == []

    def test_validate_config_rejects_unknown_piece(self, sample_manifest):
        plugin = PridePlugin(sample_manifest)
        errors = plugin.validate_config({"piece": "not-a-real-piece"})
        assert any("piece" in e.lower() for e in errors)

    def test_validate_config_rejects_bad_selection(self, sample_manifest):
        plugin = PridePlugin(sample_manifest)
        errors = plugin.validate_config({"selection": "whatever"})
        assert any("selection" in e.lower() for e in errors)

    def test_validate_config_rejects_unknown_pool_category(self, sample_manifest):
        plugin = PridePlugin(sample_manifest)
        errors = plugin.validate_config({"pool": ["flag", "imaginary"]})
        assert any("category" in e.lower() for e in errors)

    def test_validate_config_rejects_short_refresh(self, sample_manifest):
        plugin = PridePlugin(sample_manifest)
        errors = plugin.validate_config({"refresh_seconds": 10})
        assert any("refresh" in e.lower() for e in errors)

    def test_validate_config_rejects_long_message(self, sample_manifest):
        plugin = PridePlugin(sample_manifest)
        errors = plugin.validate_config({"message": "x" * 30})
        assert any("message" in e.lower() for e in errors)

    # ------------------------------------------- both sizes always published

    def test_each_fetch_publishes_both_sizes(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": "rainbow"}
        result = plugin.fetch_data()
        assert result.available
        flagship_rows = result.data["art"].split("\n")
        note_rows = result.data["art_note"].split("\n")
        assert len(flagship_rows) == 6
        assert len(note_rows) == 3

    def test_rainbow_flagship_has_six_distinct_color_rows(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": "rainbow"}
        result = plugin.fetch_data()
        rows = result.data["art"].split("\n")
        expected = ["{red}", "{orange}", "{yellow}", "{green}", "{blue}", "{violet}"]
        for row, marker in zip(rows, expected):
            assert row == marker * 22

    def test_every_piece_renders_at_both_sizes(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        # Pin the wall clock so the time-evolving pieces produce a stable result.
        with patch("plugins.pride.time.time", return_value=1_700_000_000):
            for piece_id in ART:
                plugin.config = {
                    **sample_config, "selection": "pick", "piece": piece_id,
                }
                result = plugin.fetch_data()
                assert result.available, piece_id
                assert len(result.data["art"].split("\n")) == 6, piece_id
                assert len(result.data["art_note"].split("\n")) == 3, piece_id
                assert result.data["piece_id"] == piece_id
                assert result.data["piece_name"] == ART[piece_id]["name"]
                assert result.data["piece_category"] == ART[piece_id]["category"]

    def test_vertical_stripes_use_column_distribution(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {
            **sample_config, "selection": "pick", "piece": "rainbow_columns",
        }
        rows = plugin.fetch_data().data["art"].split("\n")
        assert all(row == rows[0] for row in rows)
        for marker in ("{red}", "{orange}", "{yellow}", "{green}", "{blue}", "{violet}"):
            assert marker in rows[0]

    def test_diagonal_contains_every_spectrum_color(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {
            **sample_config, "selection": "pick", "piece": "rainbow_diagonal",
        }
        art = plugin.fetch_data().data["art"]
        for marker in ("{red}", "{orange}", "{yellow}", "{green}", "{blue}", "{violet}"):
            assert marker in art, marker

    def test_heart_uses_black_background_and_rainbow_body(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {
            **sample_config, "selection": "pick", "piece": "rainbow_heart",
        }
        art = plugin.fetch_data().data["art"]
        assert "{black}" in art
        assert "{red}" in art
        assert "{violet}" in art

    def test_equality_uses_blue_and_yellow_only(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": "equality"}
        art = plugin.fetch_data().data["art"]
        assert "{blue}" in art
        assert "{yellow}" in art
        assert "{red}" not in art

    # ------------------------------------------------------ sparkle is alive

    def test_sparkle_is_stable_within_a_mutation_window(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": "rainbow_sparkle"}
        base_time = 1_700_000_000
        with patch("plugins.pride.time.time", return_value=base_time):
            first = plugin.fetch_data().data["art"]
        with patch("plugins.pride.time.time", return_value=base_time + SPARKLE_MUTATION_SECONDS - 1):
            second = plugin.fetch_data().data["art"]
        assert first == second

    def test_sparkle_changes_one_tile_per_window(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": "rainbow_sparkle"}
        base_time = 1_700_000_000  # frame is large enough that density is full
        with patch("plugins.pride.time.time", return_value=base_time):
            first = plugin.fetch_data().data["art"]
        with patch("plugins.pride.time.time", return_value=base_time + SPARKLE_MUTATION_SECONDS):
            second = plugin.fetch_data().data["art"]
        assert first != second

    def test_sparkle_warm_up_density_is_bounded(self, sample_manifest, sample_config):
        """At a fixed time, the sparkle field has at most `density` colored tiles."""
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": "rainbow_sparkle"}
        with patch("plugins.pride.time.time", return_value=1_700_000_000):
            art = plugin.fetch_data().data["art"]
        # 6 rows * 22 cols // 5 = 26 max active mutations; tile collisions can
        # only lower the count, so at most 26 non-black markers appear.
        colored = sum(
            art.count(marker)
            for marker in ("{red}", "{orange}", "{yellow}", "{green}", "{blue}", "{violet}")
        )
        assert colored <= 26

    # ----------------------------------------------------- selection modes

    def test_selection_pick_uses_explicit_piece(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": "trans"}
        assert plugin.fetch_data().data["piece_id"] == "trans"

    def test_selection_rotate_is_deterministic_within_window(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "rotate", "rotate_seconds": 600}
        with patch("plugins.pride.time.time", return_value=1_700_000_000):
            first = plugin.fetch_data().data["piece_id"]
        with patch("plugins.pride.time.time", return_value=1_700_000_000 + 599):
            second = plugin.fetch_data().data["piece_id"]
        assert first == second

    def test_selection_rotate_visits_every_piece(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "rotate", "rotate_seconds": 600}
        seen = set()
        for window in range(len(ROTATION_ORDER)):
            with patch("plugins.pride.time.time", return_value=window * 600):
                seen.add(plugin.fetch_data().data["piece_id"])
        assert seen == set(ROTATION_ORDER)

    def test_selection_daily_is_stable_across_a_day(self, sample_manifest, sample_config):
        from datetime import datetime as real_dt

        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "daily"}

        class _FakeDt:
            @classmethod
            def now(cls):
                return real_dt(2026, 6, 28, 9, 0, 0)

        with patch("plugins.pride.datetime", _FakeDt):
            morning = plugin.fetch_data().data["piece_id"]

        class _FakeDtEvening:
            @classmethod
            def now(cls):
                return real_dt(2026, 6, 28, 23, 59, 0)

        with patch("plugins.pride.datetime", _FakeDtEvening):
            evening = plugin.fetch_data().data["piece_id"]

        assert morning == evening

    def test_selection_daily_changes_across_days(self, sample_manifest, sample_config):
        from datetime import datetime as real_dt

        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "daily"}

        picks = set()
        for day in range(1, 22):
            class _FakeDt:
                @classmethod
                def now(cls, _day=day):
                    return real_dt(2026, 6, _day, 12, 0, 0)
            with patch("plugins.pride.datetime", _FakeDt):
                picks.add(plugin.fetch_data().data["piece_id"])
        assert len(picks) >= 5

    def test_selection_random_draws_from_pool(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "random", "pool": ["heart"]}
        for _ in range(10):
            assert plugin.fetch_data().data["piece_id"] == "rainbow_heart"

    # ----------------------------------------------------------- pool filter

    def test_pool_filter_restricts_rotation(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {
            **sample_config, "selection": "rotate", "pool": ["pattern"],
            "rotate_seconds": 600,
        }
        seen = set()
        for window in range(50):
            with patch("plugins.pride.time.time", return_value=window * 600):
                seen.add(plugin.fetch_data().data["piece_id"])
        assert seen
        assert all(ART[pid]["category"] == "pattern" for pid in seen)

    def test_pool_empty_uses_all_pieces(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {
            **sample_config, "selection": "rotate", "pool": [],
            "rotate_seconds": 600,
        }
        seen = set()
        for window in range(len(ROTATION_ORDER)):
            with patch("plugins.pride.time.time", return_value=window * 600):
                seen.add(plugin.fetch_data().data["piece_id"])
        assert seen == set(ROTATION_ORDER)

    # ------------------------------------------------------ message overlay

    def test_message_overlays_on_center_row(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {
            **sample_config, "selection": "pick", "piece": "rainbow",
            "message": "Hello",
        }
        rows = plugin.fetch_data().data["art"].split("\n")
        center = rows[3]
        assert "HELLO" in center
        assert center.count("{green}") < 22

    def test_message_overlays_apply_to_both_sizes(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {
            **sample_config, "selection": "pick", "piece": "rainbow",
            "message": "HI",
        }
        result = plugin.fetch_data()
        assert "HI" in result.data["art"]
        assert "HI" in result.data["art_note"]

    # ---------------------------------------------------------- history mode

    def test_history_data_loads(self):
        history = _load_history()
        assert isinstance(history, list)
        assert len(history) > 20
        for entry in history:
            assert "date" in entry
            assert "text" in entry

    def test_history_picks_today(self, sample_manifest, sample_config):
        from datetime import datetime as real_dt

        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "mode": "history"}

        class _FakeDt:
            @classmethod
            def now(cls):
                return real_dt(2026, 6, 28, 12, 0, 0)

        with patch("plugins.pride.datetime", _FakeDt):
            result = plugin.fetch_data()
        assert result.available
        assert result.data["mode"] == "history"
        assert "STONEWALL" in result.data["art"].upper() or "1969" in result.data["art"]

    def test_history_publishes_both_sizes(self, sample_manifest, sample_config):
        from datetime import datetime as real_dt

        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "mode": "history"}

        class _FakeDt:
            @classmethod
            def now(cls):
                return real_dt(2026, 6, 28, 12, 0, 0)

        with patch("plugins.pride.datetime", _FakeDt):
            result = plugin.fetch_data()
        assert len(result.data["art"].split("\n")) == 6
        assert len(result.data["art_note"].split("\n")) == 3

    def test_history_fallback_when_no_entry(self, sample_manifest, sample_config):
        from datetime import datetime as real_dt

        history = _load_history()
        used_dates = {e["date"] for e in history}
        fallback_date = next(
            f"{m:02d}-{d:02d}"
            for m in range(1, 13)
            for d in (1, 5, 7, 11, 13)
            if f"{m:02d}-{d:02d}" not in used_dates
        )
        month, day = (int(p) for p in fallback_date.split("-"))

        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "mode": "history"}

        class _FakeDt:
            @classmethod
            def now(cls):
                return real_dt(2026, month, day, 12, 0, 0)

        with patch("plugins.pride.datetime", _FakeDt):
            result = plugin.fetch_data()
        assert result.available
        assert "HAPPY PRIDE" in result.data["art"]
        assert result.data["mode"] == "history"
