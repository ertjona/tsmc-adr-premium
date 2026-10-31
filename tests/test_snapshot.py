import numpy as np
import pandas as pd
import pytest

from tsmc_adr_premium import fill_latest_close, format_snapshot, latest_snapshot


def daily(values, dates):
    return pd.Series(values, index=pd.to_datetime(dates))


def intraday(values, stamps, tz):
    return pd.Series(values, index=pd.DatetimeIndex(stamps).tz_localize(tz))


class TestFillLatestClose:
    def test_fills_nan_close_for_today_from_intraday(self):
        d = daily([431.8, np.nan], ["2026-10-29", "2026-10-30"])
        i = intraday([404.1, 406.0], ["2026-10-30 15:50", "2026-10-30 15:55"], "America/New_York")

        out = fill_latest_close(d, i)

        assert out.loc["2026-10-30"] == 406.0
        assert out.loc["2026-10-29"] == 431.8

    def test_adds_missing_day_from_intraday(self):
        d = daily([431.8], ["2026-10-29"])
        i = intraday([406.0], ["2026-10-30 15:55"], "America/New_York")

        out = fill_latest_close(d, i)

        assert list(out.index) == list(pd.to_datetime(["2026-10-29", "2026-10-30"]))
        assert out.iloc[-1] == 406.0

    def test_keeps_official_daily_close_when_present(self):
        d = daily([2365.0, 2370.0], ["2026-10-29", "2026-10-30"])
        i = intraday([2365.0], ["2026-10-30 13:20"], "Asia/Taipei")

        out = fill_latest_close(d, i)

        assert out.loc["2026-10-30"] == 2370.0

    def test_uses_exchange_local_date_not_utc(self):
        # 20:30 New York on 10/30 is 00:30 UTC on 10/31, but it belongs to the 10/30 session.
        d = daily([1.0], ["2026-10-29"])
        i = intraday([2.0], ["2026-10-30 20:30"], "America/New_York")

        out = fill_latest_close(d, i)

        assert out.index[-1] == pd.Timestamp("2026-10-30")

    def test_empty_intraday_returns_daily_unchanged(self):
        d = daily([1.0, 2.0], ["2026-10-29", "2026-10-30"])
        i = pd.Series([], index=pd.DatetimeIndex([], tz="UTC"), dtype=float)

        out = fill_latest_close(d, i)

        pd.testing.assert_series_equal(out, d)


class TestLatestSnapshot:
    def test_pairs_latest_close_of_each_market_even_if_dates_differ(self):
        # Before NY opens: 2330 already closed today, TSM's latest is yesterday.
        tsm = daily([400.0], ["2026-10-29"])
        tw = daily([2300.0, 2400.0], ["2026-10-29", "2026-10-30"])
        fx = daily([32.0, 32.5], ["2026-10-29", "2026-10-30"])

        snap = latest_snapshot(tsm, tw, fx)

        assert snap["tsm_date"] == pd.Timestamp("2026-10-29")
        assert snap["tw_date"] == pd.Timestamp("2026-10-30")
        assert snap["tsm_usd"] == 400.0
        assert snap["tw_twd"] == 2400.0
        assert snap["usdtwd"] == 32.5
        implied = 400.0 / 5 * 32.5
        assert snap["premium_pct"] == pytest.approx((implied - 2400.0) / 2400.0 * 100)

    def test_skips_trailing_nan(self):
        tsm = daily([400.0, np.nan], ["2026-10-29", "2026-10-30"])
        tw = daily([2400.0], ["2026-10-29"])
        fx = daily([32.5], ["2026-10-29"])

        snap = latest_snapshot(tsm, tw, fx)

        assert snap["tsm_date"] == pd.Timestamp("2026-10-29")
        assert snap["tsm_usd"] == 400.0

    def test_fx_is_taken_on_or_before_latest_stock_date(self):
        # At 23:30 UTC, London is already on the next day, so TWD=X can have a row
        # dated after both stocks. That row must not be used.
        tsm = daily([400.0], ["2026-10-29"])
        tw = daily([2400.0], ["2026-10-29"])
        fx = daily([32.0, 33.0], ["2026-10-29", "2026-10-30"])

        snap = latest_snapshot(tsm, tw, fx)

        assert snap["fx_date"] == pd.Timestamp("2026-10-29")
        assert snap["usdtwd"] == 32.0


def test_format_snapshot_shows_price_and_date_of_each_market():
    snap = {
        "tsm_date": pd.Timestamp("2026-10-29"), "tsm_usd": 405.99,
        "tw_date": pd.Timestamp("2026-10-30"), "tw_twd": 2370.0,
        "fx_date": pd.Timestamp("2026-10-30"), "usdtwd": 32.5669,
        "premium_pct": 11.6,
    }

    text = format_snapshot(snap)

    assert text == "TSM $405.99 (10/29) · 2330.TW NT$2,370 (10/30) · USD/TWD 32.567 (10/30)"
