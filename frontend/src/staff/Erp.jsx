import React from "react";
import { money } from "../api.js";
import useStaffData from "./useStaffData.js";

export default function Erp({ hidden, staffApi, action, version, onError }) {
  const [health] = useStaffData(staffApi, "/api/erp/status", version, onError);
  const [syncs] = useStaffData(staffApi, "/api/erp/syncs", version, onError, []);
  const post = (path, body) => action(() => staffApi(path, { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) }));

  return (
    <div id="view-erp" className="panel view" hidden={hidden}>
      <div className="row">
        <h2>ERP 同步</h2>
        <span id="erp-health" className="hint">
          {health && (health.status !== "ok" ? "ERP 連線：無法連線"
            : `ERP 連線：${health.fail_mode ? "維修中（模擬故障）" : "正常"}`)}
        </span>
      </div>
      <div className="toolbar">
        <button id="erp-retry-all" type="button" onClick={() => post("/api/erp/retry-failed")}>重送全部失敗</button>
        <button id="erp-fail-on" className="ghost" type="button" onClick={() => post("/api/erp/fail-mode", { on: true })}>模擬 ERP 故障</button>
        <button id="erp-fail-off" className="ghost" type="button" onClick={() => post("/api/erp/fail-mode", { on: false })}>恢復 ERP</button>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>報價</th><th>客人</th><th>金額</th><th>結果</th><th>ERP 單號</th><th>次數</th><th>錯誤訊息</th><th>操作</th></tr></thead>
          <tbody id="erp-rows">
            {syncs.map((s) => (
              <tr key={s.quote_id}>
                <td>{`#${s.quote_id}`}</td><td>{s.customer_name}</td><td>{money(s.total_price)}</td><td>{s.status}</td>
                <td>{s.erp_order_no || "—"}</td><td>{s.attempts}</td><td>{s.last_error || ""}</td>
                <td>
                  {s.status === "失敗" && (
                    <button type="button" className="small-btn" onClick={() => post(`/api/erp/syncs/${s.quote_id}/retry`)}>重送</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
