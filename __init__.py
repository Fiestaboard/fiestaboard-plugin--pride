"""Pride plugin for FiestaBoard.

Renders Pride flags, color patterns, hearts, and symbols as full-screen color
art. Every piece is drawn to the dimensions of the board actually being
rendered on — a Flagship (22x6), a Note (15x3), or a note array of any size
from 15x3 to 120x24, which is also what a FiestaPanel is. There is one `art`
variable and it is always exactly board-sized, so a page template does not
have to know which board it will land on.

Selection modes: pick (explicit piece), rotate (time-based cycling), daily
(deterministic per calendar day), random (re-rolled each fetch). An optional
category pool restricts the candidates to one or more of: flag, pattern, heart,
symbol.

Also supports an "On This Day" LGBTQ+ history mode backed by a bundled JSON
dataset.
"""

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import hashlib
import json
import logging
import random
import time

from src.plugins.base import PluginBase, PluginResult
from src.board_chars import BoardChars
from src.devices import MAX_NOTES_PER_AXIS, NOTE_COLS, get_dimensions

logger = logging.getLogger(__name__)


# Fallback geometry for a render with no board bound (unit tests, legacy
# callers). Taken from core rather than retyped: this plugin holds no board
# dimensions of its own, and there is no user-facing board-size setting —
# the platform knows which board it is rendering on.
_FLAGSHIP = get_dimensions("flagship")
DEFAULT_ROWS: int = _FLAGSHIP.rows
DEFAULT_COLS: int = _FLAGSHIP.cols

# Widest board a user can own: an 8-note-wide array. Used only to bound the
# custom message setting, which the board itself then reflows.
MAX_BOARD_COLS: int = NOTE_COLS * MAX_NOTES_PER_AXIS

# Spectrum used by patterns that don't have a specific stripe definition.
SPECTRUM: List[str] = ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "VIOLET"]

# How often the "alive" sparkle pattern mutates one tile.
SPARKLE_MUTATION_SECONDS = 30

# Columns per row of heart. Board tiles are far taller than they are wide, so
# a heart that reads as a heart is several times wider than it is tall; this
# is the proportion of the shipped flagship artwork (22 cols x 6 rows).
HEART_ASPECT: float = 11.0 / 3.0

# The heart as a scale-free outline: control points down its height, each
# giving the outer span and the notch between the two lobes as *fractions*
# of the artwork box. Unitless, so the same shape draws at any size — these
# numbers reproduce the shipped 22x6 artwork exactly when interpolated onto
# six rows, and keep both the lobes and the point at three rows or twenty.
# (An implicit heart curve was tried first; its notch is ~8% of the height,
# which disappears entirely below about twenty rows and renders as a blob.)
HEART_PROFILE: Tuple[Tuple[float, float, float, float, float], ...] = (
    # height fraction, outer left, outer right, notch left, notch right
    (0.00, 0.18, 0.82, 0.32, 0.68),
    (0.20, 0.14, 0.86, 0.36, 0.64),
    (0.40, 0.09, 0.91, 0.50, 0.50),  # lobes merged from here down
    (0.60, 0.14, 0.86, 0.50, 0.50),
    (0.80, 0.23, 0.77, 0.50, 0.50),
    (1.00, 0.32, 0.68, 0.50, 0.50),
)


_COLOR_CODE: Dict[str, int] = {
    "RED": BoardChars.RED,
    "ORANGE": BoardChars.ORANGE,
    "YELLOW": BoardChars.YELLOW,
    "GREEN": BoardChars.GREEN,
    "BLUE": BoardChars.BLUE,
    "VIOLET": BoardChars.VIOLET,
    "WHITE": BoardChars.WHITE,
    "BLACK": BoardChars.BLACK,
}

_COLOR_MARKER: Dict[int, str] = {
    BoardChars.RED: "{red}",
    BoardChars.ORANGE: "{orange}",
    BoardChars.YELLOW: "{yellow}",
    BoardChars.GREEN: "{green}",
    BoardChars.BLUE: "{blue}",
    BoardChars.VIOLET: "{violet}",
    BoardChars.WHITE: "{white}",
    BoardChars.BLACK: "{black}",
}


# Art catalog. Each entry is one renderable piece; `kind` selects the renderer.
# `stripes` is consumed by the `hstripes` and `vstripes` kinds.
ART: Dict[str, Dict[str, Any]] = {
    # -- 12 stripe flags ----------------------------------------------------
    "rainbow": {
        "name": "Rainbow",
        "tagline": "Love is love",
        "category": "flag",
        "kind": "hstripes",
        "stripes": ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "VIOLET"],
    },
    "trans": {
        "name": "Trans",
        "tagline": "Trans rights",
        "category": "flag",
        "kind": "hstripes",
        "stripes": ["BLUE", "WHITE", "RED", "WHITE", "BLUE"],
    },
    "bi": {
        "name": "Bisexual",
        "tagline": "Bi the way",
        "category": "flag",
        "kind": "hstripes",
        "stripes": ["RED", "RED", "VIOLET", "BLUE", "BLUE"],
    },
    "pan": {
        "name": "Pansexual",
        "tagline": "Hearts not parts",
        "category": "flag",
        "kind": "hstripes",
        "stripes": ["RED", "YELLOW", "BLUE"],
    },
    "lesbian": {
        "name": "Lesbian",
        "tagline": "Sapphic and proud",
        "category": "flag",
        "kind": "hstripes",
        "stripes": ["ORANGE", "WHITE", "RED"],
    },
    "ace": {
        "name": "Asexual",
        "tagline": "Ace of hearts",
        "category": "flag",
        "kind": "hstripes",
        "stripes": ["BLACK", "WHITE", "WHITE", "VIOLET"],
    },
    "nonbinary": {
        "name": "Non-binary",
        "tagline": "Beyond the binary",
        "category": "flag",
        "kind": "hstripes",
        "stripes": ["YELLOW", "WHITE", "VIOLET", "BLACK"],
    },
    "progress": {
        "name": "Progress",
        "tagline": "All are welcome",
        "category": "flag",
        "kind": "hstripes",
        "stripes": ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "VIOLET"],
    },
    "intersex": {
        "name": "Intersex",
        "tagline": "Bodies are not binary",
        "category": "flag",
        "kind": "hstripes",
        "stripes": ["YELLOW", "YELLOW", "YELLOW", "YELLOW", "YELLOW", "YELLOW"],
    },
    "leather": {
        "name": "Leather",
        "tagline": "Kink is queer",
        "category": "flag",
        "kind": "hstripes",
        "stripes": ["BLACK", "BLUE", "BLACK", "WHITE", "BLACK", "BLUE"],
    },
    "polyamory": {
        "name": "Polyamory",
        "tagline": "More to love",
        "category": "flag",
        "kind": "hstripes",
        "stripes": ["BLUE", "RED", "BLACK"],
    },
    "genderfluid": {
        "name": "Genderfluid",
        "tagline": "Fluid and free",
        "category": "flag",
        "kind": "hstripes",
        "stripes": ["RED", "WHITE", "VIOLET", "BLACK", "BLUE"],
    },
    "ally": {
        "name": "Ally",
        "tagline": "Stand together",
        "category": "flag",
        "kind": "ally",
    },
    # -- vertical stripe variants ------------------------------------------
    "rainbow_columns": {
        "name": "Rainbow Columns",
        "tagline": "Standing tall",
        "category": "pattern",
        "kind": "vstripes",
        "stripes": ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "VIOLET"],
    },
    "trans_columns": {
        "name": "Trans Columns",
        "tagline": "Stand with trans",
        "category": "pattern",
        "kind": "vstripes",
        "stripes": ["BLUE", "WHITE", "RED", "WHITE", "BLUE"],
    },
    "bi_columns": {
        "name": "Bi Columns",
        "tagline": "Both and",
        "category": "pattern",
        "kind": "vstripes",
        "stripes": ["RED", "RED", "VIOLET", "BLUE", "BLUE"],
    },
    # -- patterns -----------------------------------------------------------
    "rainbow_diagonal": {
        "name": "Rainbow Diagonal",
        "tagline": "On the move",
        "category": "pattern",
        "kind": "diagonal",
    },
    "rainbow_checker": {
        "name": "Rainbow Checker",
        "tagline": "Mix it up",
        "category": "pattern",
        "kind": "checker",
    },
    "rainbow_arc": {
        "name": "Rainbow Arc",
        "tagline": "Over the rainbow",
        "category": "pattern",
        "kind": "arc",
    },
    "rainbow_sparkle": {
        "name": "Rainbow Sparkle",
        "tagline": "Alive and slow",
        "category": "pattern",
        "kind": "sparkle",
    },
    # -- hearts -------------------------------------------------------------
    "rainbow_heart": {
        "name": "Rainbow Heart",
        "tagline": "Heart and soul",
        "category": "heart",
        "kind": "heart",
    },
    # -- symbols ------------------------------------------------------------
    "equality": {
        "name": "Equality",
        "tagline": "Equal rights",
        "category": "symbol",
        "kind": "equality",
    },
}

# Stable iteration order: flags first, then patterns, hearts, symbols. Drives
# rotation, daily picks, and the order pieces appear in the settings UI.
ROTATION_ORDER: List[str] = list(ART.keys())

# Categories the user can include in `pool`.
CATEGORIES: List[str] = ["flag", "pattern", "heart", "symbol"]

VALID_SELECTIONS = ("pick", "rotate", "daily", "random")


_HISTORY_CACHE: Optional[List[Dict[str, Any]]] = None


def _bands(n: int, extent: int) -> List[int]:
    """Map each of *extent* rows (or columns) onto one of *n* stripe indices.

    When ``extent >= n`` the stripes are divided proportionally and **every
    stripe gets at least one band**: the remainder is spread evenly across the
    sequence instead of being dropped off the end.

    When ``extent < n`` there are not enough bands to go round at all, so the
    stripes are sampled at their *centres*. Centre-sampling spreads the
    selection across the whole sequence; the floor-sampling this replaced
    (``stripes[(r * n) // rows]``) bunched it onto the front, which is how a
    six-stripe Leather flag came out as three identical BLACK rows.
    """
    if n <= 0 or extent <= 0:
        return []
    if extent >= n:
        edges = [round(k * extent / n) for k in range(n + 1)]
        out: List[int] = []
        for k in range(n):
            out.extend([k] * (edges[k + 1] - edges[k]))
        return out
    return [min(n - 1, int((i + 0.5) * n / extent)) for i in range(extent)]


def _load_history() -> List[Dict[str, Any]]:
    """Load and cache the bundled LGBTQ+ history dataset."""
    global _HISTORY_CACHE
    if _HISTORY_CACHE is None:
        path = Path(__file__).parent / "data" / "history.json"
        with path.open("r", encoding="utf-8") as f:
            _HISTORY_CACHE = json.load(f)
    return _HISTORY_CACHE


class PridePlugin(PluginBase):
    """Pride plugin: Pride flags, color patterns, hearts, and LGBTQ+ history."""

    @property
    def plugin_id(self) -> str:
        return "pride"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []

        mode = config.get("mode", "art")
        if mode not in ("art", "history"):
            errors.append("Mode must be 'art' or 'history'")

        selection = config.get("selection", "rotate")
        if selection not in VALID_SELECTIONS:
            errors.append(
                f"Selection must be one of: {', '.join(VALID_SELECTIONS)}"
            )

        piece = config.get("piece") or ""
        if piece and piece not in ART:
            errors.append(f"Unknown piece '{piece}'")

        pool = config.get("pool") or []
        if not isinstance(pool, list):
            errors.append("Pool must be a list of category names")
        else:
            for cat in pool:
                if cat not in CATEGORIES:
                    errors.append(f"Unknown category '{cat}'")

        rotate_value = config.get("rotate_seconds", 600)
        if not isinstance(rotate_value, int) or rotate_value < 60:
            errors.append("rotate_seconds must be an integer >= 60")

        refresh_value = config.get("refresh_seconds", 300)
        if not isinstance(refresh_value, int) or refresh_value < 30:
            errors.append("refresh_seconds must be an integer >= 30")

        message = config.get("message", "") or ""
        if len(message) > MAX_BOARD_COLS:
            errors.append(
                f"Message must be {MAX_BOARD_COLS} characters or fewer"
            )

        return errors

    def fetch_data(self) -> PluginResult:
        try:
            mode = self.config.get("mode", "art")
            if mode == "history":
                return self._render_history()
            return self._render_art_mode()
        except Exception as exc:
            logger.exception("Error rendering Pride plugin")
            return PluginResult(available=False, error=str(exc))

    def get_formatted_display(self) -> Optional[List[str]]:
        """Return the art as a list of color-marker rows, sized to the board.

        ``self.board`` is forwarded explicitly: calling ``get_data()`` bare
        unbinds the live board and serves the board-agnostic cache slot, so
        a Note would have been handed the Flagship's frame.
        """
        result = self.get_data(self.board)
        if not result.available or not result.data:
            return None
        art = result.data.get("art", "")
        return art.split("\n") if art else None

    # ----------------------------------------------------------- geometry

    def _geometry(self) -> Tuple[int, int]:
        """Rows and columns of the board being rendered on.

        ``self.board`` is ``None`` outside a board-scoped render, where the
        documented contract is to assume a Flagship rather than crash.
        """
        board = self.board
        if board is None:
            return DEFAULT_ROWS, DEFAULT_COLS
        return max(1, int(board.rows)), max(1, int(board.cols))

    # ---------------------------------------------------- piece selection

    def _pool_ids(self) -> List[str]:
        pool = self.config.get("pool") or []
        if not pool:
            return list(ROTATION_ORDER)
        filtered = [pid for pid in ROTATION_ORDER if ART[pid]["category"] in pool]
        return filtered or list(ROTATION_ORDER)

    def _pick_piece(self) -> str:
        selection = self.config.get("selection", "rotate")
        piece = self.config.get("piece") or ""

        if selection == "pick" and piece in ART:
            return piece

        pool = self._pool_ids()

        if selection == "daily":
            day = datetime.now().strftime("%Y-%m-%d")
            digest = hashlib.sha1(day.encode("utf-8")).hexdigest()
            idx = int(digest[:8], 16) % len(pool)
            return pool[idx]

        if selection == "random":
            return random.choice(pool)

        rotate_seconds = self.config.get("rotate_seconds", 600)
        if not isinstance(rotate_seconds, int) or rotate_seconds < 60:
            rotate_seconds = 600
        idx = int(time.time() // rotate_seconds) % len(pool)
        return pool[idx]

    def _render_art_mode(self) -> PluginResult:
        piece_id = self._pick_piece()
        piece = ART[piece_id]
        rows, cols = self._geometry()
        art = self._render_art(piece, rows, cols)

        return PluginResult(
            available=True,
            formatted_lines=art.split("\n"),
            data={
                "art": art,
                "piece_id": piece_id,
                "piece_name": piece["name"],
                "piece_category": piece["category"],
                "tagline": piece["tagline"],
                "mode": "art",
                "history_year": "",
                "history_text": "",
            },
        )

    def _render_art(self, piece: Dict[str, Any], rows: int, cols: int) -> str:
        """Render *piece* at exactly ``rows`` x ``cols`` tiles."""
        grid = self._render_piece(piece, rows, cols)
        message = (self.config.get("message") or "").strip().upper()
        if message:
            self._overlay_message(grid, message, rows, cols)
        return self._grid_to_string(grid)

    # ------------------------------------------------------ piece renderers

    def _render_piece(self, piece: Dict[str, Any], rows: int, cols: int) -> List[List[int]]:
        kind = piece["kind"]
        if kind == "hstripes":
            return self._render_hstripes(piece["stripes"], rows, cols)
        if kind == "vstripes":
            return self._render_vstripes(piece["stripes"], rows, cols)
        if kind == "diagonal":
            return self._render_diagonal(rows, cols)
        if kind == "checker":
            return self._render_checker(rows, cols)
        if kind == "arc":
            return self._render_arc(rows, cols)
        if kind == "sparkle":
            return self._render_sparkle(rows, cols)
        if kind == "heart":
            return self._render_heart(rows, cols)
        if kind == "equality":
            return self._render_equality(rows, cols)
        if kind == "ally":
            return self._render_ally(rows, cols)
        raise ValueError(f"Unknown render kind: {kind}")

    @staticmethod
    def _render_hstripes(stripes: List[str], rows: int, cols: int) -> List[List[int]]:
        """Horizontal stripes sized to the board, keeping every stripe.

        Dropping a stripe changes which flag it is, so a flag is never
        resampled lossily. Where the board has at least as many rows as the
        flag has stripes, the rows are divided proportionally (see
        :func:`_bands`) and every stripe survives.

        Where it does not — a six-stripe Leather flag on a three-row Note —
        **no** horizontal layout can show them all, so the flag is turned a
        quarter turn and drawn as vertical bands, where the board's width has
        room for every stripe in order. A rotated flag is still recognisably
        that flag; the old floor-sample rendered Leather as three identical
        BLACK rows (a solid black board), Trans without its red centre, and
        Bisexual without the violet stripe that defines it.
        """
        n = len(stripes)
        if rows < n <= cols:
            return PridePlugin._render_vstripes(stripes, rows, cols)
        bands = _bands(n, rows)
        return [[_COLOR_CODE[stripes[bands[r]]]] * cols for r in range(rows)]

    @staticmethod
    def _render_vstripes(stripes: List[str], rows: int, cols: int) -> List[List[int]]:
        """Vertical stripes sized to the board, keeping every stripe."""
        n = len(stripes)
        bands = _bands(n, cols)
        col_colors = [_COLOR_CODE[stripes[bands[c]]] for c in range(cols)]
        return [list(col_colors) for _ in range(rows)]

    @staticmethod
    def _render_diagonal(rows: int, cols: int) -> List[List[int]]:
        """Diagonal rainbow sweep — stripe thickness chosen so all colors appear."""
        n = len(SPECTRUM)
        max_diag = (rows - 1) + (cols - 1)
        thickness = max(1, (max_diag + 1 + n - 1) // n)
        grid: List[List[int]] = []
        for r in range(rows):
            row = [
                _COLOR_CODE[SPECTRUM[((r + c) // thickness) % n]] for c in range(cols)
            ]
            grid.append(row)
        return grid

    @staticmethod
    def _render_checker(rows: int, cols: int) -> List[List[int]]:
        """2x2 colored blocks cycling through the spectrum."""
        n = len(SPECTRUM)
        grid: List[List[int]] = []
        for r in range(rows):
            row = [
                _COLOR_CODE[SPECTRUM[((r // 2) * 3 + (c // 2)) % n]]
                for c in range(cols)
            ]
            grid.append(row)
        return grid

    @staticmethod
    def _render_arc(rows: int, cols: int) -> List[List[int]]:
        """Rainbow pyramid: centered bands tapering from full width to half.

        The taper is proportional to the board's height, so the same shape
        appears at 22x6 and at 15x12. The previous version narrowed by a
        fixed two tiles per row, which assumed ``rows <= cols / 2``: on a
        tall-narrow 15x12 array it ran out of width at row 7 and the bottom
        five rows (42% of the board) came out solid black.
        """
        black = _COLOR_CODE["BLACK"]
        color_bands = _bands(len(SPECTRUM), rows)
        narrowest = max(1, cols // 2)
        span = max(1, rows - 1)
        grid: List[List[int]] = []
        for r in range(rows):
            color = _COLOR_CODE[SPECTRUM[color_bands[r]]]
            band_cols = round(cols - (cols - narrowest) * r / span)
            band_cols = max(1, min(cols, band_cols))
            left = (cols - band_cols) // 2
            row = [black] * left + [color] * band_cols
            row += [black] * (cols - len(row))
            grid.append(row)
        return grid

    @staticmethod
    def _render_sparkle(rows: int, cols: int) -> List[List[int]]:
        """Slowly-evolving sparkle field.

        At any moment, the visible state is the most recent N mutations, where
        N is the tile density. Each mutation is computed from a frame number
        ``frame = wall_clock // SPARKLE_MUTATION_SECONDS`` — so the pattern is
        deterministic from the clock (two boards stay in sync), one tile
        changes per window, and old sparkles slowly decay off the back end.
        """
        black = _COLOR_CODE["BLACK"]
        spectrum_codes = [_COLOR_CODE[c] for c in SPECTRUM]
        density = max(8, (rows * cols) // 5)

        frame = int(time.time() // SPARKLE_MUTATION_SECONDS)
        grid = [[black] * cols for _ in range(rows)]

        for f in range(max(0, frame - density + 1), frame + 1):
            rng = random.Random(f"sparkle:{rows}x{cols}:{f}")
            r = rng.randint(0, rows - 1)
            c = rng.randint(0, cols - 1)
            # Most mutations add a color; a small share fade a tile to black
            # so the field breathes instead of saturating.
            if rng.random() < 0.15:
                grid[r][c] = black
            else:
                grid[r][c] = rng.choice(spectrum_codes)

        return grid

    @staticmethod
    def _render_heart(rows: int, cols: int) -> List[List[int]]:
        """Rainbow heart drawn to fit the board, whatever its aspect ratio.

        The heart comes from :data:`HEART_PROFILE` — unitless fractions —
        rather than a bitmap, so there is no 22x6 literal to fall out of
        date. Its footprint is the largest box of the shipped flagship
        proportions (:data:`HEART_ASPECT`) that fits inside the board,
        centered on a black field. Sizing it is the
        aspect-ratio decision the old size threshold got wrong in both
        directions: ``rows >= 6 and cols >= 22`` handed a 24-row panel the
        6x22 bitmap and left the other 18 rows off, while a tall-narrow
        15x12 array fell to the note branch and got nine padded black rows.
        """
        black = _COLOR_CODE["BLACK"]
        heart_rows = max(1, min(rows, round(cols / HEART_ASPECT)))
        heart_cols = max(1, min(cols, round(heart_rows * HEART_ASPECT)))
        # A short, very wide board (a 120x3 array) can hold a full-height
        # heart several times over; repeating is a better use of the width
        # than one small heart adrift in a hundred black tiles.
        repeats = max(1, cols // (heart_cols + max(1, heart_cols // 2)))
        step = cols / repeats
        top = (rows - heart_rows) // 2
        color_bands = _bands(len(SPECTRUM), heart_rows)

        grid = [[black] * cols for _ in range(rows)]
        for hr in range(heart_rows):
            color = _COLOR_CODE[SPECTRUM[color_bands[hr]]]
            t = hr / (heart_rows - 1) if heart_rows > 1 else 0.5
            outer_l, outer_r, notch_l, notch_r = PridePlugin._heart_span(t)
            for hc in range(heart_cols):
                across = (hc + 0.5) / heart_cols
                if not (outer_l <= across <= outer_r) or notch_l < across < notch_r:
                    continue
                for i in range(repeats):
                    left = round(i * step + (step - heart_cols) / 2)
                    grid[top + hr][max(0, min(cols - 1, left + hc))] = color
        return grid

    @staticmethod
    def _heart_span(t: float) -> Tuple[float, float, float, float]:
        """Interpolate :data:`HEART_PROFILE` at height fraction *t*."""
        knots = HEART_PROFILE
        if t <= knots[0][0]:
            return knots[0][1:]
        if t >= knots[-1][0]:
            return knots[-1][1:]
        for lower, upper in zip(knots, knots[1:]):
            if lower[0] <= t <= upper[0]:
                spread = upper[0] - lower[0]
                f = (t - lower[0]) / spread if spread else 0.0
                return tuple(  # type: ignore[return-value]
                    a + (b - a) * f for a, b in zip(lower[1:], upper[1:])
                )
        return knots[-1][1:]

    @staticmethod
    def _render_equality(rows: int, cols: int) -> List[List[int]]:
        """HRC-style: two yellow horizontal bars on a blue field.

        Bar thickness scales with the board, so the symbol still reads as two
        bars on a 24-row panel instead of two hairlines.
        """
        blue = _COLOR_CODE["BLUE"]
        yellow = _COLOR_CODE["YELLOW"]
        thickness = max(1, rows // 6)
        bar_rows = set()
        for centre in (rows / 3.0, rows * 2 / 3.0):
            start = int(centre - thickness / 2.0 + 0.5)
            start = max(0, min(rows - thickness, start))
            bar_rows.update(range(start, start + thickness))

        margin = max(1, cols // 10)
        bar_width = max(1, cols - 2 * margin)
        grid: List[List[int]] = []
        for r in range(rows):
            if r in bar_rows:
                row = [blue] * margin + [yellow] * bar_width
                row += [blue] * (cols - len(row))
            else:
                row = [blue] * cols
            grid.append(row)
        return grid

    @staticmethod
    def _render_ally(rows: int, cols: int) -> List[List[int]]:
        """Straight Ally flag: alternating black/white stripes with a
        centered rainbow pyramid widening top-to-bottom.

        Both the spectrum bands and the pyramid width come from the board.
        The pyramid used to widen by a fixed two tiles per row, so on a
        120-column panel it stopped at a quarter of the width; the spectrum
        used to be sliced ``SPECTRUM[:rows]``, so a Note saw only red,
        orange and yellow and a 24-row panel saw violet eighteen times.
        """
        K = _COLOR_CODE["BLACK"]
        W = _COLOR_CODE["WHITE"]
        color_bands = _bands(len(SPECTRUM), rows)
        grid: List[List[int]] = []
        for r in range(rows):
            background = K if r % 2 == 0 else W
            row = [background] * cols
            band_width = max(1, min(cols, round(cols * (r + 1) / rows)))
            margin = (cols - band_width) // 2
            color = _COLOR_CODE[SPECTRUM[color_bands[r]]]
            for c in range(margin, margin + band_width):
                row[c] = color
            grid.append(row)
        return grid

    # --------------------------------------------------------- message overlay

    @staticmethod
    def _overlay_message(grid: List[List[int]], message: str, rows: int, cols: int) -> None:
        """Lay *message* over the art, centered, wrapping onto extra rows.

        The message is reflowed to the board's width rather than clipped at
        it, so a message that needs two lines on a Note gets two lines there
        and one on a wide panel.
        """
        lines = PridePlugin._wrap(message, cols, rows)
        if not lines:
            return
        top = max(0, (rows - len(lines) + 1) // 2)
        for offset, line in enumerate(lines):
            row_idx = top + offset
            if row_idx >= rows:
                break
            start = (cols - len(line)) // 2
            for i, ch in enumerate(line):
                code = PridePlugin._char_to_code(ch)
                if code is not None:
                    grid[row_idx][start + i] = code

    @staticmethod
    def _char_to_code(ch: str) -> Optional[int]:
        if ch == " ":
            return BoardChars.SPACE
        if "A" <= ch <= "Z":
            return ord(ch) - ord("A") + 1
        if "1" <= ch <= "9":
            return ord(ch) - ord("1") + 27
        if ch == "0":
            return 36
        punctuation = {
            "!": 37, "@": 38, "#": 39, "$": 40, "(": 41, ")": 42,
            "-": 44, "+": 46, "&": 47, "=": 48, ";": 49, ":": 50,
            "'": 52, '"': 53, "%": 54, ",": 55, ".": 56, "/": 59,
            "?": 60,
        }
        return punctuation.get(ch)

    # ----------------------------------------------------------- history mode

    def _render_history(self) -> PluginResult:
        history = _load_history()
        today = datetime.now().strftime("%m-%d")
        entry = next((e for e in history if e.get("date") == today), None)

        rows, cols = self._geometry()
        art = self._render_history_art(rows, cols, entry)

        year = str(entry.get("year", "")) if entry else ""
        text = entry.get("text", "") if entry else ""

        return PluginResult(
            available=True,
            formatted_lines=art.split("\n"),
            data={
                "art": art,
                "piece_id": "history" if entry else "rainbow",
                "piece_name": "On This Day" if entry else "Rainbow",
                "piece_category": "history" if entry else "flag",
                "tagline": "On this day" if entry else "Love is love",
                "mode": "history",
                "history_year": year,
                "history_text": text,
            },
        )

    def _render_history_art(
        self, rows: int, cols: int, entry: Optional[Dict[str, Any]]
    ) -> str:
        """Today's history entry laid out for a ``rows`` x ``cols`` board.

        Rainbow bands frame a centered block of text. Both the band depth and
        the number of text lines come from the board, so the entry wraps into
        more lines on a taller board instead of being cut at five.
        """
        if entry is None:
            grid = self._render_hstripes(list(SPECTRUM), rows, cols)
            self._overlay_message(grid, "HAPPY PRIDE", rows, cols)
            return self._grid_to_string(grid)

        band = max(1, rows // 8)
        bottom_band = band if rows - 2 * band >= 2 else 0
        text_rows = max(0, rows - band - bottom_band)

        year = str(entry.get("year", ""))
        text = entry.get("text", "").upper()
        body = f"{year} {text}" if year else text
        wrapped = self._wrap(body, cols, text_rows)

        grid: List[List[int]] = [self._rainbow_row(cols) for _ in range(band)]
        lead = max(0, (text_rows - len(wrapped)) // 2)
        grid.extend([BoardChars.SPACE] * cols for _ in range(lead))
        for line in wrapped:
            grid.append(self._text_row(line, cols))
        while len(grid) < rows - bottom_band:
            grid.append([BoardChars.SPACE] * cols)
        grid.extend(self._rainbow_row(cols) for _ in range(bottom_band))
        return self._grid_to_string(grid[:rows])

    @staticmethod
    def _rainbow_row(cols: int) -> List[int]:
        """One full-width rainbow row, every spectrum color present."""
        bands = _bands(len(SPECTRUM), cols)
        return [_COLOR_CODE[SPECTRUM[bands[c]]] for c in range(cols)]

    @staticmethod
    def _text_row(text: str, cols: int) -> List[int]:
        row = [BoardChars.SPACE] * cols
        text = text[:cols]
        start = (cols - len(text)) // 2
        for i, ch in enumerate(text):
            code = PridePlugin._char_to_code(ch)
            if code is not None:
                row[start + i] = code
        return row

    @staticmethod
    def _wrap(text: str, width: int, max_lines: int) -> List[str]:
        words = text.split()
        lines: List[str] = []
        current = ""
        for word in words:
            if not current:
                current = word[:width]
            elif len(current) + 1 + len(word) <= width:
                current = f"{current} {word}"
            else:
                lines.append(current)
                current = word[:width]
                if len(lines) >= max_lines:
                    break
        if current and len(lines) < max_lines:
            lines.append(current)
        return lines[:max_lines]

    # ---------------------------------------------------------------- output

    @staticmethod
    def _grid_to_string(grid: List[List[int]]) -> str:
        lines: List[str] = []
        for row in grid:
            parts: List[str] = []
            for code in row:
                if code in _COLOR_MARKER:
                    parts.append(_COLOR_MARKER[code])
                elif code == BoardChars.SPACE:
                    parts.append(" ")
                else:
                    parts.append(PridePlugin._code_to_char(code))
            lines.append("".join(parts))
        return "\n".join(lines)

    @staticmethod
    def _code_to_char(code: int) -> str:
        if 1 <= code <= 26:
            return chr(ord("A") + code - 1)
        if 27 <= code <= 35:
            return str(code - 26)
        if code == 36:
            return "0"
        reverse_punct = {
            37: "!", 38: "@", 39: "#", 40: "$", 41: "(", 42: ")",
            44: "-", 46: "+", 47: "&", 48: "=", 49: ";", 50: ":",
            52: "'", 53: '"', 54: "%", 55: ",", 56: ".", 59: "/",
            60: "?",
        }
        return reverse_punct.get(code, " ")


Plugin = PridePlugin
