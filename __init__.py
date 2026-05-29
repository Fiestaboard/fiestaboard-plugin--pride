"""Pride plugin for FiestaBoard.

Renders Pride flags, color patterns, hearts, and symbols as full-screen color
art. Every fetch publishes both flagship (6x22) and note (3x15) versions of the
active piece as separate template variables, so each demo's template picks the
size that fits its device — no per-device user setting needed.

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

logger = logging.getLogger(__name__)


# Board dimensions per device type. Used by the rendering passes, not exposed
# as a user setting — the demos array in manifest.json wires each device to
# the matching variable.
DEVICE_DIMENSIONS: Dict[str, Tuple[int, int]] = {
    "flagship": (6, 22),
    "note": (3, 15),
}

# Spectrum used by patterns that don't have a specific stripe definition.
SPECTRUM: List[str] = ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "VIOLET"]

# How often the "alive" sparkle pattern mutates one tile.
SPARKLE_MUTATION_SECONDS = 30


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
        if len(message) > 22:
            errors.append("Message must be 22 characters or fewer")

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
        """Return the flagship art as a list of color-marker rows."""
        result = self.get_data()
        if not result.available or not result.data:
            return None
        art = result.data.get("art", "")
        return art.split("\n") if art else None

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
        message = (self.config.get("message") or "").strip().upper()

        art_flagship = self._render_for_device(piece, "flagship", message)
        art_note = self._render_for_device(piece, "note", message)

        return PluginResult(
            available=True,
            data={
                "art": art_flagship,
                "art_note": art_note,
                "piece_id": piece_id,
                "piece_name": piece["name"],
                "piece_category": piece["category"],
                "tagline": piece["tagline"],
                "mode": "art",
                "history_year": "",
                "history_text": "",
            },
        )

    def _render_for_device(self, piece: Dict[str, Any], device: str, message: str) -> str:
        rows, cols = DEVICE_DIMENSIONS[device]
        grid = self._render_piece(piece, rows, cols)
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
        n = len(stripes)
        return [[_COLOR_CODE[stripes[(r * n) // rows]]] * cols for r in range(rows)]

    @staticmethod
    def _render_vstripes(stripes: List[str], rows: int, cols: int) -> List[List[int]]:
        n = len(stripes)
        col_colors = [_COLOR_CODE[stripes[(c * n) // cols]] for c in range(cols)]
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
        """Rainbow pyramid: each row a centered band, one tile narrower per side."""
        black = _COLOR_CODE["BLACK"]
        grid: List[List[int]] = []
        for r in range(rows):
            color = _COLOR_CODE[SPECTRUM[r % len(SPECTRUM)]]
            margin = r + 1
            band_cols = max(0, cols - 2 * margin)
            row = [black] * margin + [color] * band_cols + [black] * margin
            if len(row) > cols:
                row = row[:cols]
            while len(row) < cols:
                row.append(black)
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
        if rows >= 6 and cols >= 22:
            return PridePlugin._heart_flagship()
        return PridePlugin._heart_note(rows, cols)

    @staticmethod
    def _heart_flagship() -> List[List[int]]:
        """Six-row rainbow heart on black, centered in 22 cols."""
        K = _COLOR_CODE["BLACK"]
        R = _COLOR_CODE["RED"]
        O = _COLOR_CODE["ORANGE"]
        Y = _COLOR_CODE["YELLOW"]
        G = _COLOR_CODE["GREEN"]
        B = _COLOR_CODE["BLUE"]
        V = _COLOR_CODE["VIOLET"]
        return [
            [K, K, K, K, R, R, R, K, K, K, K, K, K, K, K, R, R, R, K, K, K, K],
            [K, K, K, O, O, O, O, O, K, K, K, K, K, K, O, O, O, O, O, K, K, K],
            [K, K, Y, Y, Y, Y, Y, Y, Y, Y, Y, Y, Y, Y, Y, Y, Y, Y, Y, Y, K, K],
            [K, K, K, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G, K, K, K],
            [K, K, K, K, K, B, B, B, B, B, B, B, B, B, B, B, B, K, K, K, K, K],
            [K, K, K, K, K, K, K, V, V, V, V, V, V, V, V, K, K, K, K, K, K, K],
        ]

    @staticmethod
    def _heart_note(rows: int, cols: int) -> List[List[int]]:
        """Compact tri-color heart for the 3x15 note display."""
        K = _COLOR_CODE["BLACK"]
        R = _COLOR_CODE["RED"]
        Y = _COLOR_CODE["YELLOW"]
        V = _COLOR_CODE["VIOLET"]
        heart_rows = [
            [K, R, R, K, R, R, K, K, K],
            [Y, Y, Y, Y, Y, Y, Y, K, K],
            [K, K, V, V, V, V, K, K, K],
        ]
        pad_left = max(0, (cols - 9) // 2)
        pad_right = max(0, cols - 9 - pad_left)
        framed = [
            ([K] * pad_left + row + [K] * pad_right)[:cols] for row in heart_rows
        ]
        if rows <= len(framed):
            return framed[:rows]
        while len(framed) < rows:
            framed.append([K] * cols)
        return framed

    @staticmethod
    def _render_equality(rows: int, cols: int) -> List[List[int]]:
        """HRC-style: two yellow horizontal bars on a blue field."""
        blue = _COLOR_CODE["BLUE"]
        yellow = _COLOR_CODE["YELLOW"]
        bar_rows = {rows // 3, (rows * 2) // 3}
        grid: List[List[int]] = []
        for r in range(rows):
            grid.append([yellow if r in bar_rows else blue] * cols)
        margin = max(1, cols // 10)
        for r in bar_rows:
            for c in range(margin):
                grid[r][c] = blue
                grid[r][cols - 1 - c] = blue
        return grid

    @staticmethod
    def _render_ally(rows: int, cols: int) -> List[List[int]]:
        """Straight Ally flag: alternating black/white stripes with a
        centered rainbow pyramid widening top-to-bottom."""
        K = _COLOR_CODE["BLACK"]
        W = _COLOR_CODE["WHITE"]
        # Choose enough spectrum bands for the available rows.
        bands = SPECTRUM[:rows] if rows <= len(SPECTRUM) else (
            SPECTRUM + [SPECTRUM[-1]] * (rows - len(SPECTRUM))
        )
        grid: List[List[int]] = []
        for r in range(rows):
            background = K if r % 2 == 0 else W
            row = [background] * cols
            # Pyramid widens by 2 tiles per row, narrowest on top.
            band_width = min(cols, 2 * (r + 1))
            margin = (cols - band_width) // 2
            color = _COLOR_CODE[bands[r]]
            for c in range(margin, margin + band_width):
                row[c] = color
            grid.append(row)
        return grid

    # --------------------------------------------------------- message overlay

    @staticmethod
    def _overlay_message(grid: List[List[int]], message: str, rows: int, cols: int) -> None:
        text = message[:cols]
        row_idx = rows // 2
        start = (cols - len(text)) // 2
        for i, ch in enumerate(text):
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

        art_flagship = self._render_history_for_device("flagship", entry)
        art_note = self._render_history_for_device("note", entry)

        year = str(entry.get("year", "")) if entry else ""
        text = entry.get("text", "") if entry else ""

        return PluginResult(
            available=True,
            data={
                "art": art_flagship,
                "art_note": art_note,
                "piece_id": "history" if entry else "rainbow",
                "piece_name": "On This Day" if entry else "Rainbow",
                "piece_category": "history" if entry else "flag",
                "tagline": "On this day" if entry else "Love is love",
                "mode": "history",
                "history_year": year,
                "history_text": text,
            },
        )

    def _render_history_for_device(self, device: str, entry: Optional[Dict[str, Any]]) -> str:
        rows, cols = DEVICE_DIMENSIONS[device]

        if entry is None:
            grid = self._render_hstripes(
                ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "VIOLET"], rows, cols
            )
            self._overlay_message(grid, "HAPPY PRIDE", rows, cols)
            return self._grid_to_string(grid)

        grid: List[List[int]] = [self._rainbow_top_row(cols)]
        year = str(entry.get("year", ""))
        text = entry.get("text", "").upper()
        body = f"{year} {text}" if year else text
        wrapped = self._wrap(body, cols, rows - 1)
        for line in wrapped:
            grid.append(self._text_row(line, cols))
        while len(grid) < rows:
            grid.append([BoardChars.SPACE] * cols)
        return self._grid_to_string(grid)

    @staticmethod
    def _rainbow_top_row(cols: int) -> List[int]:
        return [
            _COLOR_CODE[SPECTRUM[(c * len(SPECTRUM)) // cols]] for c in range(cols)
        ]

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
