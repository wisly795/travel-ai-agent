import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { TourCard } from "./parts.jsx";

// 篩選條件放在網址（?destination=沖繩&people=2），可以分享、重新整理也不會不見
export default function Tours() {
  const [params, setParams] = useSearchParams();
  const [destinations, setDestinations] = useState([]);
  const [tours, setTours] = useState(null);
  const [error, setError] = useState("");
  const filters = { destination: params.get("destination") || "", people: params.get("people") || "2",
    max_price: params.get("max_price") || "" };

  useEffect(() => { api("/api/destinations").then(setDestinations).catch(() => {}); }, []);
  useEffect(() => {
    const query = new URLSearchParams({ people: filters.people });
    if (filters.destination) query.set("destination", filters.destination);
    if (filters.max_price) query.set("max_price", filters.max_price);
    setError("");
    api(`/api/packages?${query}`).then(setTours).catch((e) => { setTours([]); setError(e.message); });
  }, [params]);

  const update = (key) => (event) => {
    const next = { ...filters, [key]: event.target.value };
    setParams(Object.fromEntries(Object.entries(next).filter(([, v]) => v)));
  };

  return (
    <>
      <section className="s-banner">
        <div className="s-container s-banner-body">
          <p className="s-crumb"><Link to="/">首頁</Link> ／ 精選行程</p>
          <h1>精選行程</h1>
          <p>依目的地、人數與預算篩選，只顯示名額足夠的行程。</p>
        </div>
      </section>
      <div className="s-container">
        <form className="s-filters" onSubmit={(e) => e.preventDefault()} aria-label="篩選行程">
          <label>目的地
            <select id="tour-destination" value={filters.destination} onChange={update("destination")}>
              <option value="">全部</option>
              {destinations.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </label>
          <label>人數<input id="tour-people" type="number" min="1" max="20" value={filters.people} onChange={update("people")} /></label>
          <label>每人預算上限<input id="tour-budget" type="number" min="1000" step="1000" placeholder="不限"
                                value={filters.max_price} onChange={update("max_price")} /></label>
        </form>
        {error && <p className="s-error">{error}</p>}
        {tours && !tours.length && !error && (
          <div className="s-empty"><h2>沒有符合的行程</h2><p className="s-muted">試試放寬預算或減少人數，或問問 AI 旅遊顧問。</p></div>
        )}
        <div className="s-grid" id="tour-list" style={{ paddingBottom: 56 }}>
          {tours?.map((t) => <TourCard key={t.id} tour={t} />)}
        </div>
      </div>
    </>
  );
}
