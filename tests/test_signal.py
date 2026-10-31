import numpy as np
import pandas as pd

from tsmc_adr_premium import (
    calculate_premium,
    classify_signal,
    current_zscore,
    drop_bad_ticks,
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
        s = series([100.0, 100.0, 70.0, 70.0, 70.0, 70.0])

        out = drop_bad_ticks(s, max_dev=0.1)

        assert len(out) == 6

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

    def test_nan_means_not_enough_data(self):
        assert classify_signal(np.nan)[1] == "Not enough data"


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
