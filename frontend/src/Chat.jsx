import React, { useEffect, useRef, useState } from "react";
import { postJson, TOOL_LABELS } from "./api.js";

const GREETING = "您好，我是 AI 客服。可以告訴我想去哪裡、幾個人、每人預算，我幫您查行程和報價。";
const EXAMPLES = ["4 個人想去沖繩，每人預算 3 萬", "京都有哪些行程？", "出發前取消可以退多少？"];

export default function Chat({ hidden, status }) {
  const [mode, setMode] = useState("single");
  const [conversationId, setConversationId] = useState(null);
  const [bubbles, setBubbles] = useState([{ role: "ai", text: GREETING }]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const lastRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { lastRef.current?.scrollIntoView({ block: "nearest" }); }, [bubbles]);

  function newConversation() {
    setConversationId(null);
    setBubbles([{ role: "ai", text: GREETING }]);
  }

  // 兩種模式的對話紀錄格式不同，切換時開新對話
  function changeMode(value) {
    setMode(value);
    newConversation();
  }

  async function send(text) {
    setBubbles((list) => [...list, { role: "user", text }, { role: "ai waiting", text: "查詢中…" }]);
    setInput("");
    setBusy(true);
    let answer;
    try {
      const data = await postJson("/api/chat", { conversation_id: conversationId, message: text, mode });
      setConversationId(data.conversation_id);
      const notes = [];
      if (data.agents) notes.push(`經過：${data.agents.map((step) => step.agent).join(" → ")}`);
      if (data.tools_used.length) {
        notes.push(`使用工具：${[...new Set(data.tools_used.map((name) => TOOL_LABELS[name] || name))].join("、")}`);
      }
      answer = { role: "ai", text: data.reply, notes };
    } catch (error) {
      answer = { role: "error", text: error.message };
    }
    setBubbles((list) => [...list.slice(0, -1), answer]);
    setBusy(false);
    setTimeout(() => inputRef.current?.focus());
  }

  function submit(event) {
    event.preventDefault();
    const text = input.trim();
    if (text) send(text);
  }

  const started = bubbles.length > 1;
  return (
    <section id="chat" hidden={hidden}>
      <div className="panel">
        <div className="row">
          <h2>AI 客服</h2>
          <button id="chat-new" className="ghost" type="button" onClick={newConversation}>新對話</button>
        </div>
        <p id="chat-status" className="hint">
          {status && (status.enabled
            ? `由 Claude（${status.model}）回答，價格一律由系統計算。`
            : "AI 客服尚未啟用（還沒設定 API 金鑰），可以先用「查行程」。")}
        </p>
        <fieldset className="mode-switch">
          <legend>客服模式</legend>
          <label><input type="radio" name="chat-mode" value="single" checked={mode === "single"}
                        onChange={() => changeMode("single")} /> 單一 Agent</label>
          <label><input type="radio" name="chat-mode" value="multi" checked={mode === "multi"}
                        onChange={() => changeMode("multi")} /> 多 Agent 協作（分流＋專員＋檢查員）</label>
        </fieldset>
        <div id="chat-log" className="chat-log" aria-live="polite">
          {bubbles.map((bubble, i) => (
            <div key={i} className={`bubble ${bubble.role}`} ref={i === bubbles.length - 1 ? lastRef : null}>
              {bubble.text}
              {bubble.notes?.map((note) => <small key={note}>{note}</small>)}
            </div>
          ))}
        </div>
        <div id="chat-examples" className="examples" hidden={started}>
          {EXAMPLES.map((text) => (
            <button key={text} type="button" className="chip" onClick={() => send(text)}>{text}</button>
          ))}
        </div>
        <form id="chat-form" className="chat-form" onSubmit={submit}>
          <input id="chat-input" ref={inputRef} maxLength={500} autoComplete="off" required disabled={busy}
                 value={input} onChange={(event) => setInput(event.target.value)}
                 placeholder="輸入問題，例如：2 個人去首爾 4 天多少錢？" aria-label="輸入問題" />
          <button type="submit" disabled={busy}>送出</button>
        </form>
      </div>
    </section>
  );
}
