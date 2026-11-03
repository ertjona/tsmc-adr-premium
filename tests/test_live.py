from datetime import UTC, datetime

import pandas as pd

from tsmc_adr_premium import format_snapshot, implied_tsm_open, is_live, mark_live


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def snap(tsm_date, tw_date):
    return {
        "tsm_date": pd.Timestamp(tsm_date), "tsm_usd": 400.0,
        "tw_date": pd.Timestamp(tw_date), "tw_twd": 2400.0,
        "fx_date": pd.Timestamp(tw_date), "usdtwd": 32.0,
        "premium_pct": 0.0,
    }


class TestIsLive:
    def test_twse_during_session(self):
        # 03:00 UTC = 11:00 Taipei, before the 13:30 close
        assert is_live(pd.Timestamp("2026-11-03"), "tw", utc("2026-11-03T03:00"))

    def test_twse_after_close(self):
        # 06:00 UTC = 14:00 Taipei
        assert not is_live(pd.Timestamp("2026-11-03"), "tw", utc("2026-11-03T06:00"))

    def test_nyse_during_session_uses_new_york_date(self):
        # 20:00 UTC on 11/03 = 15:00 New York (EST), before the 16:00 close
        assert is_live(pd.Timestamp("2026-11-03"), "tsm", utc("2026-11-03T20:00"))

    def test_nyse_after_close(self):
        # 21:30 UTC = 16:30 New York
        assert not is_live(pd.Timestamp("2026-11-03"), "tsm", utc("2026-11-03T21:30"))

    def test_nyse_in_summer_time(self):
        # EDT (UTC-4): 19:30 UTC = 15:30 New York -> still open; 20:30 UTC = 16:30 -> closed
        assert is_live(pd.Timestamp("2026-07-15"), "tsm", utc("2026-07-15T19:30"))
        assert not is_live(pd.Timestamp("2026-07-15"), "tsm", utc("2026-07-15T20:30"))

    def test_twse_counts_as_live_until_14_00(self):
        # The 13:30 closing print can reach Yahoo late, so wait until 14:00 Taipei.
        assert is_live(pd.Timestamp("2026-11-03"), "tw", utc("2026-11-03T05:45"))   # 13:45
        assert not is_live(pd.Timestamp("2026-11-03"), "tw", utc("2026-11-03T06:00"))  # 14:00

    def test_older_date_is_never_live(self):
        assert not is_live(pd.Timestamp("2026-11-02"), "tw", utc("2026-11-03T03:00"))


def test_mark_live_adds_flags_without_changing_input():
    s = snap("2026-11-02", "2026-11-03")

    out = mark_live(s, utc("2026-11-03T03:00"))   # 11:00 Taipei: 2330 trading, NYSE closed

    assert out["tw_live"] is True
    assert out["tsm_live"] is False
    assert "tw_live" not in s


def test_format_snapshot_marks_live_prices():
    s = mark_live(snap("2026-11-02", "2026-11-03"), utc("2026-11-03T03:00"))

    assert "2330.TW NT$2,400 (11/03 live)" in format_snapshot(s)
    assert "TSM $400.00 (11/02)" in format_snapshot(s)


def test_no_open_estimate_while_2330_is_still_trading():
    live = mark_live(snap("2026-11-02", "2026-11-03"), utc("2026-11-03T03:00"))
    closed = mark_live(snap("2026-11-02", "2026-11-03"), utc("2026-11-03T11:00"))

    assert implied_tsm_open(live, premium_ref=15.0) is None
    assert implied_tsm_open(closed, premium_ref=15.0) is not None
