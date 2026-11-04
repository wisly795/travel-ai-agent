import React, { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import { Photo, SectionHead, TourCard } from "./parts.jsx";

const BUDGETS = [["", "不限"], ["15000", "NT$ 15,000 以下"], ["25000", "NT$ 25,000 以下"], ["35000", "NT$ 35,000 以下"]];

export default function Home() {
  const navigate = useNavigate();
  const { openChat } = useOutletContext();
  const [tours, setTours] = useState([]);
  const [destinations, setDestinations] = useState([]);
  const [cities, setCities] = useState([]);
  const [hero, setHero] = useState(null);
  const [search, setSearch] = useState({ destination: "", people: "2", max_price: "" });

  useEffect(() => {
    api("/api/packages?people=1").then(setTours).catch(() => {});
    api("/api/destinations").then(setDestinations).catch(() => {});
    // 首頁大圖：開放資料裡的七星潭照片（載入失敗就用漸層背景）
    api(`/api/explore/attractions?city=${encodeURIComponent("花蓮縣")}&q=${encodeURIComponent("七星潭")}&with_image=true&limit=1`)
      .then((r) => setHero(r.items[0] || null)).catch(() => {});
    // 探索台灣：景點與住宿最多的 8 個縣市，各配一張開放資料照片
    api("/api/explore/cities").then(async (r) => {
      const top = r.cities.slice(0, 8);
      const photos = await Promise.all(top.map((c) => api(`/api/explore/attractions?city=${encodeURIComponent(c.city)}&with_image=true&limit=1`)
        .then((x) => x.items[0]?.images[0]?.url).catch(() => null)));
      setCities(top.map((c, i) => ({ ...c, photo: photos[i] })));
    }).catch(() => {});
  }, []);

  function submit(event) {
    event.preventDefault();
    const params = new URLSearchParams(Object.entries(search).filter(([, v]) => v));
    navigate(`/tours?${params}`);
  }

  const set = (key) => (event) => setSearch({ ...search, [key]: event.target.value });
  return (
    <>
      <section className="s-hero">
        {hero?.images[0] && <Photo className="s-hero-img" src={hero.images[0].url} alt={hero.name} fallback={<span />} />}
        <div className="s-container s-hero-body">
          <h1>下一段旅程，<br />從晴空開始</h1>
          <p className="lead">沖繩、京都、首爾、花蓮、台東精選行程，價格由系統即時計算；不知道怎麼選，就問 AI 旅遊顧問。</p>
          <form className="s-search" onSubmit={submit} aria-label="搜尋行程">
            <label>想去哪裡
              <select id="home-destination" value={search.destination} onChange={set("destination")}>
                <option value="">全部目的地</option>
                {destinations.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </label>
            <label>人數<input id="home-people" type="number" min="1" max="20" value={search.people} onChange={set("people")} /></label>
            <label>每人預算
              <select id="home-budget" value={search.max_price} onChange={set("max_price")}>
                {BUDGETS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <button type="submit" className="s-btn">搜尋行程</button>
          </form>
        </div>
        {hero && <span className="s-hero-credit">照片：{hero.name}（交通部觀光署開放資料）</span>}
      </section>

      <section className="s-section">
        <div className="s-container">
          <SectionHead title="精選行程" sub="五個目的地、八條路線，名額即時更新"
                       action={<Link to="/tours" className="s-btn s-btn-ghost">看全部行程</Link>} />
          <div className="s-grid" id="home-tours">{tours.map((t) => <TourCard key={t.id} tour={t} />)}</div>
        </div>
      </section>

      <section className="s-section alt">
        <div className="s-container">
          <SectionHead title="探索台灣" sub="全台景點與合法旅宿，每天同步交通部觀光署開放資料"
                       action={<Link to="/explore" className="s-btn s-btn-ghost">全部縣市</Link>} />
          <div className="s-grid" id="home-cities">
            {cities.map((c) => (
              <Link key={c.city} to={`/explore/${encodeURIComponent(c.city)}`} className="s-city">
                <Photo src={c.photo} alt={c.city} fallback={<span />} />
                <span className="s-city-text"><strong>{c.city}</strong><span>{c.attractions} 個景點・{c.hotels} 家旅宿</span></span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="s-section">
        <div className="s-container">
          <SectionHead title="為什麼選晴空" />
          <div className="s-features">
            <div className="s-feature"><span className="s-feature-icon">AI</span><b>24 小時 AI 旅遊顧問</b><p>查行程、算報價、回答取消與簽證規定，回答附上規定條號。</p></div>
            <div className="s-feature"><span className="s-feature-icon">NT$</span><b>價格透明</b><p>行程、住宿、房間數與退費都由系統計算，AI 不會自己編價格。</p></div>
            <div className="s-feature"><span className="s-feature-icon">資料</span><b>官方資料</b><p>台灣景點與旅宿來自交通部觀光署開放資料，每天自動更新。</p></div>
          </div>
          <div className="s-more"><button type="button" className="s-btn" onClick={openChat}>和 AI 聊聊我的行程</button></div>
        </div>
      </section>
    </>
  );
}
