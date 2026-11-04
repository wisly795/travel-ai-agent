import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api, loadSession, makeStaffApi, postJson, storeSession } from "../api.js";
import Admin from "./Admin.jsx";
import Dashboard from "./Dashboard.jsx";
import Erp from "./Erp.jsx";
import Evals from "./Evals.jsx";
import Handoffs from "./Handoffs.jsx";
import Notifications from "./Notifications.jsx";
import Procurement from "./Procurement.jsx";
import Quotes from "./Quotes.jsx";
import Turns from "./Turns.jsx";
import Usage from "./Usage.jsx";

const VIEWS = [
  ["view-dashboard", "儀表板"],
  ["view-notifications", "通知"],
  ["view-quotes", "報價"],
  ["view-turns", "AI 對話紀錄"],
  ["view-handoffs", "轉接單"],
  ["view-erp", "ERP 同步"],
  ["view-procurement", "採購"],
  ["view-evals", "AI 評測"],
];

export default function Staff({ hidden, onError }) {
  const [session, setSession] = useState(loadSession);
  const [login, setLogin] = useState({ username: "", password: "" });

  const save = useCallback((value) => { storeSession(value); setSession(value); }, []);
  // 要用固定的函式：每次畫面更新都換新函式的話，各分頁會以為設定變了而一直重新載入
  const expire = useCallback(() => save(null), [save]);

  async function submit(event) {
    event.preventDefault();
    onError("");
    try {
      save(await postJson("/api/auth/login", login));
      setLogin((value) => ({ ...value, password: "" }));
    } catch (error) {
      onError(error.message);
    }
  }

  async function logout() {
    await api("/api/auth/logout", { method: "POST", headers: { Authorization: `Bearer ${session.token}` } }).catch(() => {});
    save(null);
    onError("");
  }

  return (
    <section id="staff" hidden={hidden}>
      <form id="staff-form" className="panel" hidden={!!session} onSubmit={submit}>
        <h2>後台登入</h2>
        <div className="fields">
          <label>帳號<input id="login-username" autoComplete="username" required value={login.username}
                          onChange={(e) => setLogin({ ...login, username: e.target.value })} /></label>
          <label>密碼<input id="login-password" type="password" autoComplete="current-password" required
                          value={login.password} onChange={(e) => setLogin({ ...login, password: e.target.value })} /></label>
        </div>
        <button type="submit">登入</button>
      </form>
      {session && <StaffHome session={session} onLogout={logout} onExpired={expire} onError={onError} />}
    </section>
  );
}

function StaffHome({ session, onLogout, onExpired, onError }) {
  const [view, setView] = useState("view-dashboard");
  const [version, setVersion] = useState(0);
  const [unread, setUnread] = useState(0);
  const [ready, setReady] = useState(false);
  const staffApi = useMemo(() => makeStaffApi(session, onExpired), [session, onExpired]);
  const isAdmin = session.user.role === "管理員";

  // 每個分頁各自載入資料；做完一個動作就把 version 加 1，全部分頁重新載入（和原本 refreshStaff 一樣）
  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  const action = useCallback(async (work) => {
    onError("");
    try {
      await work();
      refresh();
    } catch (error) {
      onError(error.message);
    }
  }, [onError, refresh]);

  // 先確認登入還有效，才顯示後台（登入過期就回到登入畫面）
  useEffect(() => {
    staffApi("/api/admin/usage").then(() => setReady(true)).catch((error) => onError(error.message));
  }, [staffApi]);

  const ctx = { staffApi, action, refresh, version, session, onError };
  return (
    <div id="staff-result" hidden={!ready}>
      <div className="row whoami">
        <span id="whoami">{`目前登入：${session.user.display_name}（${session.user.role}）`}</span>
        <button id="logout" className="ghost" type="button" onClick={onLogout}>登出</button>
      </div>
      <Usage {...ctx} />
      <nav className="subnav">
        {VIEWS.map(([id, label]) => (
          <button key={id} type="button" data-view={id} className={`subtab${view === id ? " active" : ""}`}
                  onClick={() => setView(id)}>
            {label}{id === "view-notifications" && <> <span id="unread">{unread ? `(${unread})` : ""}</span></>}
          </button>
        ))}
        <button id="subtab-users" type="button" data-view="view-users" hidden={!isAdmin}
                className={`subtab${view === "view-users" ? " active" : ""}`} onClick={() => setView("view-users")}>系統管理</button>
      </nav>
      <Evals {...ctx} hidden={view !== "view-evals"} />
      {isAdmin && <Admin {...ctx} hidden={view !== "view-users"} />}
      <Dashboard {...ctx} hidden={view !== "view-dashboard"} />
      <Notifications {...ctx} hidden={view !== "view-notifications"} onUnread={setUnread} />
      <Procurement {...ctx} hidden={view !== "view-procurement"} />
      <Quotes {...ctx} hidden={view !== "view-quotes"} />
      <Turns {...ctx} hidden={view !== "view-turns"} />
      <Handoffs {...ctx} hidden={view !== "view-handoffs"} />
      <Erp {...ctx} hidden={view !== "view-erp"} />
    </div>
  );
}
