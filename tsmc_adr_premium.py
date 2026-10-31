"""
TSMC ADR Premium Tracker
========================
Tracks the premium/discount of TSM (NYSE ADR) over 2330.TW (TWSE).

Usage:
1. Install: pip install yfinance pandas matplotlib
2. Run: python tsmc_adr_premium.py [period]
3. Outputs:
   - tsmc_adr_premium.csv  -> daily premium data
   - tsmc_adr_premium.png  -> history chart
   - key statistics printed to the terminal

Formula:
  ADR Premium = (TSM close / 5 × USD/TWD − 2330 close) / 2330 close

Notes:
  - TSM and 2330.TW trade at different hours, so their closes are ~14 hours apart
  - History pairs closes by date; they are not simultaneous prices
  - FX uses Yahoo's daily TWD=X close
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

# ─── Settings ───
PERIOD = "5y"           # default history length; also "1y", "2y", "10y", "max"
OUTPUT_CSV = "tsmc_adr_premium.csv"
OUTPUT_PNG = "tsmc_adr_premium.png"
ADR_RATIO = 5           # 1 TSM ADR = 5 shares of 2330.TW
SIGNAL_WINDOW = 252     # judge high/low against the last year: the premium level drifts, so not the full period
MIN_BAND_DAYS = 60      # min rows before the band is drawn; with < 1 year it covers fewer days
SMOOTH_DAYS = 5         # smoothing window, damps day-to-day noise from the close-time gap
# max relative jump before a quote counts as bad (TWD=X once printed 1.8 instead of 30)
MAX_JUMP = {"TSM_USD": 0.4, "TW2330_TWD": 0.4, "USDTWD": 0.1}

# (z lower bound, console text, chart text, color), matched from high to low
SIGNAL_LEVELS = [
    (1.5, "🔴 顯著高於近 {zh}平均", "Well above {band} avg", "#C0392B"),
    (0.5, "🟡 略高於近 {zh}平均", "Above {band} avg", "#D4A017"),
    (-0.5, "⚪ 接近近 {zh}平均", "Near {band} avg", "#555555"),
    (-1.5, "🟢 略低於近 {zh}平均", "Below {band} avg", "#1D9E75"),
    (float("-inf"), "🔵 顯著低於近 {zh}平均", "Well below {band} avg", "#2E6DB4"),
]


TICKERS = {"TSM_USD": "TSM", "TW2330_TWD": "2330.TW", "USDTWD": "TWD=X"}


def _download_close(ticker, **kwargs):
    """Download one ticker's closes as a Series; empty Series if nothing comes back."""
    df = yf.download(ticker, auto_adjust=True, progress=False, **kwargs)
    if df.empty:
        return pd.Series(dtype=float)
    # Flatten MultiIndex columns (yfinance sometimes returns them)
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(level=1, axis=1)
    return df["Close"]


def drop_bad_ticks(s, max_dev, lookahead=3):
    """Drop NaN and obviously wrong quotes (e.g. TWD=X printing 1.8 instead of 30).

    Walking forward, a point is bad when it is more than ``max_dev`` away from
    BOTH the last kept point AND the median of the next ``lookahead`` points.
    With nothing ahead, only the last kept point counts, so the latest day
    (which feeds "Now") is checked too. Using a median ahead catches short runs
    of bad ticks, and a lasting level change is kept because the points after
    it agree with it. The first point has nothing kept before it, so it is
    checked afterwards against the first kept point after it.

    Limits: a real move larger than ``max_dev`` on the latest day is held back
    until the next day confirms it, and two bad ticks at the very start of the
    series are not caught.

    Args:
        s: Price series.
        max_dev: Allowed relative deviation, e.g. 0.1 = 10%.
        lookahead: How many following points form the forward reference.

    Returns:
        Filtered series (a new object).
    """
    s = s.dropna()
    if len(s) < 2:
        return s

    def is_off(value, ref):
        return ref is None or abs(value / ref - 1) > max_dev

    values = s.to_numpy()
    keep = [True] * len(values)
    last_kept = values[0]
    for i in range(1, len(values)):
        ahead = values[i + 1:i + 1 + lookahead]
        fwd_ref = float(np.median(ahead)) if len(ahead) else None
        if is_off(values[i], last_kept) and is_off(values[i], fwd_ref):
            keep[i] = False
        else:
            last_kept = values[i]

    next_kept = next((values[i] for i in range(1, len(values)) if keep[i]), None)
    if next_kept is not None and is_off(values[0], next_kept):
        keep[0] = False
    return s[keep]


def fill_latest_close(daily, intraday):
    """Fill the newest day's close from the last intraday bar.

    Right after the close, Yahoo's daily Close for that day is often NaN (or
    the row is missing), so use the last 5-minute bar instead. An official
    daily close is never overwritten.

    Args:
        daily: Daily closes, indexed by tz-naive dates.
        intraday: Intraday closes, indexed by tz-aware times in the exchange's time zone.

    Returns:
        Filled daily series (a new object; the input is not modified).
    """
    out = daily.copy()
    intraday = intraday.dropna()
    if intraday.empty:
        return out

    # Use the exchange's local date so a late bar doesn't roll into the next UTC day
    day = pd.Timestamp(intraday.index[-1].date())
    if day not in out.index or pd.isna(out.loc[day]):
        out.loc[day] = intraday.iloc[-1]
        out = out.sort_index()
    return out


def latest_snapshot(tsm, tw, fx):
    """Pair each market's latest close (dates may differ) and compute the premium.

    Before the TWSE open: TSM is the close just finished, 2330 the previous one.
    Before the NYSE open: 2330 is the close just finished, TSM the previous one.

    Args:
        tsm: TSM closes (USD).
        tw: 2330.TW closes (TWD).
        fx: USD/TWD rates.

    Returns:
        dict with each market's date and price, plus premium_pct.
    """
    tsm, tw = tsm.dropna(), tw.dropna()
    # Take FX on or before the latest stock date: London-time TWD=X can already have tomorrow's row
    fx = fx.dropna().loc[:max(tsm.index[-1], tw.index[-1])]
    implied = tsm.iloc[-1] / ADR_RATIO * fx.iloc[-1]
    premium = (implied - tw.iloc[-1]) / tw.iloc[-1] * 100
    return {
        "tsm_date": tsm.index[-1], "tsm_usd": float(tsm.iloc[-1]),
        "tw_date": tw.index[-1], "tw_twd": float(tw.iloc[-1]),
        "fx_date": fx.index[-1], "usdtwd": float(fx.iloc[-1]),
        "premium_pct": float(premium),
    }


def format_snapshot(snap):
    """One line with each market's price and date (shared by console and chart title)."""
    return (f"TSM ${snap['tsm_usd']:.2f} ({snap['tsm_date']:%m/%d}) · "
            f"2330.TW NT${snap['tw_twd']:,.0f} ({snap['tw_date']:%m/%d}) · "
            f"USD/TWD {snap['usdtwd']:.3f} ({snap['fx_date']:%m/%d})")


def fetch_data(period=PERIOD):
    """Download TSM, 2330.TW and USD/TWD closes from yfinance.

    Returns:
        (merged, closes): merged is a DataFrame of same-date rows (history);
        closes is a dict of each cleaned series with the newest day filled (snapshot).
    """
    print(f"正在下載 {period} 的歷史資料...")

    closes = {}
    for name, ticker in TICKERS.items():
        daily = _download_close(ticker, period=period)
        intraday = _download_close(ticker, period="5d", interval="5m")
        closes[name] = drop_bad_ticks(fill_latest_close(daily, intraday), MAX_JUMP[name])

    # Inner join on date: keep only days where all three have data
    merged = pd.concat(closes, axis=1, join="inner").dropna()

    print(f"  取得 {len(merged)} 個交易日的完整資料")
    return merged, closes


def calculate_premium(df):
    """Compute the ADR premium plus its 5-day average and rolling band."""
    # TSM price in TWD per 2330 share = TSM USD / 5 × FX
    # Note: TWD=X on yfinance means 1 USD = X TWD
    df["TSM_implied_TWD"] = (df["TSM_USD"] / ADR_RATIO) * df["USDTWD"]

    # Premium = (ADR-implied TWD price − 2330 price) / 2330 price
    df["premium"] = (df["TSM_implied_TWD"] - df["TW2330_TWD"]) / df["TW2330_TWD"]
    df["premium_pct"] = df["premium"] * 100

    p = df["premium_pct"]
    df["premium_5d"] = p.rolling(SMOOTH_DAYS).mean()
    df["premium_1y_mean"] = p.rolling(SIGNAL_WINDOW, min_periods=MIN_BAND_DAYS).mean()
    df["premium_1y_std"] = p.rolling(SIGNAL_WINDOW, min_periods=MIN_BAND_DAYS).std()

    return df


def latest_band(df):
    """Return (mean, std) of the rolling band on the last history row."""
    return df["premium_1y_mean"].iloc[-1], df["premium_1y_std"].iloc[-1]


def band_name(n_rows):
    """Label for the band window: "1y" once a full window exists, else e.g. "120d"."""
    return "1y" if n_rows >= SIGNAL_WINDOW else f"{n_rows}d"


def current_zscore(df, premium_pct):
    """z-score of the current premium against the latest rolling band.

    Returns NaN when the band is missing (too little data) or flat (std 0).
    """
    mean, std = latest_band(df)
    if pd.isna(std) or std == 0:
        return float("nan")
    return (premium_pct - mean) / std


def classify_signal(z, band="1y"):
    """Map a z-score to (console text, chart text, color).

    Args:
        z: z-score; any non-finite value means there is no signal.
        band: Band window label from ``band_name``, used in the texts.
    """
    if not np.isfinite(z):
        return "無訊號", "No signal", "#555555"
    zh = "1 年" if band == "1y" else f"{band[:-1]} 天"
    for threshold, console, chart, color in SIGNAL_LEVELS:
        if z > threshold:
            return console.format(zh=zh), chart.format(band=band), color


def print_stats(df, snap, z):
    """Print key stats; "now" uses each market's latest close (snap), the signal uses z."""
    p = df["premium_pct"]

    print("\n" + "=" * 60)
    print("  TSMC ADR Premium 統計摘要")
    print("=" * 60)
    print(f"  資料期間：{df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"  交易日數：{len(df)}")
    print("-" * 60)
    print(f"  目前溢價：{snap['premium_pct']:+.1f}%")
    print(f"    {format_snapshot(snap)}")
    print(f"  全期平均：{p.mean():+.1f}%")
    print(f"  全期中位數：{p.median():+.1f}%")
    print(f"  標準差：  {p.std():.1f}%")
    print(f"  最高溢價：{p.max():+.1f}%  ({p.idxmax().strftime('%Y-%m-%d')})")
    print(f"  最低溢價：{p.min():+.1f}%  ({p.idxmin().strftime('%Y-%m-%d')})")
    print("-" * 60)

    # Recent averages
    for label, days in [("近 1 週", 5), ("近 1 月", 22), ("近 3 月", 66), ("近 1 年", 252)]:
        if len(p) >= days:
            recent = p.iloc[-days:]
            print(f"  {label}平均：{recent.mean():+.1f}%  (最高 {recent.max():+.1f}%, 最低 {recent.min():+.1f}%)")

    print("=" * 60)

    # Where the current premium sits in the rolling band
    band = band_name(len(df))
    mean, std = latest_band(df)
    if pd.isna(std):
        print(f"  近期區間：資料不足（至少需要 {MIN_BAND_DAYS} 個交易日，目前 {len(df)}）")
    elif std == 0:
        print(f"  近期區間：溢價在區間內沒有變動（{mean:+.1f}%），無法計算 z")
    else:
        print(f"  近期區間（{band}）：{mean:+.1f}% ± {std:.1f}%  (z = {z:+.2f})")
    print(f"  訊號：{classify_signal(z, band)[0]}")
    print("=" * 60)


def plot_chart(df, snap, z):
    """Draw the premium history chart.

    Top: daily premium, 5-day avg, rolling avg ±1σ band, and a "Now" label
    with the latest-close premium (snap) and signal. Bottom: 2330.TW price.
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1],
                                    sharex=True, gridspec_kw={"hspace": 0.08})

    # ─── Top: premium ───
    mean, std = df["premium_1y_mean"], df["premium_1y_std"]
    band = band_name(len(df))

    # Rolling avg ±1σ band: the premium level drifts, so judge high/low against
    # recent history. Skip it entirely (incl. legend) when there's too little data.
    if mean.notna().any():
        ax1.fill_between(df.index, mean - std, mean + std, color="#1D9E75", alpha=0.12,
                         linewidth=0, label=f"{band} avg ±1σ")
        ax1.plot(df.index, mean, color="#1D9E75", linewidth=1.2, linestyle="--",
                 label=f"{band} avg")

    # Daily premium is noisy (close-time gap): draw it faint, the 5-day avg is the main line
    ax1.plot(df.index, df["premium_pct"], color="#999", linewidth=0.6, alpha=0.6, label="Daily")
    ax1.plot(df.index, df["premium_5d"], color="#222", linewidth=1.3, label=f"{SMOOTH_DAYS}-day avg")
    ax1.axhline(0, color="#888", linewidth=0.5, alpha=0.5)

    # Mark "Now" (latest closes, dates may differ), colored by signal
    current = snap["premium_pct"]
    _, signal_text, color = classify_signal(z, band)
    now_x = max(snap["tsm_date"], snap["tw_date"])
    ax1.plot(now_x, current, "o", color=color, markersize=6, zorder=5)
    z_text = f" (z {z:+.1f})" if np.isfinite(z) else ""
    ax1.annotate(f"Now: {current:+.1f}%\n{signal_text}{z_text}",
                 xy=(now_x, current),
                 xytext=(-150, 30), textcoords="offset points",
                 fontsize=10, fontweight="bold", color=color,
                 bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": color, "alpha": 0.9},
                 arrowprops={"arrowstyle": "->", "color": color, "lw": 1.2})

    ax1.set_ylabel("ADR Premium (%)", fontsize=11)
    updated = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")
    # matplotlib treats paired $ as mathtext, so escape them
    latest = format_snapshot(snap).replace("$", r"\$")
    ax1.set_title("TSMC ADR Premium: TSM (NYSE) vs 2330.TW (TWSE)\n"
                  f"Latest: {latest}  |  Updated {updated} (Taipei)",
                  fontsize=12, pad=12)
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.15)

    # ─── Bottom: 2330.TW price for context ───
    ax2.plot(df.index, df["TW2330_TWD"], color="#1D9E75", linewidth=1)
    ax2.fill_between(df.index, df["TW2330_TWD"], alpha=0.1, color="#1D9E75")
    ax2.set_ylabel("2330.TW (NT$)", fontsize=10)
    ax2.set_xlabel("Date", fontsize=10)
    ax2.grid(True, alpha=0.15)

    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    fig.autofmt_xdate(rotation=45)

    plt.tight_layout()
    plt.savefig(OUTPUT_PNG, dpi=150, bbox_inches="tight")
    print(f"\n📊 圖表已儲存至 {OUTPUT_PNG}")


def save_csv(df):
    """Export the daily history to CSV."""
    export = df[["TSM_USD", "TW2330_TWD", "USDTWD", "TSM_implied_TWD", "premium_pct"]].copy()
    export.columns = ["TSM_Price_USD", "2330TW_Price_TWD", "USD_TWD_Rate",
                       "TSM_Implied_TWD", "ADR_Premium_Pct"]
    export.index.name = "Date"
    export.to_csv(OUTPUT_CSV)
    print(f"📄 資料已儲存至 {OUTPUT_CSV}")


def main():
    period = sys.argv[1] if len(sys.argv) > 1 else PERIOD

    df, closes = fetch_data(period)
    df = calculate_premium(df)
    snap = latest_snapshot(closes["TSM_USD"], closes["TW2330_TWD"], closes["USDTWD"])
    z = current_zscore(df, snap["premium_pct"])
    print_stats(df, snap, z)
    save_csv(df)
    plot_chart(df, snap, z)

    print(f"\n✅ 完成！可用 Excel 開啟 {OUTPUT_CSV} 進一步分析")
    print(f"   或執行 python {os.path.basename(__file__)} 10y 取得更長期的資料")


if __name__ == "__main__":
    main()
