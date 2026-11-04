// 儀表板的小型圖表：純 SVG／HTML，不依賴外部圖表套件（安裝版離線也能顯示）。
// 規格：柱子最寬 24px、頂端 4px 圓角、細格線、文字用文字色（不用資料色）、滑過顯示提示、每張圖附數據表格。
import React, { useState } from "react";

// 滑過提示：固定定位，跟著滑鼠
export function useTip() {
  const [tip, setTip] = useState(null);
  const bind = (text) => ({
    onPointerMove: (event) => setTip({ text, x: Math.min(event.clientX + 12, window.innerWidth - 220), y: event.clientY - 36 }),
    onPointerLeave: () => setTip(null),
  });
  const view = <div className="chart-tip" hidden={!tip} style={tip ? { left: tip.x, top: tip.y } : undefined}>{tip?.text}</div>;
  return [bind, view];
}

// 刻度取整數：0、一半、最大值往上取整
export function niceMax(value) {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / power) * power;
}

export function compact(value) {
  if (value >= 1e6) return `${(value / 1e6).toFixed(1).replace(/\.0$/, "")}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1).replace(/\.0$/, "")}K`;
  return String(Math.round(value * 100) / 100);
}

function DataTable({ headers, rows }) {
  return (
    <details className="chart-table">
      <summary>看數據表格</summary>
      <table>
        <thead><tr>{headers.map((h) => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody>
      </table>
    </details>
  );
}

// 直條圖：每天一根，單一數列（標題說明數列，不需要圖例）
export function Columns({ rows, value, label, format, tipLabel }) {
  const [bind, tipView] = useTip();
  const width = 640, height = 220, left = 44, right = 12, top = 16, bottom = 28;
  let max = niceMax(Math.max(...rows.map(value), 0));
  // 張數這類整數資料，中間刻度也要是整數（避免出現 2.5 張）
  if (rows.every((row) => Number.isInteger(value(row))) && max % 2) max += 1;
  const plotW = width - left - right, plotH = height - top - bottom;
  const band = plotW / Math.max(rows.length, 1);
  const barW = Math.min(24, band * 0.6);
  const every = Math.ceil(rows.length / 7);
  return (
    <>
      <svg viewBox={`0 0 ${width} ${height}`} className="chart" role="img" aria-label={tipLabel}>
        {[0, 0.5, 1].map((ratio) => {
          const y = top + plotH * (1 - ratio);
          return (
            <g key={ratio}>
              <line x1={left} x2={width - right} y1={y} y2={y} className={ratio === 0 ? "axis" : "grid"} />
              <text x={left - 6} y={y + 4} className="tick" textAnchor="end">{compact(max * ratio)}</text>
            </g>
          );
        })}
        {rows.map((row, i) => {
          const v = value(row);
          const h = (v / max) * plotH;
          const x = left + band * i + (band - barW) / 2;
          const y = top + plotH - h;
          const r = Math.min(4, h, barW / 2);
          return (
            <g key={i}>
              {h > 0 && (
                <path className="bar"
                      d={`M${x},${top + plotH} V${y + r} Q${x},${y} ${x + r},${y} H${x + barW - r} Q${x + barW},${y} ${x + barW},${y + r} V${top + plotH} Z`} />
              )}
              {(i % every === 0 || i === rows.length - 1) && (
                <text x={x + barW / 2} y={height - 8} className="tick" textAnchor="middle">{label(row)}</text>
              )}
              {/* 滑鼠感應區比柱子大（整個欄位） */}
              <rect x={left + band * i} y={top} width={band} height={plotH} className="hit"
                    {...bind(`${label(row)}｜${tipLabel}：${format(v)}`)} />
            </g>
          );
        })}
      </svg>
      {tipView}
      <DataTable headers={["日期", tipLabel]} rows={rows.map((row) => [label(row), format(value(row))])} />
    </>
  );
}

// 橫條圖：熱門行程，數值寫在條的尾端
export function Bars({ rows, name, value, format, unit }) {
  const [bind, tipView] = useTip();
  const max = Math.max(...rows.map(value), 1);
  return (
    <>
      <div className="hbars">
        {!rows.length && "近 30 天沒有資料。"}
        {rows.map((row) => (
          <div key={name(row)} className="hbar-row" {...bind(`${name(row)}：${format(value(row))}`)}>
            <span className="hbar-label">{name(row)}</span>
            <span className="hbar-track">
              <span className="hbar" style={{ width: `${(value(row) / max) * 100}%` }} />
              <span className="hbar-value">{format(value(row))}</span>
            </span>
          </div>
        ))}
      </div>
      {tipView}
      <DataTable headers={["行程", unit]} rows={rows.map((row) => [name(row), format(value(row))])} />
    </>
  );
}

// 比例條：兩類以上，色塊之間留 2px 間隔，並附圖例（顏色不是唯一的辨識方式）
export function Share({ parts }) {
  const [bind, tipView] = useTip();
  const total = parts.reduce((sum, p) => sum + p.value, 0);
  const pct = (v) => (total ? Math.round((v / total) * 100) : 0);
  return (
    <>
      <div className="share-bar">
        {!total && "近 30 天沒有資料。"}
        {parts.map((part, i) => part.value > 0 && (
          <span key={part.name} className={`share-seg series-${i + 1}`} style={{ flexGrow: part.value }}
                {...bind(`${part.name}：${part.value}（${pct(part.value)}%）`)} />
        ))}
      </div>
      <div className="legend">
        {parts.map((part, i) => (
          <span key={part.name} className="legend-item">
            <i className={`swatch series-${i + 1}`} />{`${part.name} ${part.value}（${pct(part.value)}%）`}
          </span>
        ))}
      </div>
      {tipView}
      <DataTable headers={["來源", "報價數", "比例"]} rows={parts.map((p) => [p.name, p.value, `${pct(p.value)}%`])} />
    </>
  );
}
