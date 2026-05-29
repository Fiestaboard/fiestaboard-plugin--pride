# Pride Plugin Setup Guide

The Pride plugin renders Pride flags as full-screen color art and surfaces a small set of LGBTQ+ history facts. This guide walks through configuration on both the flagship (6×22) and note (3×15) displays.

## Overview

**What it does:**

- Renders one of 12 Pride flags filling the entire board
- Optionally cycles through every flag on a deterministic interval
- Overlays a 22-character custom message centered on the active flag
- Switches into an "On This Day" mode that surfaces a year + event for today
- Works on both the flagship and note display sizes

**Prerequisites:**

- ✅ FiestaBoard `>=2.10.0`
- ✅ Nothing else — no API keys, no location, no network

## Quick Setup

### 1. Enable Pride

**Via Web UI (Recommended):**

1. Open the **Integrations** page.
2. Find the **Pride** card.
3. Toggle **Enabled** on.
4. Pick a **Mode** (`flag` or `history`).
5. Pick a **Flag** (or leave at `rotate` to cycle them all).
6. Save.

**Via Environment Variables:**

```bash
PRIDE_ENABLED=true
PRIDE_MODE=flag
PRIDE_FLAG=rotate
PRIDE_DEVICE_TYPE=flagship
PRIDE_ROTATE_SECONDS=600
PRIDE_MESSAGE=""
PRIDE_REFRESH_SECONDS=300
```

### 2. Choose a Flag

| Flag ID | Display name |
|---------|--------------|
| `rainbow` | Rainbow |
| `trans` | Trans |
| `bi` | Bisexual |
| `pan` | Pansexual |
| `lesbian` | Lesbian |
| `ace` | Asexual |
| `nonbinary` | Non-binary |
| `progress` | Progress (chevron lands in v0.2) |
| `intersex` | Intersex (ring lands in v0.2) |
| `leather` | Leather |
| `polyamory` | Polyamory |
| `genderfluid` | Genderfluid |
| `rotate` | Cycle through every flag |

When `flag` is set to `rotate`, the plugin picks based on the current time: `(time.time() // rotate_seconds) % 12`. That is fully deterministic — no state to persist, no surprises across restarts.

### 3. (Optional) Add a Custom Message

Set `message` to any string up to 22 characters. It will be uppercased and centered on the middle row of the active flag.

Examples:

- `HAPPY PRIDE 2026`
- `LOVE IS LOVE`
- `MARRY ME ALEX`

### 4. (Optional) Switch to History Mode

Set `mode = history`. The plugin will:

1. Look up today's date in `data/history.json`.
2. If an event matches, render a rainbow stripe on the top row and wrap the year + event text across the remaining rows.
3. If nothing matches, fall back to a rainbow flag with `HAPPY PRIDE` overlaid.

History mode also exposes `{{pride.history_year}}` and `{{pride.history_text}}` so you can compose your own layouts in other templates.

### 5. Pick a Device Type

The plugin supports two display sizes:

- `flagship` — 6 rows × 22 cols (the standard Vestaboard)
- `note` — 3 rows × 15 cols (the smaller Vestaboard Note)

The same flag data drives both — stripes are distributed proportionally across the available rows.

## Using Pride in Templates

The simplest template fills the whole board with the active flag:

```
{{pride.art}}
```

To pair the flag with its name and tagline:

```
{{pride.flag_name}}
{{pride.tagline}}
{{pride.art}}
```

For history mode, the art already contains a rainbow banner + event text, but you can also reference the parts directly:

```
ON THIS DAY {{pride.history_year}}
{{pride.history_text}}
```

## Troubleshooting

**The plugin renders a flat color.**

Some flags have very few stripes (`pan` has 3, `polyamory` has 3) and proportionally span multiple board rows each. That is by design.

**The message is cut off.**

`message` is capped at 22 characters. Longer values are truncated to fit the flagship width.

**No history shows up.**

History mode falls back to a `HAPPY PRIDE` banner when today's date is missing from `data/history.json`. To add your own entries, edit that file — each entry is `{"date": "MM-DD", "year": 1969, "text": "..."}`.

**Pink looks red. Cyan looks blue.**

The Vestaboard palette has 8 tiles (red, orange, yellow, green, blue, violet, white, black). The plugin uses the nearest substitute for off-palette colors. The README lists the substitutions explicitly.

## Testing Locally

```bash
python -m pytest tests/ -v
```

The test suite covers every flag, both display sizes, rotation determinism, message overlay, and the history lookup. No network is touched.
