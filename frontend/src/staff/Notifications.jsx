import React, { useEffect } from "react";
import { timeText } from "../api.js";
import useStaffData from "./useStaffData.js";

export default function Notifications({ hidden, staffApi, action, version, onError, onUnread }) {
  const [items] = useStaffData(staffApi, "/api/notifications", version, onError, []);
  useEffect(() => { onUnread(items.filter((item) => !item.is_read).length); }, [items]);
  const markRead = (body) => action(() => staffApi("/api/notifications/read", { method: "POST", body: JSON.stringify(body) }));

  return (
    <div id="view-notifications" className="panel view" hidden={hidden}>
      <div className="row">
        <h2>通知中心</h2>
        <button id="read-all" className="ghost" type="button" onClick={() => markRead({})}>全部標為已讀</button>
      </div>
      <p className="hint">由 n8n 自動化流程產生：新報價、每日報表、採購待核准、ERP 同步失敗。</p>
      <div id="notification-list">
        {!items.length && <p>目前沒有通知。</p>}
        {items.map((item) => (
          <div key={item.id} className={`notice${item.is_read ? "" : " unread"}`}>
            <small>{`${item.kind}｜${timeText(item.created_at)}`}</small>
            <strong>{item.title}</strong>
            <p className="policy-text">{item.body}</p>
            {!item.is_read && <button type="button" className="small-btn ghost" onClick={() => markRead({ id: item.id })}>已讀</button>}
          </div>
        ))}
      </div>
    </div>
  );
}
