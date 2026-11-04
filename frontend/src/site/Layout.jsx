import React, { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../api.js";
import Chat from "../Chat.jsx";
import { SOURCE_NOTE } from "./destinations.js";

const NAV = [["/", "首頁"], ["/tours", "精選行程"], ["/explore", "探索台灣"], ["/guide", "旅遊須知"]];

export default function Layout() {
  const [chatOpen, setChatOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [status, setStatus] = useState(null);
  const location = useLocation();

  useEffect(() => { api("/api/chat/status").then(setStatus).catch(() => setStatus({ enabled: false })); }, []);
  // 換頁時回到頁面頂端、收起手機選單
  useEffect(() => { window.scrollTo(0, 0); setMenuOpen(false); }, [location.pathname]);

  return (
    <div className="site">
      <header className="s-nav">
        <div className="s-container s-nav-inner">
          <Link to="/" className="s-logo" aria-label="晴空旅遊首頁">
            <span className="s-logo-mark" aria-hidden="true" />晴空旅遊
          </Link>
          <button type="button" className="s-menu-btn" aria-label="選單" aria-expanded={menuOpen}
                  onClick={() => setMenuOpen(!menuOpen)}>☰</button>
          <nav className={`s-links${menuOpen ? " open" : ""}`}>
            {NAV.map(([to, label]) => (
              <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>{label}</NavLink>
            ))}
            <Link to="/admin" className="s-staff-link">業務登入</Link>
          </nav>
        </div>
      </header>

      <Outlet context={{ openChat: () => setChatOpen(true) }} />

      <footer className="s-footer">
        <div className="s-container s-footer-grid">
          <div>
            <p className="s-logo s-logo-footer"><span className="s-logo-mark" aria-hidden="true" />晴空旅遊</p>
            <p>求職作品展示網站。行程、價格、飯店、供應商皆為模擬資料，非真實報價。</p>
          </div>
          <div>
            <p className="s-footer-title">資料來源</p>
            <p>{SOURCE_NOTE}</p>
            <p>供應商參考價：模擬比價網站，由本系統爬蟲每日更新。</p>
          </div>
        </div>
      </footer>

      {/* AI 客服：右下角聊天泡泡，點開才顯示對話視窗；對話內容在關閉後保留 */}
      <div className={`s-chat${chatOpen ? " open" : ""}`} aria-hidden={!chatOpen}>
        <div className="s-chat-head">
          <strong>AI 旅遊顧問</strong>
          <button type="button" aria-label="關閉對話" onClick={() => setChatOpen(false)}>×</button>
        </div>
        <Chat hidden={false} status={status} />
      </div>
      <button type="button" className="s-chat-fab" aria-label="開啟 AI 客服" onClick={() => setChatOpen(!chatOpen)}>
        {chatOpen ? "×" : "問 AI"}
      </button>
    </div>
  );
}
