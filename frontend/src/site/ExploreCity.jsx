import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, money } from "../api.js";
import { SOURCE_NOTE } from "./destinations.js";
import { Photo } from "./parts.jsx";

const PAGE = 12;
const KEYWORDS = ["", "海", "步道", "溫泉", "老街", "部落", "博物館"];
const BUDGETS = [["", "不限"], ["2000", "2,000 以下"], ["3000", "3,000 以下"], ["5000", "5,000 以下"]];

export default function ExploreCity() {
  const { city } = useParams();
  const [kind, setKind] = useState("attractions");
  const [keyword, setKeyword] = useState("");
  const [budget, setBudget] = useState("");
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(null);  // 點開的卡片（I6 驗收問題 8：卡片原本點不進去）

  function load(offset) {
    const query = new URLSearchParams({ city, limit: PAGE, offset });
    if (keyword) query.set("q", keyword);
    if (kind === "hotels" && budget) query.set("max_price", budget);
    setLoading(true);
    return api(`/api/explore/${kind}?${query}`).then((r) => {
      setItems((list) => (offset ? [...list, ...r.items] : r.items));
      setTotal(r.total);
    }).catch(() => setTotal(0)).finally(() => setLoading(false));
  }

  useEffect(() => { load(0); }, [city, kind, keyword, budget]);

  return (
    <>
      <section className="s-banner">
        {items[0]?.images?.[0] && kind === "attractions" && <Photo src={items[0].images[0].url} alt={city} fallback={<span />} />}
        <div className="s-container s-banner-body">
          <p className="s-crumb"><Link to="/">首頁</Link> ／ <Link to="/explore">探索台灣</Link> ／ {city}</p>
          <h1 id="city-title">{city}</h1>
          <p>景點與合法旅宿（交通部觀光署開放資料）</p>
        </div>
      </section>
      <div className="s-container" style={{ paddingBottom: 56 }}>
        <div className="s-filters" role="group" aria-label="篩選">
          <div className="s-chips" style={{ margin: 0, flex: "1 1 100%" }}>
            <button type="button" className={`s-chip${kind === "attractions" ? " on" : ""}`} onClick={() => setKind("attractions")}>景點</button>
            <button type="button" className={`s-chip${kind === "hotels" ? " on" : ""}`} onClick={() => setKind("hotels")}>住宿</button>
          </div>
          <div className="s-chips" style={{ margin: 0 }}>
            {KEYWORDS.map((k) => (
              <button key={k || "all"} type="button" className={`s-chip${keyword === k ? " on" : ""}`} onClick={() => setKeyword(k)}>
                {k || "全部"}
              </button>
            ))}
          </div>
          {kind === "hotels" && (
            <label style={{ flex: "0 1 200px" }}>每晚最低價
              <select id="hotel-budget" value={budget} onChange={(e) => setBudget(e.target.value)}>
                {BUDGETS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
          )}
        </div>

        {total !== null && <p className="s-muted" id="explore-count">共 {total.toLocaleString()} 筆</p>}
        {total === 0 && <div className="s-empty"><h2>找不到符合的資料</h2><p className="s-muted">換個關鍵字試試看。</p></div>}
        <div className="s-grid" id="explore-list">
          {items.map((item) => (
            <button key={item.id} type="button" className="s-attr-btn" aria-label={`看 ${item.name} 的詳細介紹`}
                    onClick={() => setOpen({ kind, item })}>
              {kind === "attractions" ? <AttractionCard item={item} /> : <HotelCard item={item} />}
            </button>
          ))}
        </div>
        {open && <Detail kind={open.kind} item={open.item} onClose={() => setOpen(null)} />}
        {items.length < (total || 0) && (
          <div className="s-more">
            <button type="button" className="s-btn s-btn-ghost" disabled={loading} onClick={() => load(items.length)}>
              {loading ? "載入中…" : `載入更多（還有 ${(total - items.length).toLocaleString()} 筆）`}
            </button>
          </div>
        )}
        <p className="s-source">{SOURCE_NOTE}。內容以官方公告為準。</p>
      </div>
    </>
  );
}

// 詳細內容：先用列表已有的資料顯示，再向後端拿完整資料（照片、網站等）
function Detail({ kind, item, onClose }) {
  const [full, setFull] = useState(item);
  useEffect(() => {
    api(`/api/explore/${kind}/${encodeURIComponent(item.id)}`).then(setFull).catch(() => {});
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [kind, item.id]);
  const map = full.lat && full.lon
    ? `https://www.google.com/maps/search/?api=1&query=${full.lat},${full.lon}`
    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(full.address || full.name)}`;
  const services = (full.services || "").split(",").filter(Boolean);
  return (
    <div className="s-modal-bg" onClick={onClose}>
      <div className="s-modal" role="dialog" aria-modal="true" aria-labelledby="detail-title" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="s-modal-close" aria-label="關閉" onClick={onClose}>×</button>
        <div className="s-modal-photos">
          {(full.images || []).slice(0, 3).map((img) => <Photo key={img.url} src={img.url} alt={img.name || full.name} fallback={<span />} />)}
        </div>
        <div className="s-modal-body">
          <h2 id="detail-title">{full.name}</h2>
          <div>{(full.class_names || []).map((c) => <span key={c} className="s-tag" style={{ marginRight: 6 }}>{c}</span>)}
            {full.free && <span className="s-tag warm">免費</span>}</div>
          <dl className="s-modal-info">
            <dt>地址</dt><dd>{full.address || "—"}</dd>
            {kind === "hotels" && <><dt>房間</dt><dd>{full.total_rooms} 間</dd></>}
            {kind === "hotels" && full.lowest_price && <><dt>登記房價</dt><dd>{money(full.lowest_price)} ～ {money(full.ceiling_price)}／晚（業者向官方登記的參考價，不是本站報價）</dd></>}
            {services.length > 0 && <><dt>服務</dt><dd>{services.join("・")}</dd></>}
          </dl>
          {full.description && <p className="s-modal-desc">{full.description}</p>}
          <div className="s-modal-actions">
            <a className="s-btn" href={map} target="_blank" rel="noreferrer">在 Google 地圖查看</a>
            {full.website && <a className="s-btn s-btn-ghost" href={full.website} target="_blank" rel="noreferrer">官方網站</a>}
          </div>
          <p className="s-source">資料來源：{full.source || "交通部觀光署"}（{full.license || "政府資料開放授權條款"}）。內容以官方公告為準，出發前請再確認。</p>
        </div>
      </div>
    </div>
  );
}

function AttractionCard({ item }) {
  return (
    <article className="s-attr">
      <div className="s-attr-photo"><Photo src={item.images[0]?.url} alt={item.name} /></div>
      <div className="s-attr-body">
        <h3>{item.name}</h3>
        <div>{item.class_names.slice(0, 2).map((c) => <span key={c} className="s-tag" style={{ marginRight: 6 }}>{c}</span>)}
          {item.free && <span className="s-tag warm">免費</span>}</div>
        <span className="s-note">{item.address}</span>
        <p>{item.description}</p>
      </div>
    </article>
  );
}

function HotelCard({ item }) {
  return (
    <article className="s-attr">
      <div className="s-attr-photo"><Photo src={item.images[0]?.url} alt={item.name} fallback={<div className="s-photo-fallback">{item.class_names[0] || "旅宿"}</div>} /></div>
      <div className="s-attr-body">
        <h3>{item.name}</h3>
        <div><span className="s-tag">{item.class_names[0] || "旅宿"}</span> <span className="s-note">{item.total_rooms} 間房</span></div>
        <span className="s-note">{item.address}</span>
        {item.lowest_price && <span className="s-price" style={{ fontSize: 17 }}>{money(item.lowest_price)} ～ {money(item.ceiling_price)}<small>／晚（登記價）</small></span>}
        {item.services && <p>{item.services.split(",").filter(Boolean).slice(0, 5).join("・")}</p>}
      </div>
    </article>
  );
}
