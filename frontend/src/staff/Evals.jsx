import React, { useEffect, useState } from "react";
import { timeText } from "../api.js";
import useStaffData from "./useStaffData.js";

export default function Evals({ hidden, staffApi, action, version, session, onError }) {
  const [tick, setTick] = useState(0);
  const [data] = useStaffData(staffApi, "/api/admin/evals", `${version}-${tick}`, onError);
  const isAdmin = session.user.role === "管理員";
  const running = data?.running;

  // 執行中每 10 秒只更新這一頁，跑完自動停止
  useEffect(() => {
    if (!running) return undefined;
    const timer = setTimeout(() => setTick((t) => t + 1), 10000);
    return () => clearTimeout(timer);
  }, [running, data]);

  const run = (mode) => action(() => staffApi("/api/admin/evals/run", { method: "POST", body: JSON.stringify({ mode }) }));
  const latest = data?.latest;

  return (
    <div id="view-evals" className="panel view" hidden={hidden}>
      <div className="row">
        <h2>AI 自動評測</h2>
        <div className="toolbar">
          <button id="eval-run" type="button" hidden={!isAdmin} disabled={running} onClick={() => run("single")}>
            {running ? "評測執行中…" : "執行評測（約 2 分鐘）"}
          </button>
          <button id="eval-run-multi" className="ghost" type="button" hidden={!isAdmin} disabled={running}
                  onClick={() => run("multi")}>評測多 Agent 版</button>
        </div>
      </div>
      <p className="hint">20 題標準問答，用程式規則自動評分：金額是否正確、是否附條文出處、是否用對工具、該拒絕時是否拒絕、稱謂是否正確。改 AI 規則或換模型前後各跑一次，用數字確認有沒有變好。只有管理員能執行。</p>
      <div id="eval-summary" className="stats">
        {data && !latest && <p>還沒有評測紀錄。</p>}
        {latest && [
          ["總分", `${latest.passed} / ${latest.total}`, `${Math.round((latest.passed / latest.total) * 100)}%｜${latest.model}`],
          ...latest.by_category.map((c) => [c.category, `${c.passed} / ${c.total}`, ""]),
        ].map(([label, value, note]) => (
          <div key={label} className="stat">
            <small>{label}</small><strong>{value}</strong>{note && <span className="stat-note">{note}</span>}
          </div>
        ))}
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>題號</th><th>類別</th><th>問題</th><th>結果</th><th>沒通過的原因</th></tr></thead>
          <tbody id="eval-rows">
            {latest?.results.map((r) => (
              // 不用表情符號：有些電腦沒有表情字型會顯示成方框
              <tr key={r.case_id} title={`AI 回答：${r.reply}`}>
                <td>{r.case_id}</td><td>{r.category}</td><td>{r.question}</td>
                <td className={r.passed ? "pass" : "fail"}>{r.passed ? "通過" : "未通過"}</td>
                <td>{r.failures.join("；")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>歷次評測</h3>
      <div className="table-wrap">
        <table>
          <thead><tr><th>時間</th><th>說明</th><th>模型</th><th>分數</th><th>花費</th></tr></thead>
          <tbody id="eval-history">
            {data?.history.map((h) => (
              <tr key={h.id}>
                <td>{timeText(h.started_at)}</td><td>{h.label}</td><td>{h.model}</td>
                <td>{h.status === "完成" ? `${h.passed} / ${h.total}` : h.status}</td><td>{`US$ ${h.cost_usd.toFixed(4)}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
