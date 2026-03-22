import { useState, useMemo, useCallback } from "react";

// Sample monthly data points (approximate historical ADR premium %)
// Users can replace this with their own CSV data from the Python script
const SAMPLE_DATA = [
  { date: "2020-01", premium: 2.1 },
  { date: "2020-04", premium: 3.5 },
  { date: "2020-07", premium: 4.2 },
  { date: "2020-10", premium: 3.8 },
  { date: "2021-01", premium: 5.1 },
  { date: "2021-04", premium: 4.6 },
  { date: "2021-07", premium: 6.2 },
  { date: "2021-10", premium: 5.8 },
  { date: "2022-01", premium: 4.9 },
  { date: "2022-04", premium: 3.2 },
  { date: "2022-07", premium: 1.8 },
  { date: "2022-10", premium: 0.5 },
  { date: "2022-12", premium: 0.2 },
  { date: "2023-01", premium: 1.5 },
  { date: "2023-03", premium: 4.8 },
  { date: "2023-06", premium: 8.2 },
  { date: "2023-09", premium: 10.5 },
  { date: "2023-12", premium: 12.8 },
  { date: "2024-01", premium: 14.2 },
  { date: "2024-03", premium: 16.5 },
  { date: "2024-06", premium: 18.3 },
  { date: "2024-08", premium: 15.2 },
  { date: "2024-10", premium: 19.8 },
  { date: "2024-12", premium: 22.1 },
  { date: "2025-01", premium: 25.0 },
  { date: "2025-03", premium: 21.3 },
  { date: "2025-06", premium: 18.7 },
  { date: "2025-09", premium: 15.4 },
  { date: "2025-12", premium: 13.8 },
  { date: "2026-01", premium: 12.5 },
  { date: "2026-03", premium: 10.7 },
];

const FONT = `'DM Sans', 'Noto Sans TC', sans-serif`;
const MONO = `'JetBrains Mono', monospace`;

export default function ADRPremiumTracker() {
  const [data, setData] = useState(SAMPLE_DATA);
  const [csvInput, setCsvInput] = useState("");
  const [showImport, setShowImport] = useState(false);
  const [hoverIdx, setHoverIdx] = useState(null);

  // ─── 即時計算機 ───
  const [calcTSM, setCalcTSM] = useState(329.24);
  const [calc2330, setCalc2330] = useState(1905);
  const [calcFX, setCalcFX] = useState(32.03);

  const calcImplied = (calcTSM / 5) * calcFX;
  const calcPremium = ((calcImplied - calc2330) / calc2330) * 100;

  // ─── 統計 ───
  const stats = useMemo(() => {
    const prems = data.map((d) => d.premium);
    const avg = prems.reduce((a, b) => a + b, 0) / prems.length;
    const max = Math.max(...prems);
    const min = Math.min(...prems);
    const maxIdx = prems.indexOf(max);
    const minIdx = prems.indexOf(min);
    const current = prems[prems.length - 1];
    const std = Math.sqrt(prems.reduce((s, p) => s + (p - avg) ** 2, 0) / prems.length);
    return { avg, max, min, maxIdx, minIdx, current, std };
  }, [data]);

  // ─── 圖表 ───
  const chartW = 600, chartH = 220, padL = 50, padR = 20, padT = 20, padB = 30;
  const plotW = chartW - padL - padR;
  const plotH = chartH - padT - padB;

  const chartData = useMemo(() => {
    const prems = data.map((d) => d.premium);
    const yMin = Math.min(0, Math.min(...prems) - 2);
    const yMax = Math.max(...prems) + 3;
    const yRange = yMax - yMin;

    const points = data.map((d, i) => ({
      x: padL + (i / (data.length - 1)) * plotW,
      y: padT + plotH - ((d.premium - yMin) / yRange) * plotH,
      premium: d.premium,
      date: d.date,
    }));

    const avgY = padT + plotH - ((stats.avg - yMin) / yRange) * plotH;
    const zeroY = padT + plotH - ((0 - yMin) / yRange) * plotH;

    const yTicks = [];
    const step = yRange > 20 ? 5 : yRange > 10 ? 3 : 2;
    for (let v = Math.ceil(yMin / step) * step; v <= yMax; v += step) {
      yTicks.push({ v, y: padT + plotH - ((v - yMin) / yRange) * plotH });
    }

    return { points, avgY, zeroY, yTicks, yMin, yMax };
  }, [data, stats]);

  const polyline = chartData.points.map((p) => `${p.x},${p.y}`).join(" ");
  const areaPath =
    `M${chartData.points[0].x},${chartData.zeroY} ` +
    chartData.points.map((p) => `L${p.x},${p.y}`).join(" ") +
    ` L${chartData.points[chartData.points.length - 1].x},${chartData.zeroY} Z`;

  // ─── CSV 匯入 ───
  const handleImport = useCallback(() => {
    try {
      const lines = csvInput.trim().split("\n");
      const parsed = [];
      for (const line of lines) {
        if (line.startsWith("Date") || line.startsWith("date")) continue;
        const parts = line.split(",");
        if (parts.length >= 6) {
          const date = parts[0].trim().substring(0, 7);
          const prem = parseFloat(parts[5]);
          if (!isNaN(prem)) parsed.push({ date, premium: prem });
        }
      }
      if (parsed.length > 0) {
        // 如果資料太多，取每月最後一筆
        if (parsed.length > 200) {
          const monthly = {};
          for (const d of parsed) {
            monthly[d.date] = d;
          }
          setData(Object.values(monthly).sort((a, b) => a.date.localeCompare(b.date)));
        } else {
          setData(parsed);
        }
        setShowImport(false);
        setCsvInput("");
      }
    } catch {
      // silent
    }
  }, [csvInput]);

  const signal =
    stats.current > stats.avg + 1.5 * stats.std
      ? { text: "顯著高於歷史平均", color: "#E24B4A", bg: "rgba(248,113,113,0.1)" }
      : stats.current > stats.avg + 0.5 * stats.std
      ? { text: "略高於歷史平均", color: "#EF9F27", bg: "rgba(251,191,36,0.1)" }
      : stats.current < stats.avg - 0.5 * stats.std
      ? { text: "低於歷史平均", color: "#1D9E75", bg: "rgba(52,211,153,0.1)" }
      : { text: "接近歷史平均", color: "#64748b", bg: "rgba(100,116,139,0.1)" };

  const inputStyle = {
    padding: "6px 10px",
    borderRadius: 6,
    border: "1px solid #334155",
    background: "#0f172a",
    color: "#e2e8f0",
    fontFamily: MONO,
    fontSize: 13,
    width: 100,
    outline: "none",
  };

  return (
    <div style={{ fontFamily: FONT, background: "#0a0f1a", color: "#e2e8f0", minHeight: "100vh", padding: "20px 16px" }}>
      <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&family=Noto+Sans+TC:wght@400;500;700&display=swap" rel="stylesheet" />

      <div style={{ maxWidth: 680, margin: "0 auto" }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px", color: "#f8fafc" }}>
          TSMC ADR Premium Tracker
        </h1>
        <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 20px" }}>
          TSM (NYSE) vs 2330.TW (TWSE) — 溢價歷史追蹤與即時計算
        </p>

        {/* ─── 即時計算機 ─── */}
        <div style={{
          background: "#111827", border: "1px solid #1e293b", borderRadius: 12,
          padding: "16px 20px", marginBottom: 16, borderTop: "3px solid #22d3ee"
        }}>
          <div style={{ fontSize: 12, color: "#64748b", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 12 }}>
            即時溢價計算機
          </div>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div>
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 3 }}>TSM (USD)</div>
              <input type="number" value={calcTSM} onChange={(e) => setCalcTSM(+e.target.value || 0)} step="0.01" style={inputStyle} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 3 }}>2330.TW (TWD)</div>
              <input type="number" value={calc2330} onChange={(e) => setCalc2330(+e.target.value || 0)} step="1" style={inputStyle} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 3 }}>USD/TWD</div>
              <input type="number" value={calcFX} onChange={(e) => setCalcFX(+e.target.value || 0)} step="0.01" style={inputStyle} />
            </div>
            <div style={{ fontSize: 11, color: "#64748b", lineHeight: 1.6 }}>
              <div>隱含台幣價：<span style={{ color: "#22d3ee", fontFamily: MONO }}>NT${calcImplied.toFixed(0)}</span></div>
              <div>ADR 溢價：<span style={{
                color: calcPremium > 15 ? "#f87171" : calcPremium > 8 ? "#fbbf24" : "#34d399",
                fontFamily: MONO, fontWeight: 700, fontSize: 15
              }}>{calcPremium >= 0 ? "+" : ""}{calcPremium.toFixed(1)}%</span></div>
            </div>
          </div>
          <div style={{ fontSize: 11, color: "#475569", marginTop: 8 }}>
            公式：(TSM ÷ 5 × 匯率 − 2330) ÷ 2330 = ({calcTSM} ÷ 5 × {calcFX} − {calc2330}) ÷ {calc2330}
          </div>
        </div>

        {/* ─── 統計卡片 ─── */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, marginBottom: 16 }}>
          {[
            { label: "目前溢價", value: `${stats.current >= 0 ? "+" : ""}${stats.current.toFixed(1)}%`, color: signal.color },
            { label: "歷史平均", value: `${stats.avg.toFixed(1)}%`, color: "#22d3ee" },
            { label: "最高", value: `${stats.max.toFixed(1)}%`, sub: data[stats.maxIdx]?.date, color: "#f87171" },
            { label: "最低", value: `${stats.min.toFixed(1)}%`, sub: data[stats.minIdx]?.date, color: "#34d399" },
          ].map((m) => (
            <div key={m.label} style={{ background: "#111827", border: "1px solid #1e293b", borderRadius: 10, padding: "12px 14px" }}>
              <div style={{ fontSize: 11, color: "#64748b" }}>{m.label}</div>
              <div style={{ fontSize: 20, fontWeight: 700, fontFamily: MONO, color: m.color }}>{m.value}</div>
              {m.sub && <div style={{ fontSize: 10, color: "#475569" }}>{m.sub}</div>}
            </div>
          ))}
        </div>

        {/* ─── 訊號 ─── */}
        <div style={{
          padding: "10px 16px", borderRadius: 8, marginBottom: 16,
          background: signal.bg, border: `1px solid ${signal.color}33`,
          display: "flex", alignItems: "center", gap: 8
        }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: signal.color }} />
          <span style={{ fontSize: 13, color: signal.color, fontWeight: 600 }}>{signal.text}</span>
          <span style={{ fontSize: 12, color: "#64748b" }}>
            — 目前 {stats.current.toFixed(1)}% vs 平均 {stats.avg.toFixed(1)}% (±{stats.std.toFixed(1)}%)
          </span>
        </div>

        {/* ─── 圖表 ─── */}
        <div style={{ background: "#111827", border: "1px solid #1e293b", borderRadius: 12, padding: "16px 12px", marginBottom: 16 }}>
          <svg width="100%" viewBox={`0 0 ${chartW} ${chartH}`} style={{ display: "block" }}
            onMouseLeave={() => setHoverIdx(null)}>
            {/* Grid */}
            {chartData.yTicks.map((t) => (
              <g key={t.v}>
                <line x1={padL} y1={t.y} x2={chartW - padR} y2={t.y} stroke="#1e293b" strokeWidth="0.5" />
                <text x={padL - 6} y={t.y + 4} textAnchor="end" fill="#475569" fontSize="10" fontFamily={MONO}>{t.v}%</text>
              </g>
            ))}

            {/* Average line */}
            <line x1={padL} y1={chartData.avgY} x2={chartW - padR} y2={chartData.avgY}
              stroke="#1D9E75" strokeWidth="1" strokeDasharray="5 3" opacity="0.7" />
            <text x={chartW - padR + 4} y={chartData.avgY + 3} fill="#1D9E75" fontSize="9" fontFamily={MONO}>avg</text>

            {/* Area fill */}
            <path d={areaPath} fill="url(#premGrad)" opacity="0.3" />
            <defs>
              <linearGradient id="premGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#D85A30" stopOpacity="0.6" />
                <stop offset="100%" stopColor="#D85A30" stopOpacity="0" />
              </linearGradient>
            </defs>

            {/* Line */}
            <polyline points={polyline} fill="none" stroke="#D85A30" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />

            {/* X labels (sparse) */}
            {chartData.points.filter((_, i) => i % Math.max(1, Math.floor(data.length / 8)) === 0).map((p) => (
              <text key={p.date} x={p.x} y={chartH - 4} textAnchor="middle" fill="#475569" fontSize="9" fontFamily={MONO}>{p.date}</text>
            ))}

            {/* Hover targets */}
            {chartData.points.map((p, i) => (
              <g key={i} onMouseEnter={() => setHoverIdx(i)} style={{ cursor: "crosshair" }}>
                <rect x={p.x - plotW / data.length / 2} y={padT} width={plotW / data.length} height={plotH} fill="transparent" />
                {hoverIdx === i && (
                  <>
                    <line x1={p.x} y1={padT} x2={p.x} y2={padT + plotH} stroke="#475569" strokeWidth="0.5" strokeDasharray="3 3" />
                    <circle cx={p.x} cy={p.y} r="4" fill="#D85A30" stroke="#0a0f1a" strokeWidth="2" />
                    <rect x={p.x - 44} y={p.y - 32} width="88" height="24" rx="4" fill="#1e293b" stroke="#334155" strokeWidth="0.5" />
                    <text x={p.x} y={p.y - 16} textAnchor="middle" fill="#e2e8f0" fontSize="11" fontFamily={MONO} fontWeight="600">
                      {p.date}: {p.premium >= 0 ? "+" : ""}{p.premium.toFixed(1)}%
                    </text>
                  </>
                )}
              </g>
            ))}
          </svg>
        </div>

        {/* ─── CSV Import ─── */}
        <div style={{ background: "#111827", border: "1px solid #1e293b", borderRadius: 12, padding: "16px 20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: showImport ? 12 : 0 }}>
            <div>
              <div style={{ fontSize: 12, color: "#64748b", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
                匯入自己的資料
              </div>
              <div style={{ fontSize: 11, color: "#475569", marginTop: 2 }}>
                執行 Python 腳本後，貼上 tsmc_adr_premium.csv 的內容
              </div>
            </div>
            <button onClick={() => setShowImport(!showImport)} style={{
              padding: "6px 14px", borderRadius: 6, border: "1px solid #334155",
              background: showImport ? "#334155" : "transparent", color: "#22d3ee",
              fontSize: 12, cursor: "pointer", fontFamily: FONT
            }}>
              {showImport ? "收起" : "匯入 CSV"}
            </button>
          </div>
          {showImport && (
            <div>
              <textarea
                value={csvInput}
                onChange={(e) => setCsvInput(e.target.value)}
                placeholder={"Date,TSM_Price_USD,2330TW_Price_TWD,USD_TWD_Rate,TSM_Implied_TWD,ADR_Premium_Pct\n2024-01-02,105.3,593.0,31.05,654.3,10.3\n..."}
                style={{
                  width: "100%", height: 120, padding: 10, borderRadius: 6,
                  border: "1px solid #334155", background: "#0f172a", color: "#e2e8f0",
                  fontFamily: MONO, fontSize: 11, resize: "vertical", boxSizing: "border-box"
                }}
              />
              <button onClick={handleImport} style={{
                marginTop: 8, padding: "8px 20px", borderRadius: 6, border: "none",
                background: "#22d3ee", color: "#0a0f1a", fontSize: 12, fontWeight: 600,
                cursor: "pointer", fontFamily: FONT
              }}>
                解析並更新圖表
              </button>
            </div>
          )}
        </div>

        {/* ─── 使用說明 ─── */}
        <div style={{ marginTop: 16, fontSize: 11, color: "#475569", lineHeight: 1.7, padding: "12px 16px", background: "#111827", border: "1px solid #1e293b", borderRadius: 10 }}>
          <strong style={{ color: "#fbbf24" }}>如何取得真實歷史資料：</strong>
          <br />1. 在本機執行 <code style={{ color: "#22d3ee", fontFamily: MONO }}>pip install yfinance pandas matplotlib</code>
          <br />2. 執行 <code style={{ color: "#22d3ee", fontFamily: MONO }}>python tsmc_adr_premium.py</code>（預設抓 5 年）或 <code style={{ color: "#22d3ee", fontFamily: MONO }}>python tsmc_adr_premium.py 10y</code>
          <br />3. 開啟產出的 <code style={{ color: "#22d3ee", fontFamily: MONO }}>tsmc_adr_premium.csv</code>，全選複製，貼到上方「匯入 CSV」區域
          <br />4. 點擊「解析並更新圖表」即可看到真實歷史走勢
          <br /><br />
          <strong style={{ color: "#fbbf24" }}>目前顯示的是近似歷史數據</strong>（月度粒度），匯入 CSV 後會更新為每日精確數據。
        </div>

        <div style={{ marginTop: 20, fontSize: 10, color: "#334155", textAlign: "center" }}>
          ADR Premium = (TSM ÷ 5 × USD/TWD − 2330.TW) ÷ 2330.TW
        </div>
      </div>
    </div>
  );
}
