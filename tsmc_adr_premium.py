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

import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import sys
import os

# ─── 設定 ───
PERIOD = "5y"           # 預設抓 5 年資料，可改為 "1y", "2y", "10y", "max"
OUTPUT_CSV = "tsmc_adr_premium.csv"
OUTPUT_PNG = "tsmc_adr_premium.png"
ADR_RATIO = 5           # 1 TSM ADR = 5 shares of 2330.TW


def fetch_data(period=PERIOD):
    """從 yfinance 抓取 TSM、2330.TW、USD/TWD 的歷史收盤價"""
    print(f"正在下載 {period} 的歷史資料...")

    tsm = yf.download("TSM", period=period, auto_adjust=True, progress=False)
    tw2330 = yf.download("2330.TW", period=period, auto_adjust=True, progress=False)
    usdtwd = yf.download("TWD=X", period=period, auto_adjust=True, progress=False)

    # 取收盤價，展平 MultiIndex columns（yfinance 有時會回傳 MultiIndex）
    def get_close(df, name):
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(level=1, axis=1)
        return df[["Close"]].rename(columns={"Close": name})

    tsm_close = get_close(tsm, "TSM_USD")
    tw_close = get_close(tw2330, "TW2330_TWD")
    fx_close = get_close(usdtwd, "USDTWD")

    # 合併（以日期為 key，inner join 只保留三者都有資料的交易日）
    merged = tsm_close.join(tw_close, how="inner").join(fx_close, how="inner")
    merged = merged.dropna()

    print(f"  取得 {len(merged)} 個交易日的完整資料")
    return merged


def calculate_premium(df):
    """計算 ADR 溢價率"""
    # TSM 等價台幣價格 = TSM美元價 / 5 × 匯率
    # 注意：TWD=X 在 yfinance 上代表 1 USD = X TWD
    df["TSM_implied_TWD"] = (df["TSM_USD"] / ADR_RATIO) * df["USDTWD"]

    # 溢價 = (ADR隱含台幣價 - 台股價) / 台股價
    df["premium"] = (df["TSM_implied_TWD"] - df["TW2330_TWD"]) / df["TW2330_TWD"]
    df["premium_pct"] = df["premium"] * 100

    return df


def print_stats(df):
    """印出關鍵統計數據"""
    p = df["premium_pct"]

    print("\n" + "=" * 60)
    print("  TSMC ADR Premium 統計摘要")
    print("=" * 60)
    print(f"  資料期間：{df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"  交易日數：{len(df)}")
    print("-" * 60)
    print(f"  目前溢價：{p.iloc[-1]:+.1f}%")
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
    current = p.iloc[-1]
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


def plot_chart(df):
    """畫出 ADR 溢價歷史走勢圖"""
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
                 label=f"60-day MA", linestyle="--")

    # 平均線
    ax1.axhline(avg, color="#1D9E75", linewidth=1, linestyle=":",
                label=f"Period avg: {avg:.1f}%")
    ax1.axhline(0, color="#888", linewidth=0.5, alpha=0.5)

    # 標注目前值
    current = p.iloc[-1]
    ax1.annotate(f"Now: {current:+.1f}%",
                 xy=(df.index[-1], current),
                 xytext=(-80, 20), textcoords="offset points",
                 fontsize=10, fontweight="bold", color="#D85A30",
                 arrowprops=dict(arrowstyle="->", color="#D85A30", lw=1.2))

    ax1.set_ylabel("ADR Premium (%)", fontsize=11)
    ax1.set_title("TSMC ADR Premium: TSM (NYSE) vs 2330.TW (TWSE)", fontsize=13, pad=12)
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

    df = fetch_data(period)
    df = calculate_premium(df)
    print_stats(df)
    save_csv(df)
    plot_chart(df)

    print(f"\n✅ 完成！可用 Excel 開啟 {OUTPUT_CSV} 進一步分析")
    print(f"   或執行 python {os.path.basename(__file__)} 10y 取得更長期的資料")


if __name__ == "__main__":
    main()
