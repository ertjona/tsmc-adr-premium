import numpy as np
import pandas as pd
import pytest

from tsmc_adr_premium import (
    CONFIRM_DAYS,
    band_label,
    build_signal,
    calculate_premium,
    classify_signal,
    current_zscore,
    drop_bad_ticks,
    latest_band,
)


def series(values):
    return pd.Series(values, index=pd.date_range("2026-01-01", periods=len(values), freq="B"), dtype=float)


class TestDropBadTicks:
    def test_drops_single_bad_fx_tick(self):
        # Real case: TWD=X showed 1.801 on 2011-10-25 between ~30 values.
        s = series([30.0, 30.1, 1.8, 30.1, 30.0])

        out = drop_bad_ticks(s, max_dev=0.1)

        assert 1.8 not in out.values
        assert len(out) == 4

    def test_keeps_real_drop_on_latest_day(self):
        # A big real move on the last day must not be treated as bad data.
        s = series([100.0, 100.0, 100.0, 100.0, 75.0])

        out = drop_bad_ticks(s, max_dev=0.4)

        assert out.iloc[-1] == 75.0

    def test_keeps_lasting_level_change(self):
        # A new level is accepted once the following CONFIRM_DAYS points agree with it.
        s = series([100.0] * 8 + [70.0] * 8)

        out = drop_bad_ticks(s, max_dev=0.1)

        assert len(out) == 16

    def test_level_change_right_after_first_day_drops_first_point(self):
        # Documented limit: one point before a level change at the very start
        # can't be told apart from a bad first tick.
        s = series([100.0, 70.0, 70.0, 70.0])

        out = drop_bad_ticks(s, max_dev=0.1)

        assert list(out.values) == [70.0, 70.0, 70.0]

    def test_drops_bad_tick_on_latest_day(self):
        # The latest day feeds the "Now" point, so a bad print there must be caught too.
        s = series([30.0, 30.1, 30.0, 1.8])

        out = drop_bad_ticks(s, max_dev=0.1)

        assert list(out.values) == [30.0, 30.1, 30.0]

    def test_drops_bad_tick_on_first_day(self):
        s = series([1.8, 30.0, 30.1, 30.0])

        out = drop_bad_ticks(s, max_dev=0.1)

        assert list(out.values) == [30.0, 30.1, 30.0]

    def test_keeps_good_latest_day_after_bad_tick(self):
        s = series([30.0, 30.0, 1.8, 30.0])

        out = drop_bad_ticks(s, max_dev=0.1)

        assert list(out.values) == [30.0, 30.0, 30.0]
        assert out.index[-1] == s.index[-1]

    def test_keeps_good_first_day_before_bad_tick(self):
        s = series([30.0, 1.8, 30.0, 30.0])

        out = drop_bad_ticks(s, max_dev=0.1)

        assert list(out.values) == [30.0, 30.0, 30.0]
        assert out.index[0] == s.index[0]

    def test_drops_two_bad_ticks_in_a_row(self):
        s = series([30.0, 30.0, 1.8, 1.8, 30.0, 30.0])

        out = drop_bad_ticks(s, max_dev=0.1)

        assert 1.8 not in out.values
        assert len(out) == 4

    def test_drops_run_of_three_and_keeps_good_latest_day(self):
        s = series([30.0, 30.0, 30.0, 1.8, 1.8, 1.8, 30.0])

        out = drop_bad_ticks(s, max_dev=0.1)

        assert list(out.values) == [30.0, 30.0, 30.0, 30.0]
        assert out.index[-1] == s.index[-1]

    def test_drops_run_as_long_as_confirm_days(self):
        s = series([30.0] * 4 + [1.8] * CONFIRM_DAYS + [30.0] * 2)

        out = drop_bad_ticks(s, max_dev=0.1)

        assert 1.8 not in out.values
        assert len(out) == 6

    def test_run_longer_than_confirm_days_is_taken_as_new_level(self):
        # Documented limit: a run longer than CONFIRM_DAYS looks like a real level change.
        s = series([30.0] * 4 + [1.8] * (CONFIRM_DAYS + 1) + [30.0] * 2)

        out = drop_bad_ticks(s, max_dev=0.1)

        assert 1.8 in out.values

    def test_short_series_is_kept(self):
        assert len(drop_bad_ticks(series([30.0]), max_dev=0.1)) == 1
        assert len(drop_bad_ticks(series([30.0, 1.8]), max_dev=0.1)) == 2
        assert len(drop_bad_ticks(series([]), max_dev=0.1)) == 0

    def test_drops_nan(self):
        s = series([30.0, np.nan, 30.0])

        out = drop_bad_ticks(s, max_dev=0.1)

        assert out.notna().all()
        assert len(out) == 2


class TestClassifySignal:
    def test_levels(self):
        assert classify_signal(2.0)[1] == "Well above 1y avg"
        assert classify_signal(1.0)[1] == "Above 1y avg"
        assert classify_signal(0.0)[1] == "Near 1y avg"
        assert classify_signal(-1.0)[1] == "Below 1y avg"
        assert classify_signal(-2.0)[1] == "Well below 1y avg"

    def test_nan_means_no_signal(self):
        assert classify_signal(np.nan)[1] == "No signal"

    def test_texts_use_band_length(self):
        console, chart, _ = classify_signal(-1.0, band_days=120)

        assert chart == "Below 120d avg"
        assert "近 120 天" in console

    def test_infinite_z_means_no_signal(self):
        assert classify_signal(float("-inf"))[1] == "No signal"
        assert classify_signal(float("inf"))[1] == "No signal"


def test_calculate_premium_adds_smoothed_and_rolling_columns():
    n = 300
    df = pd.DataFrame({
        "TSM_USD": np.full(n, 100.0),
        "TW2330_TWD": np.full(n, 500.0),
        "USDTWD": np.full(n, 30.0),
    }, index=pd.date_range("2025-01-01", periods=n, freq="B"))

    out = calculate_premium(df)

    # 100 / 5 * 30 = 600 vs 500 -> +20%
    assert out["premium_pct"].iloc[-1] == 20.0
    assert out["premium_5d"].iloc[-1] == 20.0
    assert out["premium_1y_mean"].iloc[-1] == 20.0
    assert out["premium_1y_std"].iloc[-1] == 0.0


def test_current_zscore_uses_latest_rolling_band():
    df = pd.DataFrame({"premium_1y_mean": [10.0, 15.0], "premium_1y_std": [1.0, 2.0]})

    assert current_zscore(df, 19.0) == 2.0


def test_latest_band_returns_last_mean_and_std():
    df = pd.DataFrame({"premium_1y_mean": [10.0, 15.0], "premium_1y_std": [1.0, 2.0]})

    assert latest_band(df) == (15.0, 2.0)


def test_band_label():
    assert band_label(252) == ("1y", "1 年")
    assert band_label(120) == ("120d", "120 天")


def test_build_signal_bundles_z_band_texts_and_open_estimate():
    n = 100
    df = pd.DataFrame({
        "premium_1y_mean": np.full(n, 15.0),
        "premium_1y_std": np.full(n, 2.0),
        "premium_5d": np.full(n, 15.0),
    })
    snap = {
        "tsm_date": pd.Timestamp("2026-10-29"), "tsm_usd": 400.0,
        "tw_date": pd.Timestamp("2026-10-30"), "tw_twd": 2400.0,
        "fx_date": pd.Timestamp("2026-10-30"), "usdtwd": 32.0,
        "premium_pct": 11.0,
    }

    sig = build_signal(df, snap)

    assert sig["z"] == -2.0
    assert sig["band"] == "100d"
    assert sig["chart"] == "Well below 100d avg"
    assert sig["console"].startswith("🔵")
    assert sig["est_open"]["price"] == pytest.approx(431.25)


def test_current_zscore_is_nan_when_band_is_flat():
    df = pd.DataFrame({"premium_1y_mean": [15.0], "premium_1y_std": [0.0]})

    assert np.isnan(current_zscore(df, 10.0))
