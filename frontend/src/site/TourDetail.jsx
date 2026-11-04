import React, { useEffect, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import { api, money, postJson } from "../api.js";
import DestinationArt from "./DestinationArt.jsx";
import { meta, SOURCE_NOTE } from "./destinations.js";
import { Photo } from "./parts.jsx";

const DAY = 24 * 60 * 60 * 1000;
const isoDay = (offset) => new Date(Date.now() + offset).toLocaleDateString("sv-SE", { timeZone: "Asia/Taipei" });

export default function TourDetail() {
  const { id } = useParams();
  const { openChat } = useOutletContext();
  const [tour, setTour] = useState(null);
  const [hotels, setHotels] = useState([]);
  const [form, setForm] = useState({ hotelId: "", people: "2", departure: "", name: "" });
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState("");
  const [quote, setQuote] = useState(null);
  const [error, setError] = useState("");
  const [spots, setSpots] = useState([]);
  const [supplier, setSupplier] = useState([]);

  // 行程本身：從行程清單找（人數 1 才不會被名額篩掉）
  useEffect(() => {
    api("/api/packages?people=1").then((list) => setTour(list.find((t) => String(t.id) === id) || false)).catch(() => setTour(false));
  }, [id]);

  useEffect(() => {
    if (!tour) return;
    const info = meta(tour.destination);
    api(`/api/hotels?destination=${encodeURIComponent(tour.destination)}`).then((list) => {
      setHotels(list);
      setForm((f) => ({ ...f, hotelId: f.hotelId || String(list[0]?.id || "") }));
    }).catch(() => {});
    // 台灣的目的地：附近景點（開放資料）
    if (info.city) {
      api(`/api/explore/attractions?city=${encodeURIComponent(info.city)}&with_image=true&limit=6`).then((r) => setSpots(r.items)).catch(() => {});
    }
    // 供應商參考價（爬蟲抓的模擬比價網站）
    api(`/api/supplier-prices?city=${encodeURIComponent(info.supplier)}`).then((r) => setSupplier(r.hotels)).catch(() => {});
  }, [tour]);

  // 人數、飯店、日期一改就重新試算（價格一律由後端計算）
  useEffect(() => {
    if (!tour || !form.hotelId) return;
    const body = { package_id: tour.id, hotel_id: Number(form.hotelId), people: Number(form.people) };
    if (form.departure) body.departure_date = form.departure;
    setPreviewError("");
    postJson("/api/quotes/preview", body).then(setPreview).catch((e) => { setPreview(null); setPreviewError(e.message); });
  }, [tour, form.hotelId, form.people, form.departure]);

  async function book(event) {
    event.preventDefault();
    setError("");
    try {
      setQuote(await postJson("/api/quotes", { customer_name: form.name, package_id: tour.id, hotel_id: Number(form.hotelId),
        people: Number(form.people), departure_date: form.departure }));
    } catch (e) {
      setError(e.message);
    }
  }

  if (tour === false) return <section className="s-container s-empty"><h1>找不到這個行程</h1><Link className="s-btn" to="/tours">看全部行程</Link></section>;
  if (!tour) return <section className="s-container s-empty"><p className="s-muted">載入中…</p></section>;
  const info = meta(tour.destination);
  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  return (
    <>
      <section className="s-banner">
        <DestinationArt art={info.art} label={tour.destination} />
        <div className="s-container s-banner-body">
          <p className="s-crumb"><Link to="/">首頁</Link> ／ <Link to="/tours">精選行程</Link> ／ {tour.destination}</p>
          <h1 id="tour-title">{tour.name}</h1>
          <p>{info.tagline}｜{tour.description}</p>
        </div>
      </section>

      <div className="s-container s-detail">
        <div>
          <div className="s-box">
            <h2>行程資訊</h2>
            <div className="s-facts">
              <div className="s-fact"><small>目的地</small><b>{info.country}・{tour.destination}</b></div>
              <div className="s-fact"><small>天數</small><b>{tour.days} 天 {tour.days - 1} 夜</b></div>
              <div className="s-fact"><small>行程費</small><b>{money(tour.price_per_person)}／人</b></div>
              <div className="s-fact"><small>剩餘名額</small><b>{tour.seats_left} 位</b></div>
            </div>
          </div>

          <div className="s-box">
            <h2>選擇住宿</h2>
            <div className="s-hotels" role="radiogroup" aria-label="選擇住宿">
              {hotels.map((h) => (
                <label key={h.id} className={`s-hotel${form.hotelId === String(h.id) ? " on" : ""}`}>
                  <span><input type="radio" name="hotel" value={h.id} checked={form.hotelId === String(h.id)} onChange={set("hotelId")} />
                    <b>{h.name}</b> <span className="s-muted">{h.room_type}</span></span>
                  <span className="s-price" style={{ fontSize: 17 }}>{money(h.price_per_night)}<small>／晚</small></span>
                </label>
              ))}
            </div>
          </div>

          {supplier.length > 0 && (
            <div className="s-box" id="supplier-prices">
              <h2>供應商參考價</h2>
              <p className="s-note">本系統爬蟲每天從模擬比價網站抓取的每晚房價，僅供參考，不是本行程報價。</p>
              <div style={{ overflowX: "auto" }}>
                <table className="s-table">
                  <thead><tr><th>住宿</th><th>房型</th><th className="num">每晚</th><th>價格日期</th></tr></thead>
                  <tbody>
                    {supplier.slice(0, 4).flatMap((h) => h.rooms.map((r, i) => (
                      <tr key={`${h.id}${r.room}`}>
                        <td>{i === 0 ? `${h.name}（${"★".repeat(h.stars)}）` : ""}</td><td>{r.room}</td>
                        <td className="num">{r.price ? money(r.price) : "售完"}</td><td>{r.price_date}</td>
                      </tr>
                    )))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {spots.length > 0 && (
            <div className="s-box" id="nearby-spots">
              <h2>{info.city}景點推薦</h2>
              <div className="s-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))" }}>
                {spots.map((s) => (
                  <article key={s.id} className="s-attr">
                    <div className="s-attr-photo"><Photo src={s.images[0]?.url} alt={s.name} /></div>
                    <div className="s-attr-body"><h3>{s.name}</h3><span className="s-note">{s.town}・{s.class_names.join("、")}</span></div>
                  </article>
                ))}
              </div>
              <p className="s-source">{SOURCE_NOTE}｜<Link to={`/explore/${encodeURIComponent(info.city)}`}>看更多{info.city}景點與住宿</Link></p>
            </div>
          )}
        </div>

        <aside className="s-book">
          <form className="s-box" id="book-form" onSubmit={book} aria-label="試算與建立報價">
            <h2>試算與報價</h2>
            <div className="fields" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <label>人數<input id="book-people" type="number" min="1" max="20" required value={form.people} onChange={set("people")} /></label>
              <label>出發日期<input id="book-date" type="date" required min={isoDay(DAY)} max={isoDay(365 * DAY)}
                                value={form.departure} onChange={set("departure")} /></label>
            </div>
            {previewError && <p className="s-error">{previewError}</p>}
            {preview && (
              <div className="s-sum" id="book-summary">
                <div><span>行程費 × {preview.people} 人</span><span>{money(preview.package_fee)}</span></div>
                <div><span>住宿 {preview.rooms} 間 × {preview.nights} 晚</span><span>{money(preview.hotel_fee)}</span></div>
                {preview.return_date && <div><span>出發／回程</span><span>{preview.departure_date} ～ {preview.return_date}</span></div>}
                <div className="total"><span>總價</span><span id="book-total">{money(preview.total_price)}</span></div>
              </div>
            )}
            {!quote && (
              <>
                <label>聯絡人姓名<input id="book-name" maxLength={50} required value={form.name} onChange={set("name")} /></label>
                {error && <p className="s-error">{error}</p>}
                <button type="submit" className="s-btn" style={{ width: "100%", marginTop: 14 }}>建立報價單</button>
                <p className="s-note" style={{ marginTop: 10 }}>建立報價單不需付款，業務會與您聯絡確認。</p>
              </>
            )}
            {quote && (
              <div className="s-success" id="book-result">
                <h3>報價單 #{quote.id} 已建立</h3>
                <p>{quote.customer_name}｜{quote.package}｜{quote.hotel}<br />{quote.people} 人、{quote.rooms} 間房、{quote.nights} 晚</p>
                <p className="s-price">{money(quote.total_price)}</p>
                <p className="s-note">模擬資料，非真實報價</p>
              </div>
            )}
          </form>
          <button type="button" className="s-btn s-btn-ghost" style={{ width: "100%" }} onClick={openChat}>有問題？問 AI 旅遊顧問</button>
        </aside>
      </div>
    </>
  );
}
