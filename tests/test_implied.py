import numpy as np
import pandas as pd

from tsmc_adr_premium import implied_tsm_open


def snap(tsm_date, tw_date):
    return {
        "tsm_date": pd.Timestamp(tsm_date), "tsm_usd": 400.0,
        "tw_date": pd.Timestamp(tw_date), "tw_twd": 2400.0,
        "fx_date": pd.Timestamp(tw_date), "usdtwd": 32.0,
        "premium_pct": 0.0,
    }


def test_price_from_2330_fx_and_reference_premium():
    # Before the NYSE open: 2330 has today's close, TSM still has yesterday's.
    est = implied_tsm_open(snap("2026-10-29", "2026-10-30"), premium_ref=15.0)

    expected = 2400.0 * 1.15 * 5 / 32.0      # = 431.25
    assert est["price"] == expected
    assert est["change_pct"] == (expected / 400.0 - 1) * 100


def test_none_when_2330_is_not_newer_than_tsm():
    # After the NYSE close both are from the same day, so 2330 adds nothing new.
    assert implied_tsm_open(snap("2026-10-30", "2026-10-30"), premium_ref=15.0) is None
    # Taiwan holiday: 2330 older than TSM.
    assert implied_tsm_open(snap("2026-10-30", "2026-10-29"), premium_ref=15.0) is None


def test_none_without_reference_premium():
    assert implied_tsm_open(snap("2026-10-29", "2026-10-30"), premium_ref=np.nan) is None
