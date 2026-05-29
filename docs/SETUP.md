# Pride Plugin Setup Guide

The Pride plugin renders Pride flags, color patterns, hearts, and an LGBTQ+ history banner as full-screen color art. This guide walks through configuration, the four selection modes, and pool filtering.

## Overview

**What it does:**

- Renders 21 art pieces: 12 flags, 3 vertical-stripe variants, 4 patterns (including a slowly-evolving "alive" sparkle), 1 rainbow heart, 1 equality symbol
- Picks pieces explicitly, on a rotation timer, deterministically per day, or randomly
- Optionally restricts the candidate pool to flags / patterns / hearts / symbols
- Overlays a 22-character message centered on the active piece
- Surfaces an "On This Day" LGBTQ+ history fact when in history mode
- Publishes both flagship (6×22) and note (3×15) renders every fetch, as separate template variables — no device setting required

**Prerequisites:**

- ✅ FiestaBoard `>=2.10.0`
- ✅ Nothing else — no API keys, no location, no network

## Quick Setup

### 1. Enable Pride

**Via Web UI (Recommended):**

1. Open the **Integrations** page.
2. Find the **Pride** card.
3. Toggle **Enabled** on.
4. Pick a **Mode** (`art` or `history`).
5. Pick a **Selection** (`pick`, `rotate`, `daily`, `random`).
6. If selection is `pick`, choose a **Piece**.
7. Save.

**Via Environment Variables:**

```bash
PRIDE_ENABLED=true
PRIDE_MODE=art
PRIDE_SELECTION=rotate
PRIDE_PIECE=rainbow
PRIDE_ROTATE_SECONDS=600
PRIDE_MESSAGE=""
PRIDE_REFRESH_SECONDS=300
```

### 2. Choose a Piece (or let the plugin choose)

| Piece ID | Display name | Category |
|---------|--------------|----------|
| `rainbow` | Rainbow | flag |
| `trans` | Trans | flag |
| `bi` | Bisexual | flag |
| `pan` | Pansexual | flag |
| `lesbian` | Lesbian | flag |
| `ace` | Asexual | flag |
| `nonbinary` | Non-binary | flag |
| `progress` | Progress | flag |
| `intersex` | Intersex | flag |
| `leather` | Leather | flag |
| `polyamory` | Polyamory | flag |
| `genderfluid` | Genderfluid | flag |
| `rainbow_columns` | Rainbow Columns | pattern |
| `trans_columns` | Trans Columns | pattern |
| `bi_columns` | Bi Columns | pattern |
| `rainbow_diagonal` | Rainbow Diagonal | pattern |
| `rainbow_checker` | Rainbow Checker | pattern |
| `rainbow_arc` | Rainbow Arc | pattern |
| `rainbow_sparkle` | Rainbow Sparkle | pattern |
| `rainbow_heart` | Rainbow Heart | heart |
| `equality` | Equality | symbol |

### 3. Pick a Selection Mode

- **`pick`** — render the exact piece you chose. No timer.
- **`rotate`** — cycle through the pool every `rotate_seconds`. Deterministic from the wall clock — same time, same piece, no extra state.
- **`daily`** — hash today's date into a piece. Same piece all day, different piece tomorrow.
- **`random`** — re-roll each fetch.

### 4. Filter the Pool (Optional)

The `pool` setting is a list of categories (`flag`, `pattern`, `heart`, `symbol`) and applies to rotate/daily/random. Examples:

- `["flag"]` — only the 12 stripe flags rotate
- `["pattern"]` — only color patterns (great if you want abstract art only)
- `["heart", "symbol"]` — only the heart and equality sign
- `[]` (empty) — every piece is in the pool

### 5. The Alive Rainbow Sparkle

`rainbow_sparkle` is special: at any moment, the visible state is the most recent ~26 mutations (≈ tile density). Each mutation is derived from a frame number `frame = wall_clock // 30`, so:

- One tile changes per 30 seconds
- Old sparkles slowly fade off as new ones appear
- Two boards in the same room stay perfectly in sync
- Restarting the plugin doesn't reset the pattern — it picks up wherever the clock is

To see it evolve smoothly, set `refresh_seconds` to `30` (the minimum the manifest allows). At the default `300` the sparkle will jump by 10 mutations between refreshes — still pretty, but less alive.

### 6. (Optional) Add a Custom Message

Set `message` to any string up to 22 characters. It's uppercased and centered on the middle row of whichever piece is active.

### 7. (Optional) Switch to History Mode

Set `mode = history`. The plugin will:

1. Look up today's date in `data/history.json`.
2. If an event matches, render a rainbow stripe on the top row and wrap the year + event text across the remaining rows.
3. If nothing matches, fall back to a rainbow flag with `HAPPY PRIDE` overlaid.

History mode also exposes `{{pride.history_year}}` and `{{pride.history_text}}` so you can compose your own layouts in other templates.

## Using Pride in Templates

The default templates already do the right thing — flagship demos use `{{pride.art}}`, note demos use `{{pride.art_note}}`. To pair the piece with its metadata:

```
{{pride.piece_name}}
{{pride.tagline}}
{{pride.art}}
```

For history mode:

```
ON THIS DAY {{pride.history_year}}
{{pride.history_text}}
```

## Troubleshooting

**The piece never changes.**

Make sure `selection` is set to something other than `pick`, and that `refresh_seconds` ≤ `rotate_seconds`. The framework only re-fetches every `refresh_seconds`.

**The sparkle looks frozen.**

Drop `refresh_seconds` to `30`. The alive sparkle mutates once per 30 seconds — if the framework only re-renders every 300 seconds, you'll see a 10-mutation jump every five minutes instead of a smooth crawl.

**The message is cut off.**

`message` is capped at 22 characters. Longer values are truncated.

**No history shows up.**

History mode falls back to a `HAPPY PRIDE` banner when today's date is missing from `data/history.json`. To add your own entries, edit that file — each entry is `{"date": "MM-DD", "year": 1969, "text": "..."}`.

**Pink looks red. Cyan looks blue.**

The Vestaboard palette has 8 tiles (red, orange, yellow, green, blue, violet, white, black). The plugin uses the nearest substitute for off-palette colors. The README lists the substitutions explicitly.

## Testing Locally

```bash
python -m pytest tests/ -v
```

The test suite covers every piece at both display sizes, all four selection modes, pool filtering, message overlay, alive-sparkle behavior, and the history lookup. No network is touched.
