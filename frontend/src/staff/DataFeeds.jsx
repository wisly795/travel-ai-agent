import React from "react";
import { money, timeText } from "../api.js";
import useStaffData from "./useStaffData.js";

const DATASET_LABELS = { attractions: "景點", hotels: "旅宿" };

export default function DataFeeds({ hidden, staffApi, action, version, session, onError }) {
  const [imports] = useStaffData(staffApi, "/api/admin/opendata/imports", version, onError, []);
  const [runs] = useStaffData(staffApi, "/api/admin/crawler/runs", version, onError, []);
  const [changes] = useStaffData(staffApi, "/api/admin/crawler/changes", version, onError, []);
  const isAdmin = session.user.role === "管理員";
  const start = (path) => action(() => staffApi(path, { method: "POST" }));

  return (
    <div id="view-data" className="panel view" hidden={hidden}>
      <div className="row">
        <h2>資料與爬蟲</h2>
        <div className="toolbar" hidden={!isAdmin}>
          <button id="opendata-run" type="button" className="ghost" onClick={() => start("/api/admin/opendata/import")}>重新匯入開放資料</button>
          <button id="crawler-run" type="button" onClick={() => start("/api/admin/crawler/run")}>立即執行爬蟲</button>
        </div>
      </div>
      <p className="hint">政府開放資料（交通部觀光署景點、旅宿）每天 04:30 自動更新；供應商價格爬蟲每天 05:00 自動執行（遵守 robots.txt，每秒最多 1 次）。都在背景執行，按下後約 1 分鐘重新整理可看到結果。只有管理員能手動執行。</p>

      <h3>開放資料匯入紀錄</h3>
      <div className="table-wrap">
        <table>
          <thead><tr><th>時間</th><th>資料</th><th>觸發</th><th>結果</th><th>總筆數</th><th>新增</th><th>更新</th><th>不變</th><th>下架</th><th>官方資料時間</th></tr></thead>
          <tbody id="import-rows">
            {imports.map((r) => (
              <tr key={r.id} title={r.error || ""}>
                <td>{timeText(r.started_at)}</td><td>{DATASET_LABELS[r.dataset] || r.dataset}</td><td>{r.trigger}</td>
                <td className={r.status === "失敗" ? "fail" : r.status === "完成" ? "pass" : ""}>{r.status}</td>
                <td>{r.total ?? "—"}</td><td>{r.inserted ?? "—"}</td><td>{r.updated ?? "—"}</td><td>{r.unchanged ?? "—"}</td>
                <td>{r.removed ?? "—"}</td><td>{r.source_time ? r.source_time.slice(0, 16).replace("T", " ") : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>爬蟲紀錄</h3>
      <div className="table-wrap">
        <table>
          <thead><tr><th>時間</th><th>觸發</th><th>結果</th><th>頁數</th><th>住宿</th><th>價格變動</th><th>通知</th><th>請求</th><th>重試</th><th>秒數</th><th>錯誤</th></tr></thead>
          <tbody id="crawl-rows">
            {runs.map((r) => (
              <tr key={r.id}>
                <td>{timeText(r.started_at)}</td><td>{r.trigger}</td>
                <td className={r.status === "完成" ? "pass" : r.status === "執行中" ? "" : "fail"}>{r.status}</td>
                <td>{r.pages ?? "—"}</td><td>{r.hotels ?? "—"}</td><td>{r.changes ?? "—"}</td><td>{r.alerts ?? "—"}</td>
                <td>{r.requests ?? "—"}</td><td>{r.retries ?? "—"}</td><td>{r.seconds ?? "—"}</td>
                <td>{(r.errors || []).length ? r.errors.join("；").slice(0, 80) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>最近的價格變動</h3>
      {!changes.length && <p className="hint">目前沒有價格變動（第一次爬取只建立基準）。</p>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>住宿</th><th>城市</th><th>房型</th><th>原價</th><th>新價</th><th>漲跌</th><th>價格日期</th></tr></thead>
          <tbody id="change-rows">
            {changes.map((c, i) => {
              const ratio = c.old_price && c.new_price ? (c.new_price - c.old_price) / c.old_price : null;
              return (
                <tr key={i}>
                  <td>{c.name}</td><td>{c.city}</td><td>{c.room}</td>
                  <td>{c.old_price ? money(c.old_price) : "售完"}</td><td>{c.new_price ? money(c.new_price) : "售完"}</td>
                  <td className={ratio > 0 ? "fail" : ratio < 0 ? "pass" : ""}>{ratio === null ? "—" : `${ratio > 0 ? "+" : ""}${(ratio * 100).toFixed(0)}%`}</td>
                  <td>{c.price_date}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
