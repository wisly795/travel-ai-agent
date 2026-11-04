import React from "react";
import { money, SOURCE_LABELS } from "../api.js";
import useStaffData from "./useStaffData.js";

export default function Quotes({ hidden, staffApi, action, version, session, onError }) {
  const [quotes] = useStaffData(staffApi, "/api/quotes", version, onError, []);

  const setStatus = (id, status) => action(() => staffApi(`/api/quotes/${id}/status`, {
    method: "PATCH", body: JSON.stringify({ status }),
  }));

  async function exportCsv() {
    onError("");
    const response = await fetch("/api/quotes/export.csv", { headers: { Authorization: `Bearer ${session.token}` } });
    if (!response.ok) {
      onError("下載失敗，請重新登入");
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = "quotes.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div id="view-quotes" className="panel view" hidden={hidden}>
      <div className="row">
        <h2>報價紀錄</h2>
        <button id="export" type="button" onClick={exportCsv}>下載 CSV</button>
      </div>
      <p className="hint">改成「成交」會自動把訂單送到 ERP。</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>編號</th><th>客人</th><th>行程</th><th>飯店</th><th>人數</th><th>出發日</th><th>總價</th><th>來源</th><th>狀態</th><th>ERP</th><th>操作</th></tr>
          </thead>
          <tbody id="quote-rows">
            {quotes.map((q) => (
              <tr key={q.id}>
                <td>{q.id}</td><td>{q.customer_name}</td><td>{q.package}</td><td>{q.hotel}</td><td>{q.people}</td>
                <td>{q.departure_date || "—"}</td><td>{money(q.total_price)}</td>
                <td>{SOURCE_LABELS[q.source] || q.source}</td><td>{q.status}</td>
                <td>{q.erp_status ? `${q.erp_status}${q.erp_order_no ? `（${q.erp_order_no}）` : ""}` : "—"}</td>
                <td>
                  {q.status === "已報價" && <button type="button" className="small-btn" onClick={() => setStatus(q.id, "成交")}>成交</button>}
                  {q.status !== "取消" && <button type="button" className="small-btn ghost" onClick={() => setStatus(q.id, "取消")}>取消</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
