"""Unit tests for the Pride plugin."""

from unittest.mock import patch

import pytest

from src.devices import BoardContext
from src.text_to_board import count_tiles

from plugins.pride import (
    ART,
    CATEGORIES,
    MAX_BOARD_COLS,
    ROTATION_ORDER,
    SPARKLE_MUTATION_SECONDS,
    PridePlugin,
    _bands,
    _load_history,
)

# Every board shape the platform supports, as (rows, cols). A note array is
# anything from 15x3 to 120x24; the tall-narrow and wide-short entries are the
# two that break code assuming "not a Flagship means smaller".
BOARD_SHAPES = [
    ("flagship 22x6", 6, 22),
    ("note 15x3", 3, 15),
    ("panel 30x12", 12, 30),
    ("tall-narrow 15x12", 12, 15),
    ("wide-short 120x3", 3, 120),
    ("max array 120x24", 24, 120),
]


def board_for(rows: int, cols: int) -> BoardContext:
    """A BoardContext of the given size, as a note array where needed."""
    if (rows, cols) == (6, 22):
        return BoardContext.from_device_type("flagship")
    if (rows, cols) == (3, 15):
        return BoardContext.from_device_type("note")
    return BoardContext(device_type="note_array", rows=rows, cols=cols)


def render(plugin, rows, cols):
    """Render *plugin* for a board of this size, bypassing the per-board cache.

    Used where a test re-renders one instance with a changing config, which
    ``get_data`` would legitimately serve from its geometry-keyed cache.
    """
    with plugin._bound_board(board_for(rows, cols)):
        return plugin.fetch_data()


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
        errors = plugin.validate_config({"message": "x" * (MAX_BOARD_COLS + 1)})
        assert any("message" in e.lower() for e in errors)

    def test_validate_config_accepts_a_message_as_wide_as_the_widest_board(
        self, sample_manifest
    ):
        """The cap is the widest board a user can own, not the Flagship's 22."""
        plugin = PridePlugin(sample_manifest)
        assert plugin.validate_config({"message": "x" * MAX_BOARD_COLS}) == []

    # ----------------------------------------------- art is always board-sized

    @pytest.mark.parametrize("label,rows,cols", BOARD_SHAPES)
    def test_art_is_exactly_board_sized(
        self, sample_manifest, sample_config, label, rows, cols
    ):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": "rainbow"}
        result = plugin.get_data(board_for(rows, cols))
        assert result.available, label
        lines = result.data["art"].split("\n")
        assert len(lines) == rows, label
        assert all(count_tiles(line) == cols for line in lines), label
        # formatted_lines is the live whole-board path and must agree.
        assert result.formatted_lines == lines, label

    def test_art_defaults_to_flagship_with_no_board_bound(
        self, sample_manifest, sample_config
    ):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": "rainbow"}
        lines = plugin.get_data(None).data["art"].split("\n")
        assert len(lines) == 6
        assert all(count_tiles(line) == 22 for line in lines)

    def test_rainbow_flagship_has_six_distinct_color_rows(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": "rainbow"}
        result = plugin.fetch_data()
        rows = result.data["art"].split("\n")
        expected = ["{red}", "{orange}", "{yellow}", "{green}", "{blue}", "{violet}"]
        for row, marker in zip(rows, expected):
            assert row == marker * 22

    @pytest.mark.parametrize("label,rows,cols", BOARD_SHAPES)
    def test_every_piece_renders_at_every_board_shape(
        self, sample_manifest, sample_config, label, rows, cols
    ):
        plugin = PridePlugin(sample_manifest)
        # Pin the wall clock so the time-evolving pieces produce a stable result.
        with patch("plugins.pride.time.time", return_value=1_700_000_000):
            for piece_id in ART:
                plugin.config = {
                    **sample_config, "selection": "pick", "piece": piece_id,
                }
                result = render(plugin, rows, cols)
                assert result.available, (piece_id, label)
                lines = result.data["art"].split("\n")
                assert len(lines) == rows, (piece_id, label)
                assert all(count_tiles(line) == cols for line in lines), (
                    piece_id, label,
                )
                assert result.data["piece_id"] == piece_id
                assert result.data["piece_name"] == ART[piece_id]["name"]
                assert result.data["piece_category"] == ART[piece_id]["category"]

    # ---------------------------------------- no flag ever loses a stripe

    # Every flag whose stripe count exceeds a Note's three rows. These are the
    # flags the old nearest-neighbour downsample silently mangled: Leather came
    # out as three identical BLACK rows (a solid black board), Trans lost its
    # red centre, Bisexual lost the violet stripe that defines it.
    MULTI_STRIPE_FLAGS = [
        pid for pid, piece in ART.items()
        if piece.get("stripes") and len(piece["stripes"]) > 3
    ]

    @pytest.mark.parametrize("piece_id", MULTI_STRIPE_FLAGS)
    @pytest.mark.parametrize("label,rows,cols", BOARD_SHAPES)
    def test_every_stripe_survives_on_every_board(
        self, sample_manifest, sample_config, piece_id, label, rows, cols
    ):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": piece_id}
        art = render(plugin, rows, cols).data["art"]
        for color in set(ART[piece_id]["stripes"]):
            marker = "{%s}" % color.lower()
            assert marker in art, (
                f"{piece_id} lost its {color} stripe on {label}: "
                f"{len(set(ART[piece_id]['stripes']))} colors expected, "
                f"got {sorted(set(m for m in art.split()))[:1]}"
            )

    def test_leather_flag_is_not_a_solid_black_board_on_a_note(
        self, sample_manifest, sample_config
    ):
        """The specific regression: 6 stripes floor-sampled into 3 rows."""
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": "leather"}
        art = render(plugin, 3, 15).data["art"]
        assert art.count("{black}") < 45, art
        assert "{blue}" in art and "{white}" in art

    def test_bands_never_drop_a_stripe_when_there_is_room(self):
        for n in range(1, 9):
            for extent in range(n, 121):
                bands = _bands(n, extent)
                assert len(bands) == extent, (n, extent)
                assert set(bands) == set(range(n)), (n, extent)

    def test_bands_spread_the_selection_when_there_is_not_room(self):
        """Fewer bands than stripes: sample centres, not the front of the list."""
        assert _bands(6, 3) == [1, 3, 5]
        assert _bands(5, 2) == [1, 3]

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

    def test_ally_mixes_bw_stripes_with_rainbow_pyramid(self, sample_manifest, sample_config):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": "ally"}
        art = plugin.fetch_data().data["art"]
        # Background should contain both black and white stripes
        assert "{black}" in art
        assert "{white}" in art
        # Rainbow pyramid should contribute at least the apex (red) and base (violet)
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

    def test_sparkle_changes_across_windows(self, sample_manifest, sample_config):
        """Most consecutive 30s windows produce a visible change.

        Occasional windows are no-ops by coincidence — the new mutation lands
        on a saturated tile, or the dropped one was already masked by a later
        write within the window. That breathing rhythm is part of the design,
        so the contract is "mostly changes," not "always changes."
        """
        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "selection": "pick", "piece": "rainbow_sparkle"}
        bases = [1_700_000_000 + i * 97 for i in range(20)]
        changes = 0
        for base in bases:
            with patch("plugins.pride.time.time", return_value=base):
                first = plugin.fetch_data().data["art"]
            with patch("plugins.pride.time.time", return_value=base + SPARKLE_MUTATION_SECONDS):
                second = plugin.fetch_data().data["art"]
            if first != second:
                changes += 1
        assert changes >= len(bases) * 0.7

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
        # Pin to a window boundary so +599 stays inside the same window.
        base = (1_700_000_000 // 600) * 600
        with patch("plugins.pride.time.time", return_value=base):
            first = plugin.fetch_data().data["piece_id"]
        with patch("plugins.pride.time.time", return_value=base + 599):
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

    @pytest.mark.parametrize("label,rows,cols", BOARD_SHAPES)
    def test_message_overlays_on_every_board(
        self, sample_manifest, sample_config, label, rows, cols
    ):
        plugin = PridePlugin(sample_manifest)
        plugin.config = {
            **sample_config, "selection": "pick", "piece": "rainbow",
            "message": "HI",
        }
        assert "HI" in render(plugin, rows, cols).data["art"], label

    def test_long_message_reflows_onto_more_rows_on_a_narrow_board(
        self, sample_manifest, sample_config
    ):
        """A message too wide for the board wraps rather than being clipped."""
        plugin = PridePlugin(sample_manifest)
        plugin.config = {
            **sample_config, "selection": "pick", "piece": "rainbow",
            "message": "HAPPY PRIDE EVERYONE",
        }
        note_rows = render(plugin, 3, 15).data["art"].split("\n")
        with_text = [r for r in note_rows if "HAPPY" in r or "PRIDE" in r or "EVERYONE" in r]
        assert len(with_text) >= 2, note_rows
        # The same message fits on one row of a wide board.
        wide_rows = render(plugin, 3, 120).data["art"].split("\n")
        assert any("HAPPY PRIDE EVERYONE" in r for r in wide_rows), wide_rows

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

    @pytest.mark.parametrize("label,rows,cols", BOARD_SHAPES)
    def test_history_is_board_sized(
        self, sample_manifest, sample_config, label, rows, cols
    ):
        from datetime import datetime as real_dt

        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "mode": "history"}

        class _FakeDt:
            @classmethod
            def now(cls):
                return real_dt(2026, 6, 28, 12, 0, 0)

        with patch("plugins.pride.datetime", _FakeDt):
            result = render(plugin, rows, cols)
        lines = result.data["art"].split("\n")
        assert len(lines) == rows, label
        assert all(count_tiles(line) == cols for line in lines), label

    def test_history_wraps_into_more_lines_on_a_taller_board(
        self, sample_manifest, sample_config
    ):
        """A taller board shows more of the entry, not the same five lines."""
        from datetime import datetime as real_dt

        plugin = PridePlugin(sample_manifest)
        plugin.config = {**sample_config, "mode": "history"}

        class _FakeDt:
            @classmethod
            def now(cls):
                return real_dt(2026, 6, 28, 12, 0, 0)

        with patch("plugins.pride.datetime", _FakeDt):
            short = render(plugin, 3, 15).data["art"]
            tall = render(plugin, 24, 15).data["art"]
        assert len(tall.replace(" ", "")) > len(short.replace(" ", ""))

    # ------------------------------------------------- manifest is honest

    def test_manifest_max_lengths_cover_every_history_entry(self):
        import json
        from pathlib import Path

        manifest = json.loads(
            (Path(__file__).resolve().parent.parent / "manifest.json").read_text()
        )
        declared = manifest["max_lengths"]
        for entry in _load_history():
            assert len(entry.get("text", "")) <= declared["history_text"], entry
            assert len(str(entry.get("year", ""))) <= declared["history_year"], entry

    def test_manifest_max_lengths_cover_every_piece(self):
        import json
        from pathlib import Path

        manifest = json.loads(
            (Path(__file__).resolve().parent.parent / "manifest.json").read_text()
        )
        declared = manifest["max_lengths"]
        for piece_id, piece in ART.items():
            assert len(piece_id) <= declared["piece_id"], piece_id
            assert len(piece["name"]) <= declared["piece_name"], piece_id
            assert len(piece["tagline"]) <= declared["tagline"], piece_id
            assert len(piece["category"]) <= declared["piece_category"], piece_id

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
