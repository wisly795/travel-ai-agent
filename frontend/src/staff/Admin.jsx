import React, { useState } from "react";
import { timeText } from "../api.js";
import useStaffData from "./useStaffData.js";

const EMPTY_USER = { username: "", display_name: "", role: "業務", password: "" };

export default function Admin({ hidden, staffApi, action, version, session, onError }) {
  const [users] = useStaffData(staffApi, "/api/admin/users", version, onError, []);
  const [events] = useStaffData(staffApi, "/api/admin/login-events", version, onError, []);
  const [partners] = useStaffData(staffApi, "/api/admin/partners", version, onError, { partners: [], recent_calls: [] });
  const [newUser, setNewUser] = useState(EMPTY_USER);
  const [newPartner, setNewPartner] = useState({ name: "", limit: "30" });
  const [createdKey, setCreatedKey] = useState(null);

  const patch = (path, body) => action(() => staffApi(path, { method: "PATCH", body: JSON.stringify(body) }));

  function resetPassword(user) {
    const password = window.prompt(`輸入 ${user.username} 的新密碼（至少 8 碼，英文加數字）`) || "";
    if (password) patch(`/api/admin/users/${user.id}`, { password });
  }

  function createUser(event) {
    event.preventDefault();
    action(async () => {
      await staffApi("/api/admin/users", { method: "POST", body: JSON.stringify(newUser) });
      setNewUser(EMPTY_USER);
    });
  }

  function createPartner(event) {
    event.preventDefault();
    action(async () => {
      const created = await staffApi("/api/admin/partners", {
        method: "POST", body: JSON.stringify({ name: newPartner.name, rate_limit_per_minute: Number(newPartner.limit) }),
      });
      setCreatedKey(created);
      setNewPartner({ name: "", limit: "30" });
    });
  }

  const field = (setter, key) => (event) => setter((value) => ({ ...value, [key]: event.target.value }));

  return (
    <div id="view-users" className="panel view" hidden={hidden}>
      <h2>系統管理：帳號</h2>
      <p className="hint">只有管理員看得到。密碼以加鹽雜湊存放；連續錯 5 次鎖定 15 分鐘；停用或重設密碼會讓該帳號立即登出。</p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>帳號</th><th>名稱</th><th>角色</th><th>狀態</th><th>最後登入</th><th>操作</th></tr></thead>
          <tbody id="user-rows">
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.username}</td><td>{user.display_name}</td><td>{user.role}</td>
                <td>{!user.is_active ? "已停用" : user.locked ? "鎖定中" : "正常"}</td>
                <td>{user.last_login_at ? timeText(user.last_login_at) : "—"}</td>
                <td>
                  {user.username !== session.user.username && (
                    <>
                      <button type="button" className={user.is_active ? "small-btn ghost" : "small-btn"}
                              onClick={() => patch(`/api/admin/users/${user.id}`, { is_active: !user.is_active })}>
                        {user.is_active ? "停用" : "啟用"}
                      </button>
                      <button type="button" className="small-btn" onClick={() => resetPassword(user)}>重設密碼</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form id="user-form" className="new-user" onSubmit={createUser}>
        <h3>新增帳號</h3>
        <div className="fields">
          <label>帳號<input id="new-username" required pattern="[a-z0-9_]{3,30}" placeholder="小寫英文或數字"
                          value={newUser.username} onChange={field(setNewUser, "username")} /></label>
          <label>名稱<input id="new-display" required maxLength={30} value={newUser.display_name}
                          onChange={field(setNewUser, "display_name")} /></label>
          <label>角色
            <select id="new-role" value={newUser.role} onChange={field(setNewUser, "role")}>
              <option>業務</option><option>主管</option><option>管理員</option>
            </select>
          </label>
          <label>初始密碼<input id="new-password" type="password" required autoComplete="new-password"
                            placeholder="至少 8 碼，英文加數字" value={newUser.password} onChange={field(setNewUser, "password")} /></label>
        </div>
        <button type="submit">新增</button>
      </form>

      <h3>合作夥伴 API（官網串接）</h3>
      <p className="hint">合作夥伴的後端用 API 金鑰呼叫 <a href="/partner/docs" target="_blank" rel="noopener">合作夥伴 API 文件</a>。金鑰只在建立時顯示一次，系統只存雜湊；超過每分鐘上限回 429。</p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>名稱</th><th>金鑰開頭</th><th>每分鐘上限</th><th>24 小時呼叫</th><th>被限流</th><th>報價數</th><th>狀態</th><th>操作</th></tr></thead>
          <tbody id="partner-rows">
            {partners.partners.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td><td>{`${p.key_prefix}…`}</td><td>{p.rate_limit_per_minute}</td><td>{p.calls_24h}</td>
                <td>{p.limited_24h}</td><td>{p.quotes}</td><td>{p.is_active ? "啟用" : "停用"}</td>
                <td>
                  <button type="button" className={p.is_active ? "small-btn ghost" : "small-btn"}
                          onClick={() => patch(`/api/admin/partners/${p.id}`, { is_active: !p.is_active })}>
                    {p.is_active ? "停用" : "啟用"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form id="partner-form" className="new-user" onSubmit={createPartner}>
        <div className="fields">
          <label>合作夥伴名稱<input id="partner-name" required maxLength={50} placeholder="例如：某某旅遊平台"
                              value={newPartner.name} onChange={field(setNewPartner, "name")} /></label>
          <label>每分鐘上限<input id="partner-limit" type="number" min="1" max="600" required
                             value={newPartner.limit} onChange={field(setNewPartner, "limit")} /></label>
        </div>
        <button type="submit">建立並產生金鑰</button>
      </form>
      <div id="partner-key" className="key-once" hidden={!createdKey}>
        {createdKey && (
          <>
            <strong>{`「${createdKey.name}」的 API 金鑰（只顯示這一次，請立即交給對方並妥善保存）：`}</strong>
            <p><code>{createdKey.api_key}</code></p>
          </>
        )}
      </div>
      <details className="chart-table">
        <summary>最近的 API 呼叫</summary>
        <table>
          <thead><tr><th>時間</th><th>合作夥伴</th><th>路徑</th><th>結果</th></tr></thead>
          <tbody id="partner-calls">
            {partners.recent_calls.map((c, i) => (
              <tr key={i}><td>{timeText(c.created_at)}</td><td>{c.name}</td><td>{`${c.method} ${c.path}`}</td><td>{c.status}</td></tr>
            ))}
          </tbody>
        </table>
      </details>

      <h3>登入紀錄</h3>
      <div className="table-wrap">
        <table>
          <thead><tr><th>時間</th><th>帳號</th><th>結果</th><th>說明</th></tr></thead>
          <tbody id="login-rows">
            {events.map((e, i) => (
              <tr key={i}><td>{timeText(e.created_at)}</td><td>{e.username}</td><td>{e.success ? "成功" : "失敗"}</td><td>{e.reason}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
