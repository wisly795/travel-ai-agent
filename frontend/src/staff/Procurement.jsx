import React, { useState } from "react";
import { money } from "../api.js";
import useStaffData from "./useStaffData.js";

export default function Procurement({ hidden, staffApi, action, version, session, onError }) {
  const [items] = useStaffData(staffApi, "/api/procurement", version, onError, []);
  const [analyzing, setAnalyzing] = useState(null);

  async function decide(item, approve) {
    let reason = "";
    if (!approve) {
      reason = window.prompt("退回原因（必填）") || "";
      if (!reason.trim()) return;
    }
    if (item.approver_role === "主管" && session.user.role !== "主管") {
      onError("這張採購單需要主管核准或退回，請用主管帳號登入");
      return;
    }
    await action(() => staffApi(`/api/purchase-orders/${item.po_id}/decision`, {
      method: "POST", body: JSON.stringify({ approve, reason }),
    }));
  }

  async function analyze(id) {
    setAnalyzing(id);
    await action(() => staffApi(`/api/procurement/${id}/analyze`, { method: "POST" }));
    setAnalyzing(null);
  }

  return (
    <div id="view-procurement" className="panel view" hidden={hidden}>
      <h2>採購（向供應商訂房）</h2>
      <p className="hint">報價成交後自動產生請購單。AI 比價並建立草稿，由人核准後才會下單；金額達門檻或超出預算需要主管帳號核准。</p>
      <div id="procurement-list">
        {!items.length && <p>還沒有請購單。把報價改成「成交」就會產生。</p>}
        {items.map((item) => (
          <article key={item.id} className="pr-card">
            <h3>{`請購單 #${item.id}｜報價 #${item.quote_id} ${item.customer_name}｜${item.status}`}</h3>
            <p>{`${item.hotel}：${item.rooms} 間 × ${item.nights} 晚，住宿預算 ${money(item.budget)}｜出發日 ${item.departure_date || "未填"}`}</p>
            {item.ai_analysis && <p className="policy-text ai-note">{`AI 比價：${item.ai_analysis}`}</p>}
            {item.po_id && (
              <div className="po-box">
                <strong>{`採購單 #${item.po_id}：${item.supplier} ${money(item.amount)}｜${item.po_status}`}</strong>
                <small>
                  {`${item.over_budget ? "超出預算，" : ""}需要${item.approver_role}核准`
                    + (item.decided_by ? `｜處理人：${item.decided_by}` : "")
                    + (item.confirmation_no ? `｜供應商確認編號 ${item.confirmation_no}` : "")
                    + (item.reject_reason ? `｜退回原因：${item.reject_reason}` : "")
                    + (item.last_error ? `｜錯誤：${item.last_error}` : "")}
                </small>
                {item.po_status === "待核准" && (
                  <>
                    <button type="button" className="small-btn" onClick={() => decide(item, true)}>核准並下單</button>
                    <button type="button" className="small-btn ghost" onClick={() => decide(item, false)}>退回</button>
                  </>
                )}
                {item.po_status === "下單失敗" && (
                  <button type="button" className="small-btn" onClick={() => action(() => staffApi(`/api/purchase-orders/${item.po_id}/retry`, { method: "POST" }))}>重送</button>
                )}
              </div>
            )}
            {item.status === "待比價" && (
              <button type="button" className="small-btn" disabled={analyzing === item.id} onClick={() => analyze(item.id)}>
                {analyzing === item.id ? "AI 比價中…" : "AI 比價"}
              </button>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
