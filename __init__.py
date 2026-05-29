"""Pride plugin for FiestaBoard.

Renders Pride flags as full-screen color art on either the flagship (6x22) or
note (3x15) display, with optional custom message overlay and an "On This Day"
LGBTQ+ history mode backed by a bundled JSON dataset.
"""

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import json
import logging
import time

from src.plugins.base import PluginBase, PluginResult
from src.board_chars import BoardChars

logger = logging.getLogger(__name__)


# Board dimensions per device type. Flagship is the canonical Vestaboard;
# note is the smaller "Vestaboard Note" variant.
DEVICE_DIMENSIONS: Dict[str, Tuple[int, int]] = {
    "flagship": (6, 22),
    "note": (3, 15),
}


# Single source of truth for tile color names. Keys match the {color} markers
# the FiestaBoard renderer expects when these grids are flattened to strings.
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


# Flag stripe definitions, top-to-bottom. The 8-tile board palette has no
# pink/brown/cyan, so several flags lean on the closest substitute:
#   pink     -> RED
#   magenta  -> VIOLET
#   gray     -> WHITE
#   cyan     -> BLUE
# These approximations are documented in the README.
FLAGS: Dict[str, Dict[str, Any]] = {
    "rainbow": {
        "name": "Rainbow",
        "tagline": "Love is love",
        "stripes": ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "VIOLET"],
    },
    "trans": {
        "name": "Trans",
        "tagline": "Trans rights",
        "stripes": ["BLUE", "WHITE", "RED", "WHITE", "BLUE"],
    },
    "bi": {
        "name": "Bisexual",
        "tagline": "Bi the way",
        "stripes": ["RED", "RED", "VIOLET", "BLUE", "BLUE"],
    },
    "pan": {
        "name": "Pansexual",
        "tagline": "Hearts not parts",
        "stripes": ["RED", "YELLOW", "BLUE"],
    },
    "lesbian": {
        "name": "Lesbian",
        "tagline": "Sapphic and proud",
        "stripes": ["ORANGE", "WHITE", "RED"],
    },
    "ace": {
        "name": "Asexual",
        "tagline": "Ace of hearts",
        "stripes": ["BLACK", "WHITE", "WHITE", "VIOLET"],
    },
    "nonbinary": {
        "name": "Non-binary",
        "tagline": "Beyond the binary",
        "stripes": ["YELLOW", "WHITE", "VIOLET", "BLACK"],
    },
    "progress": {
        "name": "Progress",
        "tagline": "All are welcome",
        "stripes": ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "VIOLET"],
    },
    "intersex": {
        "name": "Intersex",
        "tagline": "Bodies are not binary",
        "stripes": ["YELLOW", "YELLOW", "YELLOW", "YELLOW", "YELLOW", "YELLOW"],
    },
    "leather": {
        "name": "Leather",
        "tagline": "Kink is queer",
        "stripes": ["BLACK", "BLUE", "BLACK", "WHITE", "BLACK", "BLUE"],
    },
    "polyamory": {
        "name": "Polyamory",
        "tagline": "More to love",
        "stripes": ["BLUE", "RED", "BLACK"],
    },
    "genderfluid": {
        "name": "Genderfluid",
        "tagline": "Fluid and free",
        "stripes": ["RED", "WHITE", "VIOLET", "BLACK", "BLUE"],
    },
}

# Stable rotation order — drives the time-based "rotate" mode and the order
# flags appear in the settings UI.
ROTATION_ORDER: List[str] = [
    "rainbow", "trans", "bi", "pan", "lesbian", "ace", "nonbinary",
    "progress", "intersex", "leather", "polyamory", "genderfluid",
]


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
    """Pride plugin: rotating Pride flags and LGBTQ+ history for the board."""

    @property
    def plugin_id(self) -> str:
        return "pride"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []

        mode = config.get("mode", "flag")
        if mode not in ("flag", "history"):
            errors.append("Mode must be 'flag' or 'history'")

        flag = config.get("flag", "rotate")
        if flag != "rotate" and flag not in FLAGS:
            errors.append(f"Unknown flag '{flag}'")

        device_type = config.get("device_type", "flagship")
        if device_type not in DEVICE_DIMENSIONS:
            errors.append("Device type must be 'flagship' or 'note'")

        rotate_seconds = config.get("rotate_seconds", 600)
        if not isinstance(rotate_seconds, int) or rotate_seconds < 60:
            errors.append("Rotation interval must be at least 60 seconds")

        refresh_seconds = config.get("refresh_seconds", 300)
        if not isinstance(refresh_seconds, int) or refresh_seconds < 60:
            errors.append("Refresh interval must be at least 60 seconds")

        message = config.get("message", "") or ""
        if len(message) > 22:
            errors.append("Message must be 22 characters or fewer")

        return errors

    def fetch_data(self) -> PluginResult:
        try:
            mode = self.config.get("mode", "flag")
            device_type = self.config.get("device_type", "flagship")
            if device_type not in DEVICE_DIMENSIONS:
                device_type = "flagship"

            rows, cols = DEVICE_DIMENSIONS[device_type]

            if mode == "history":
                return self._render_history(rows, cols)
            return self._render_flag_mode(rows, cols)
        except Exception as exc:
            logger.exception("Error rendering Pride plugin")
            return PluginResult(available=False, error=str(exc))

    def get_formatted_display(self) -> Optional[List[str]]:
        """Return the active art as a list of color-marker rows."""
        result = self.get_data()
        if not result.available or not result.data:
            return None
        art = result.data.get("art", "")
        return art.split("\n") if art else None

    # ------------------------------------------------------------------ flag

    def _render_flag_mode(self, rows: int, cols: int) -> PluginResult:
        flag_id = self._pick_flag()
        flag = FLAGS[flag_id]

        grid = self._stripes_to_grid(flag["stripes"], rows, cols)

        message = (self.config.get("message") or "").strip().upper()
        if message:
            self._overlay_message(grid, message, rows, cols)

        art = self._grid_to_string(grid)
        return PluginResult(
            available=True,
            data={
                "art": art,
                "flag_name": flag["name"],
                "tagline": flag["tagline"],
                "mode": "flag",
                "history_year": "",
                "history_text": "",
            },
        )

    def _pick_flag(self) -> str:
        flag = self.config.get("flag", "rotate")
        if flag in FLAGS:
            return flag

        rotate_seconds = self.config.get("rotate_seconds", 600)
        if not isinstance(rotate_seconds, int) or rotate_seconds < 60:
            rotate_seconds = 600
        idx = int(time.time() // rotate_seconds) % len(ROTATION_ORDER)
        return ROTATION_ORDER[idx]

    @staticmethod
    def _stripes_to_grid(stripes: List[str], rows: int, cols: int) -> List[List[int]]:
        """Distribute stripe colors evenly across the available rows.

        When ``len(stripes) != rows`` we use proportional integer mapping so
        e.g. 3 stripes on a 6-row board become two rows per stripe; 5 stripes
        on a 6-row board produce a 2-1-1-1-1 split with the wider band on top.
        """
        n_stripes = len(stripes)
        grid: List[List[int]] = []
        for r in range(rows):
            stripe_idx = (r * n_stripes) // rows
            color = _COLOR_CODE[stripes[stripe_idx]]
            grid.append([color] * cols)
        return grid

    @staticmethod
    def _overlay_message(grid: List[List[int]], message: str, rows: int, cols: int) -> None:
        """Center ``message`` horizontally on the middle row of ``grid``.

        Letters take over their tile entirely — the board renders them in the
        natural flap typography rather than blending with the background color.
        """
        text = message[:cols]
        row_idx = rows // 2
        start = (cols - len(text)) // 2
        for i, ch in enumerate(text):
            code = PridePlugin._char_to_code(ch)
            if code is not None:
                grid[row_idx][start + i] = code

    @staticmethod
    def _char_to_code(ch: str) -> Optional[int]:
        """Convert a single ASCII character to its board tile code.

        Returns None for characters the board can't render so the caller can
        fall back to the underlying tile color.
        """
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

    # --------------------------------------------------------------- history

    def _render_history(self, rows: int, cols: int) -> PluginResult:
        history = _load_history()
        today = datetime.now().strftime("%m-%d")
        entry = next((e for e in history if e.get("date") == today), None)

        rainbow_stripes = FLAGS["rainbow"]["stripes"]
        if entry is None:
            grid = self._stripes_to_grid(rainbow_stripes, rows, cols)
            self._overlay_message(grid, "HAPPY PRIDE", rows, cols)
            art = self._grid_to_string(grid)
            return PluginResult(
                available=True,
                data={
                    "art": art,
                    "flag_name": "Rainbow",
                    "tagline": "Love is love",
                    "mode": "history",
                    "history_year": "",
                    "history_text": "",
                },
            )

        grid: List[List[int]] = [self._rainbow_top_row(cols)]
        year = str(entry.get("year", ""))
        text = entry.get("text", "").upper()
        body = f"{year} {text}" if year else text
        wrapped = self._wrap(body, cols, rows - 1)
        for line in wrapped:
            grid.append(self._text_row(line, cols))
        while len(grid) < rows:
            grid.append([BoardChars.SPACE] * cols)

        art = self._grid_to_string(grid)
        return PluginResult(
            available=True,
            data={
                "art": art,
                "flag_name": "Rainbow",
                "tagline": "On this day",
                "mode": "history",
                "history_year": year,
                "history_text": entry.get("text", ""),
            },
        )

    @staticmethod
    def _rainbow_top_row(cols: int) -> List[int]:
        spectrum = ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "VIOLET"]
        row: List[int] = []
        for c in range(cols):
            color_idx = (c * len(spectrum)) // cols
            row.append(_COLOR_CODE[spectrum[color_idx]])
        return row

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
        """Word-wrap ``text`` to ``width`` columns, capping at ``max_lines``."""
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


# Export the plugin class
Plugin = PridePlugin
