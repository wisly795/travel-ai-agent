import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import Chat from "./Chat.jsx";
import Customer from "./Customer.jsx";
import Policy from "./Policy.jsx";
import Staff from "./staff/Staff.jsx";

const TABS = [
  ["chat", "AI 客服"],
  ["customer", "查行程"],
  ["policy", "旅遊規定"],
  ["staff", "業務後台"],
];

export default function App() {
  const [tab, setTab] = useState(null);
  const [message, setMessage] = useState("");
  const [chatStatus, setChatStatus] = useState(null);

  // AI 客服有啟用就預設打開 AI 客服，否則打開查行程
  useEffect(() => {
    api("/api/chat/status")
      .then((status) => { setChatStatus(status); setTab((current) => current || (status.enabled ? "chat" : "customer")); })
      .catch(() => setTab((current) => current || "customer"));
  }, []);

  const choose = (name) => { setTab(name); setMessage(""); };

  return (
    <>
      <header>
        <h1>旅遊行程報價系統</h1>
        <p className="demo">模擬資料，非真實報價</p>
        <nav>
          {TABS.map(([name, label]) => (
            <button key={name} id={`tab-${name}`} type="button" className={`tab${tab === name ? " active" : ""}`}
                    onClick={() => choose(name)}>{label}</button>
          ))}
        </nav>
      </header>
      <main>
        {/* 四個分頁都保持掛載，切換分頁時對話與查詢結果不會不見 */}
        <Chat hidden={tab !== "chat"} status={chatStatus} />
        <Customer hidden={tab !== "customer"} onError={setMessage} />
        <Policy hidden={tab !== "policy"} onError={setMessage} />
        <Staff hidden={tab !== "staff"} onError={setMessage} />
        <p id="message" className="message" role="alert" hidden={!message}>{message}</p>
      </main>
    </>
  );
}
