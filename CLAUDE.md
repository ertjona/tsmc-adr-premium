# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TSMC ADR Premium Tracker — a financial analysis tool that monitors the price premium/discount of TSMC's NYSE ADR (TSM) vs. Taiwan Stock Exchange stock (2330.TW), accounting for the USD/TWD exchange rate.

**Formula**: `ADR Premium = (TSM_USD / 5 × USD/TWD − 2330_TWD) / 2330_TWD × 100%`
(1 TSM ADR = 5 shares of 2330.TW)

## Running the Python Script

```bash
# Activate virtual environment
source .venv/bin/activate

# Run with default 5 years of data
python tsmc_adr_premium.py

# Run with custom period (1y, 2y, 5y, 10y, max)
python tsmc_adr_premium.py 10y
```

Outputs: `tsmc_adr_premium.csv` and `tsmc_adr_premium.png`

Dependencies: `yfinance`, `pandas`, `matplotlib` (installed in `.venv/`)

Tests and lint (dev deps in `requirements-dev.txt`):

```bash
pytest
ruff check tsmc_adr_premium.py tests
```

## Architecture

### Python (`tsmc_adr_premium.py`)

Linear pipeline:
1. `fetch_data(period)` — downloads TSM, 2330.TW, TWD=X daily closes, patches the newest day from 5-minute bars via `fill_latest_close` (Yahoo's same-day daily Close is often NaN right after the close), inner-joins on date. Returns `(merged, closes)`.
2. `calculate_premium(df)` — computes premium %, 60-day MA, rolling stats
3. `latest_snapshot(tsm, tw, fx)` — pairs each market's latest close even when dates differ (before the NY open, 2330 is a day ahead of TSM). This is the "Now" value.
4. `print_stats(df, snap)` — console output with signal (color-coded by σ from mean)
5. `save_csv(df)` — exports daily data (date-aligned history only)
6. `plot_chart(df, snap)` — matplotlib dual-panel chart (premium + 2330.TW price); title shows each price's date

### GitHub Actions (`.github/workflows/update-data.yml`)

Runs twice per weekday so the PNG is fresh before each market opens: 23:30 UTC (07:30 Taipei, before TWSE opens) and 11:30 UTC (19:30 Taipei, before NYSE opens). Commits CSV + PNG directly to `main`.

### React (`tsmc_adr_premium_tracker.jsx`)

Standalone JSX component (no build system). Key sections:
- Real-time calculator with live premium from manual price inputs
- SVG-based interactive chart with hover tooltips
- CSV import (paste output from Python script); auto-resamples to monthly if >200 rows
- Hardcoded sample data (2020–2026) for demonstration

The component uses `useState`/`useMemo`/`useCallback` only — no external dependencies beyond React.

## Key Constants

- ADR ratio: `5` (hardcoded in both files — 1 TSM ADR = 5 Taiwan shares)
- Signal thresholds: ±0.5σ (green), ±1.5σ (yellow/red)
- Chart resampling threshold: 200 data points → monthly
