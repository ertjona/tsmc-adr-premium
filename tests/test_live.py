from datetime import UTC, datetime

import pandas as pd

from tsmc_adr_premium import format_snapshot, implied_tsm_open, is_live, latest_snapshot


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def snap(tsm_date, tw_date, now_utc):
    def one(value, day):
        return pd.Series([value], index=pd.to_datetime([day]))

    return latest_snapshot(one(400.0, tsm_date), one(2400.0, tw_date), one(32.0, tw_date), now_utc)


class TestIsLive:
    def test_twse_during_session(self):
        # 03:00 UTC = 11:00 Taipei, before the 13:30 close
        assert is_live(pd.Timestamp("2026-11-03"), "tw", utc("2026-11-03T03:00"))

    def test_nyse_during_session_uses_new_york_date(self):
        # 20:00 UTC on 11/03 = 15:00 New York (EST), before the 16:00 close
        assert is_live(pd.Timestamp("2026-11-03"), "tsm", utc("2026-11-03T20:00"))

    def test_nyse_counts_as_live_until_16_30(self):
        # The closing-auction print can reach Yahoo late, so wait until 16:30 New York.
        assert is_live(pd.Timestamp("2026-11-03"), "tsm", utc("2026-11-03T21:15"))      # 16:15
        assert not is_live(pd.Timestamp("2026-11-03"), "tsm", utc("2026-11-03T21:30"))  # 16:30

    def test_nyse_in_summer_time(self):
        # EDT (UTC-4): 20:17 UTC = 16:17 New York -> still live; 20:30 UTC = 16:30 -> closed
        assert is_live(pd.Timestamp("2026-07-15"), "tsm", utc("2026-07-15T20:17"))
        assert not is_live(pd.Timestamp("2026-07-15"), "tsm", utc("2026-07-15T20:30"))

    def test_twse_counts_as_live_until_14_00(self):
        # The 13:30 closing print can reach Yahoo late, so wait until 14:00 Taipei.
        assert is_live(pd.Timestamp("2026-11-03"), "tw", utc("2026-11-03T05:45"))   # 13:45
        assert not is_live(pd.Timestamp("2026-11-03"), "tw", utc("2026-11-03T06:00"))  # 14:00

    def test_older_date_is_never_live(self):
        assert not is_live(pd.Timestamp("2026-11-02"), "tw", utc("2026-11-03T03:00"))


def test_latest_snapshot_sets_live_flags():
    s = snap("2026-11-02", "2026-11-03", utc("2026-11-03T03:00"))   # 11:00 Taipei: 2330 trading

    assert s["tw_live"] is True
    assert s["tsm_live"] is False


def test_format_snapshot_marks_live_prices():
    s = snap("2026-11-02", "2026-11-03", utc("2026-11-03T03:00"))

    assert "2330.TW NT$2,400 (11/03 live)" in format_snapshot(s)
    assert "TSM $400.00 (11/02)" in format_snapshot(s)


def test_no_open_estimate_while_2330_is_still_trading():
    live = snap("2026-11-02", "2026-11-03", utc("2026-11-03T03:00"))
    closed = snap("2026-11-02", "2026-11-03", utc("2026-11-03T11:00"))

    assert implied_tsm_open(live, premium_ref=15.0) is None
    assert implied_tsm_open(closed, premium_ref=15.0) is not None
