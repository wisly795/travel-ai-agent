import React from "react";
import { timeText, TOOL_LABELS } from "../api.js";
import useStaffData from "./useStaffData.js";

export default function Turns({ hidden, staffApi, version, onError }) {
  const [turns] = useStaffData(staffApi, "/api/admin/turns", version, onError, []);
  return (
    <div id="view-turns" className="panel view" hidden={hidden}>
      <h2>AI 對話紀錄</h2>
      <p className="hint">每次提問的回答、使用的工具與花費，點開可看工具的輸入和結果，方便查錯。</p>
      <div id="turn-list">
        {!turns.length && <p>還沒有 AI 對話。</p>}
        {turns.map((turn) => (
          <details key={turn.id} className="turn">
            <summary>{`#${turn.id}　${timeText(turn.created_at)}　客人：${turn.user_message}`}</summary>
            <p className="policy-text">{`AI：${turn.reply}`}</p>
            <small>
              {`工具：${turn.tools.map((t) => TOOL_LABELS[t.tool] || t.tool).join("、") || "無"}｜模型 ${turn.model}｜US$ ${Number(turn.cost_usd).toFixed(5)}`}
            </small>
            {turn.agent_path && (
              <pre className="tool-log">{`多 Agent 流程\n${turn.agent_path.map((step) => `${step.agent}：${step.detail}`).join("\n")}`}</pre>
            )}
            {turn.tools.map((t, i) => (
              <pre key={i} className="tool-log">
                {`${t.is_error ? "⚠ " : ""}${t.agent ? `［${t.agent}］` : ""}${t.tool}\n輸入：${JSON.stringify(t.input)}\n結果：${JSON.stringify(t.output).slice(0, 600)}`}
              </pre>
            ))}
          </details>
        ))}
      </div>
    </div>
  );
}
