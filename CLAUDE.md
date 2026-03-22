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

## Architecture

### Python (`tsmc_adr_premium.py`)

Linear pipeline:
1. `fetch_data(period)` — downloads TSM, 2330.TW, TWD=X from Yahoo Finance, inner-joins on date
2. `calculate_premium(df)` — computes premium %, 60-day MA, rolling stats
3. `print_stats(df)` — console output with signal (color-coded by σ from mean)
4. `save_csv(df)` — exports daily data
5. `plot_chart(df)` — matplotlib dual-panel chart (premium + 2330.TW price)

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
