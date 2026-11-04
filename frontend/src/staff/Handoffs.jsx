import React from "react";
import { timeText } from "../api.js";
import useStaffData from "./useStaffData.js";

export default function Handoffs({ hidden, staffApi, action, version, onError }) {
  const [items] = useStaffData(staffApi, "/api/handoffs", version, onError, []);
  return (
    <div id="view-handoffs" className="panel view" hidden={hidden}>
      <h2>轉接單</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>編號</th><th>原因</th><th>建立時間</th><th>狀態</th><th>操作</th></tr></thead>
          <tbody id="handoff-rows">
            {items.map((item) => {
              const next = item.status === "待處理" ? "已處理" : "待處理";
              return (
                <tr key={item.id}>
                  <td>{item.id}</td><td>{item.reason}</td><td>{timeText(item.created_at)}</td><td>{item.status}</td>
                  <td>
                    <button type="button" className="small-btn" onClick={() => action(() => staffApi(`/api/handoffs/${item.id}`, {
                      method: "PATCH", body: JSON.stringify({ status: next }),
                    }))}>{`標為${next}`}</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
