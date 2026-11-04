import React from "react";
import { money, timeText } from "../api.js";
import { Bars, Columns, Share } from "../charts/Charts.jsx";
import useStaffData from "./useStaffData.js";

const day = (row) => row.day.slice(5).replace("-", "/");

export default function Dashboard({ hidden, staffApi, version, onError }) {
  const [data] = useStaffData(staffApi, "/api/admin/dashboard?days=14", version, onError);
  if (!data) return <div id="view-dashboard" className="view" hidden={hidden}><div id="kpis" className="stats kpis" /></div>;

  const s = data.summary;
  const kpis = [
    ["近 30 天報價", `${s.quotes} 張`, `AI 客服 ${s.ai_quotes} 張`],
    ["成交", `${s.deals} 張`, `成交率 ${(s.conversion_rate * 100).toFixed(0)}%`],
    ["成交金額", money(s.deal_amount), "近 30 天"],
    ["AI 花費", `US$ ${s.ai_cost_usd.toFixed(2)}`, `${s.ai_turns} 次對話`],
    ["待處理", `${s.pending_approvals + s.erp_failed + s.open_handoffs} 件`,
      `待核准 ${s.pending_approvals}｜ERP 失敗 ${s.erp_failed}｜轉接 ${s.open_handoffs}`],
    ["AI 評測", data.eval ? `${data.eval.passed} / ${data.eval.total} 題` : "尚未執行",
      data.eval ? `${Math.round((data.eval.passed / data.eval.total) * 100)}%｜${timeText(data.eval.finished_at)}` : "到「AI 評測」分頁執行"],
  ];
  const bySource = Object.fromEntries(data.sources.map((r) => [r.source, r.quotes]));

  return (
    <div id="view-dashboard" className="view" hidden={hidden}>
      <div id="kpis" className="stats kpis">
        {kpis.map(([label, value, note]) => (
          <div key={label} className="stat"><small>{label}</small><strong>{value}</strong><span className="stat-note">{note}</span></div>
        ))}
      </div>
      <div className="dash-grid">
        <section className="panel">
          <h3>每日成交金額（近 14 天）</h3>
          <div id="chart-deals"><Columns rows={data.daily} value={(r) => r.deal_amount} label={day} format={money} tipLabel="成交金額" /></div>
        </section>
        <section className="panel">
          <h3>每日報價數（近 14 天）</h3>
          <div id="chart-quotes"><Columns rows={data.daily} value={(r) => r.quotes} label={day} format={(v) => `${v} 張`} tipLabel="報價數" /></div>
        </section>
        <section className="panel">
          <h3>熱門行程（近 30 天報價數）</h3>
          <div id="chart-packages"><Bars rows={data.top_packages} name={(r) => r.name} value={(r) => r.quotes} format={(v) => `${v} 張`} unit="報價數" /></div>
        </section>
        <section className="panel">
          <h3>報價來源（近 30 天）</h3>
          <div id="chart-sources">
            <Share parts={[{ name: "網頁", value: bySource.web || 0 }, { name: "AI 客服", value: bySource.ai || 0 },
              { name: "官網串接", value: bySource.partner || 0 }]} />
          </div>
          <h3 className="sub">AI 每日花費（美元，近 14 天）</h3>
          <div id="chart-ai"><Columns rows={data.daily} value={(r) => r.ai_cost_usd} label={day} format={(v) => `US$ ${v.toFixed(4)}`} tipLabel="AI 花費" /></div>
        </section>
      </div>
    </div>
  );
}
