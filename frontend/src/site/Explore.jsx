import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { SOURCE_NOTE } from "./destinations.js";
import { Photo } from "./parts.jsx";

export default function Explore() {
  const [cities, setCities] = useState(null);

  useEffect(() => {
    api("/api/explore/cities").then(async (r) => {
      setCities(r.cities.map((c) => ({ ...c, photo: null })));
      // 照片慢慢補上：每個縣市一張有照片的景點
      const photos = await Promise.all(r.cities.map((c) => api(`/api/explore/attractions?city=${encodeURIComponent(c.city)}&with_image=true&limit=1`)
        .then((x) => x.items[0]?.images[0]?.url).catch(() => null)));
      setCities(r.cities.map((c, i) => ({ ...c, photo: photos[i] })));
    }).catch(() => setCities([]));
  }, []);

  return (
    <>
      <section className="s-banner">
        <div className="s-container s-banner-body">
          <p className="s-crumb"><Link to="/">首頁</Link> ／ 探索台灣</p>
          <h1>探索台灣</h1>
          <p>全台 22 個縣市的景點與合法旅宿，資料每天同步交通部觀光署開放資料。</p>
        </div>
      </section>
      <section className="s-section">
        <div className="s-container">
          {cities && !cities.length && <div className="s-empty"><h2>資料準備中</h2><p className="s-muted">開放資料正在匯入，請稍後再來。</p></div>}
          <div className="s-grid" id="city-list">
            {cities?.map((c) => (
              <Link key={c.city} to={`/explore/${encodeURIComponent(c.city)}`} className="s-city">
                <Photo src={c.photo} alt={c.city} fallback={<span />} />
                <span className="s-city-text"><strong>{c.city}</strong><span>{c.attractions} 個景點・{c.hotels} 家旅宿</span></span>
              </Link>
            ))}
          </div>
          <p className="s-source">{SOURCE_NOTE}</p>
        </div>
      </section>
    </>
  );
}
