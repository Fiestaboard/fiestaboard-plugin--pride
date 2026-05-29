# Pride Plugin 🏳️‍🌈

Rotating Pride flags, LGBTQ+ history, and rainbow color art for your FiestaBoard split-flap display.

![Pride Display](./docs/board-display.png)

**→ [Setup Guide](./docs/SETUP.md)** — Configuration and modes

## Overview

The Pride plugin renders Pride flags as full-screen color art on the 8-tile board palette. It ships with twelve flags, a deterministic rotation mode, a custom message overlay, and an "On This Day" LGBTQ+ history mode backed by a bundled dataset of dated events. It works on both the flagship (6×22) and note (3×15) displays.

## Features

- **12 Pride flags**: Rainbow, Trans, Bi, Pan, Lesbian, Ace, Non-binary, Progress, Intersex, Leather, Polyamory, Genderfluid
- **Rotation mode**: cycles flags on a deterministic interval — same time, same flag, no extra state
- **Custom message overlay**: drop a 22-character message centered over the active flag
- **On This Day**: ~50 bundled LGBTQ+ history events; renders a rainbow banner with the day's fact
- **Dual display**: works on the flagship (6×22) and note (3×15) board variants
- **Pure local rendering**: no network calls, no API keys

## Color Approximations

The Vestaboard's 8-tile palette has no pink, brown, or cyan, so several flags lean on the nearest substitute:

| Real color | Tile used |
|-----------|-----------|
| Pink      | `{red}`   |
| Magenta   | `{violet}`|
| Gray      | `{white}` |
| Cyan      | `{blue}`  |
| Brown     | (omitted for now — Progress chevron lands in v0.2) |

The README and SETUP guide call these approximations out so you know what to expect. A future release will add overlay glyphs (Progress chevron, Intersex ring, Leather heart, Poly infinity).

## Template Variables

```
{{pride.art}}            # Full-board color art for the active flag/banner
{{pride.flag_name}}      # e.g. "Rainbow", "Trans", "Bisexual"
{{pride.tagline}}        # e.g. "Love is love"
{{pride.mode}}           # Current mode: "flag" or "history"
{{pride.history_year}}   # Year of today's history entry (history mode)
{{pride.history_text}}   # Text of today's history entry (history mode)
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `enabled` | `false` | Master switch |
| `mode` | `flag` | `flag` or `history` |
| `flag` | `rotate` | One of the 12 flag IDs, or `rotate` |
| `device_type` | `flagship` | `flagship` (6×22) or `note` (3×15) |
| `rotate_seconds` | `600` | Rotation interval when `flag = rotate` |
| `message` | `""` | Optional centered overlay (≤ 22 chars) |
| `refresh_seconds` | `300` | How often to recompute the rendered art |

Environment variable equivalents (prefix `PRIDE_*`) are listed in `manifest.json`.

## Example Templates

**Full-screen rotating flag:**

```
{{pride.art}}
```

**Today in LGBTQ+ history:**

```
{{pride.art}}
```

(With `mode = history`, the top row is a rainbow stripe and the body is the year + event.)

**Greeting overlay:**

```
Set message to "HAPPY PRIDE 2026" and the active flag renders with that line
centered on the middle row.
```

## Testing

```bash
python -m pytest tests/ -v
```

Tests cover every flag, both display sizes, rotation determinism, message overlay, and the history lookup.

## Roadmap

- v0.2 — Progress chevron, Intersex ring, Leather heart, Poly infinity overlays
- v0.3 — Pride parade countdown by city, awareness-day auto-flag matching, LGBTQ+ icon quote-of-the-day
- v0.4 — Rainbow gradient text helper, animated shimmer mode, webhook "celebrate" trigger

See the implementation plan in `docs/SETUP.md` for the full creative roadmap.

## License

MIT — see [LICENSE](./LICENSE).
