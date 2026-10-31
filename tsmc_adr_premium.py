"""
TSMC ADR Premium Tracker
========================
追蹤 TSM (美股 ADR) 相對於 2330.TW (台股) 的溢價/折價歷史。

使用方式：
1. 安裝依賴：pip install yfinance pandas matplotlib
2. 執行：python tsmc_adr_premium.py
3. 產出：
   - tsmc_adr_premium.csv  → 每日溢價數據
   - tsmc_adr_premium.png  → 歷史走勢圖
   - 終端機顯示關鍵統計數據

公式：
  ADR Premium = (TSM收盤價 / 5 × USD/TWD匯率 − 2330收盤價) / 2330收盤價

注意：
  - TSM 和 2330.TW 的交易時間不同，存在時差
  - 本腳本以收盤價對齊日期，非同步即時價格
  - 匯率使用每日收盤中間價
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

# ─── 設定 ───
PERIOD = "5y"           # 預設抓 5 年資料，可改為 "1y", "2y", "10y", "max"
OUTPUT_CSV = "tsmc_adr_premium.csv"
OUTPUT_PNG = "tsmc_adr_premium.png"
ADR_RATIO = 5           # 1 TSM ADR = 5 shares of 2330.TW


TICKERS = {"TSM_USD": "TSM", "TW2330_TWD": "2330.TW", "USDTWD": "TWD=X"}


def _download_close(ticker, **kwargs):
    """下載單一標的的收盤價 Series；抓不到時回傳空 Series"""
    df = yf.download(ticker, auto_adjust=True, progress=False, **kwargs)
    if df.empty:
        return pd.Series(dtype=float)
    # 展平 MultiIndex columns（yfinance 有時會回傳 MultiIndex）
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(level=1, axis=1)
    return df["Close"]


def fill_latest_close(daily, intraday):
    """用盤中最後一筆價格補上日線最新一天的收盤價。

    Yahoo 剛收盤後，當天日線的 Close 常是 NaN（或還沒有那一列），
    這裡用 5 分鐘線最後一筆價格補上。已有正式收盤價時不覆蓋。

    Args:
        daily: 日線收盤價，index 為 tz-naive 日期。
        intraday: 盤中收盤價，index 為交易所當地時區的 tz-aware 時間。

    Returns:
        補好的日線 Series（新物件，不改動輸入）。
    """
    out = daily.copy()
    intraday = intraday.dropna()
    if intraday.empty:
        return out

    # 用交易所當地日期，避免盤後時間換成 UTC 後跑到隔天
    day = pd.Timestamp(intraday.index[-1].date())
    if day not in out.index or pd.isna(out.loc[day]):
        out.loc[day] = intraday.iloc[-1]
        out = out.sort_index()
    return out


def latest_snapshot(tsm, tw, fx):
    """取三者各自最新的收盤價（日期可以不同）並計算溢價。

    台股開盤前：TSM 是剛收的美股收盤，2330 是前一個台股收盤。
    美股開盤前：2330 是剛收的台股收盤，TSM 是前一個美股收盤。

    Args:
        tsm: TSM 收盤價（USD）。
        tw: 2330.TW 收盤價（TWD）。
        fx: USD/TWD 匯率。

    Returns:
        dict，含各自的日期、價格，以及 premium_pct。
    """
    tsm, tw = tsm.dropna(), tw.dropna()
    # 匯率取最新股價日期當天或之前的值：倫敦時區的 TWD=X 可能已經有「明天」的資料
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
    """把 snap 的三個價格與日期組成一行文字（給終端機與圖表標題共用）"""
    return (f"TSM ${snap['tsm_usd']:.2f} ({snap['tsm_date']:%m/%d}) · "
            f"2330.TW NT${snap['tw_twd']:,.0f} ({snap['tw_date']:%m/%d}) · "
            f"USD/TWD {snap['usdtwd']:.3f} ({snap['fx_date']:%m/%d})")


def fetch_data(period=PERIOD):
    """從 yfinance 抓取 TSM、2330.TW、USD/TWD 的歷史收盤價

    Returns:
        (merged, closes)：merged 是三者同日期對齊的 DataFrame（歷史用），
        closes 是各自補好最新一天的收盤價 dict（最新快照用）。
    """
    print(f"正在下載 {period} 的歷史資料...")

    closes = {}
    for name, ticker in TICKERS.items():
        daily = _download_close(ticker, period=period)
        intraday = _download_close(ticker, period="5d", interval="5m")
        closes[name] = fill_latest_close(daily, intraday)

    # 合併（以日期為 key，inner join 只保留三者都有資料的交易日）
    merged = pd.concat(closes, axis=1, join="inner").dropna()

    print(f"  取得 {len(merged)} 個交易日的完整資料")
    return merged, closes


def calculate_premium(df):
    """計算 ADR 溢價率"""
    # TSM 等價台幣價格 = TSM美元價 / 5 × 匯率
    # 注意：TWD=X 在 yfinance 上代表 1 USD = X TWD
    df["TSM_implied_TWD"] = (df["TSM_USD"] / ADR_RATIO) * df["USDTWD"]

    # 溢價 = (ADR隱含台幣價 - 台股價) / 台股價
    df["premium"] = (df["TSM_implied_TWD"] - df["TW2330_TWD"]) / df["TW2330_TWD"]
    df["premium_pct"] = df["premium"] * 100

    return df


def print_stats(df, snap):
    """印出關鍵統計數據；目前溢價用各市場最新收盤（snap）"""
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

    # 近期趨勢
    for label, days in [("近 1 週", 5), ("近 1 月", 22), ("近 3 月", 66), ("近 1 年", 252)]:
        if len(p) >= days:
            recent = p.iloc[-days:]
            print(f"  {label}平均：{recent.mean():+.1f}%  (最高 {recent.max():+.1f}%, 最低 {recent.min():+.1f}%)")

    print("=" * 60)

    # 判斷目前水位
    current = snap["premium_pct"]
    avg = p.mean()
    std = p.std()
    if current > avg + 1.5 * std:
        signal = "🔴 顯著高於歷史平均（可能反映美股端過熱情緒）"
    elif current > avg + 0.5 * std:
        signal = "🟡 略高於歷史平均"
    elif current < avg - 0.5 * std:
        signal = "🟢 低於歷史平均（ADR 相對便宜）"
    else:
        signal = "⚪ 接近歷史平均水準"
    print(f"  訊號：{signal}")
    print("=" * 60)


def plot_chart(df, snap):
    """畫出 ADR 溢價歷史走勢圖；右端標注各市場最新收盤的溢價（snap）"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1],
                                    sharex=True, gridspec_kw={"hspace": 0.08})

    # ─── 上圖：溢價走勢 ───
    p = df["premium_pct"]
    avg = p.mean()

    # 填色：溢價為紅色系，折價為藍色系
    ax1.fill_between(df.index, p, avg, where=(p >= avg),
                     color="#F0997B", alpha=0.3, interpolate=True)
    ax1.fill_between(df.index, p, avg, where=(p < avg),
                     color="#85B7EB", alpha=0.3, interpolate=True)
    ax1.plot(df.index, p, color="#333", linewidth=0.8, alpha=0.8)

    # 移動平均線
    if len(df) > 60:
        ma60 = p.rolling(60).mean()
        ax1.plot(df.index, ma60, color="#D85A30", linewidth=1.5,
                 label="60-day MA", linestyle="--")

    # 平均線
    ax1.axhline(avg, color="#1D9E75", linewidth=1, linestyle=":",
                label=f"Period avg: {avg:.1f}%")
    ax1.axhline(0, color="#888", linewidth=0.5, alpha=0.5)

    # 標注目前值（兩市場最新收盤，日期可能不同）
    current = snap["premium_pct"]
    now_x = max(snap["tsm_date"], snap["tw_date"])
    ax1.plot(now_x, current, "o", color="#D85A30", markersize=5)
    ax1.annotate(f"Now: {current:+.1f}%",
                 xy=(now_x, current),
                 xytext=(-80, 20), textcoords="offset points",
                 fontsize=10, fontweight="bold", color="#D85A30",
                 arrowprops={"arrowstyle": "->", "color": "#D85A30", "lw": 1.2})

    ax1.set_ylabel("ADR Premium (%)", fontsize=11)
    updated = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")
    # matplotlib 會把成對的 $ 當成數學式，要跳脫
    latest = format_snapshot(snap).replace("$", r"\$")
    ax1.set_title("TSMC ADR Premium: TSM (NYSE) vs 2330.TW (TWSE)\n"
                  f"Latest: {latest}  |  Updated {updated} (Taipei)",
                  fontsize=12, pad=12)
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.15)

    # ─── 下圖：台股價格走勢（提供背景脈絡）───
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
    """匯出 CSV"""
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
    print_stats(df, snap)
    save_csv(df)
    plot_chart(df, snap)

    print(f"\n✅ 完成！可用 Excel 開啟 {OUTPUT_CSV} 進一步分析")
    print(f"   或執行 python {os.path.basename(__file__)} 10y 取得更長期的資料")


if __name__ == "__main__":
    main()
