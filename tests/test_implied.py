import numpy as np
import pandas as pd
import pytest

from tsmc_adr_premium import implied_tsm_open


def make_snap(tsm_date, tw_date):
    return {
        "tsm_date": pd.Timestamp(tsm_date), "tsm_usd": 400.0,
        "tw_date": pd.Timestamp(tw_date), "tw_twd": 2400.0,
        "fx_date": pd.Timestamp(tw_date), "usdtwd": 32.0,
        "premium_pct": 0.0,
    }


def test_price_from_2330_fx_and_reference_premium():
    # Before the NYSE open: 2330 has today's close, TSM still has yesterday's.
    est_open = implied_tsm_open(make_snap("2026-10-29", "2026-10-30"), premium_ref=15.0)

    expected = 2400.0 * 1.15 * 5 / 32.0      # = 431.25
    assert est_open["price"] == pytest.approx(expected)
    assert est_open["change_pct"] == pytest.approx((expected / 400.0 - 1) * 100)


def test_texts_name_the_dates_used():
    # On a US holiday the "open" is days away, so the text must say which closes it uses.
    est_open = implied_tsm_open(make_snap("2026-11-25", "2026-11-26"), premium_ref=15.0)

    assert est_open["chart"] == (
        "Est. next TSM open: \\$431.25 (+7.8% vs 11/25 close \\$400.00)\n"
        "from 2330 11/26 close x 5-day avg premium (+15.0%)"
    )
    assert "11/25" in est_open["console"] and "11/26" in est_open["console"]
    assert "今日" not in est_open["console"]


def test_none_when_2330_is_not_newer_than_tsm():
    # After the NYSE close both are from the same day, so 2330 adds nothing new.
    assert implied_tsm_open(make_snap("2026-10-30", "2026-10-30"), premium_ref=15.0) is None
    # Taiwan holiday: 2330 older than TSM.
    assert implied_tsm_open(make_snap("2026-10-30", "2026-10-29"), premium_ref=15.0) is None


def test_none_without_reference_premium():
    assert implied_tsm_open(make_snap("2026-10-29", "2026-10-30"), premium_ref=np.nan) is None
