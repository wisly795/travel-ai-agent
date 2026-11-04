import React, { useEffect, useRef, useState } from "react";
import { api, money, postJson } from "./api.js";

// 出發日期只能選明天到一年內（後端也會再檢查一次）
const DAY = 24 * 60 * 60 * 1000;
const isoDay = (offset) => new Date(Date.now() + offset).toLocaleDateString("sv-SE", { timeZone: "Asia/Taipei" });

export default function Customer({ hidden, onError }) {
  const [destinations, setDestinations] = useState([]);
  const [search, setSearch] = useState({ destination: "", people: "2", maxPrice: "" });
  const [packages, setPackages] = useState(null);
  const [selected, setSelected] = useState(null);
  const [hotels, setHotels] = useState([]);
  const [form, setForm] = useState({ hotelId: "", departure: "", name: "" });
  const [quote, setQuote] = useState(null);
  const quoteRef = useRef(null);

  useEffect(() => { api("/api/destinations").then(setDestinations).catch((error) => onError(error.message)); }, []);
  useEffect(() => { if (selected) quoteRef.current?.scrollIntoView({ behavior: "smooth" }); }, [selected]);

  async function searchPackages(event) {
    event.preventDefault();
    onError("");
    setSelected(null);
    setQuote(null);
    const params = new URLSearchParams({ people: search.people });
    if (search.destination) params.set("destination", search.destination);
    if (search.maxPrice) params.set("max_price", search.maxPrice);
    try {
      setPackages(await api(`/api/packages?${params}`));
    } catch (error) {
      onError(error.message);
    }
  }

  async function choose(item) {
    try {
      const list = await api(`/api/hotels?destination=${encodeURIComponent(item.destination)}`);
      setHotels(list);
      setForm((f) => ({ ...f, hotelId: list[0] ? String(list[0].id) : "" }));
      setSelected(item);
    } catch (error) {
      onError(error.message);
    }
  }

  async function createQuote(event) {
    event.preventDefault();
    onError("");
    try {
      setQuote(await postJson("/api/quotes", {
        customer_name: form.name, package_id: selected.id, hotel_id: Number(form.hotelId),
        people: Number(search.people), departure_date: form.departure,
      }));
    } catch (error) {
      onError(error.message);
    }
  }

  const setField = (setter, key) => (event) => setter((value) => ({ ...value, [key]: event.target.value }));

  return (
    <section id="customer" hidden={hidden}>
      <form id="search-form" className="panel" onSubmit={searchPackages}>
        <h2>1. 查詢行程</h2>
        <div className="fields">
          <label>目的地
            <select id="destination" value={search.destination} onChange={setField(setSearch, "destination")}>
              <option value="">全部</option>
              {destinations.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label>人數<input id="people" type="number" min="1" max="20" required value={search.people}
                          onChange={setField(setSearch, "people")} /></label>
          <label>每人預算<input id="max-price" type="number" min="1" step="1000" placeholder="不限"
                            value={search.maxPrice} onChange={setField(setSearch, "maxPrice")} /></label>
        </div>
        <button type="submit">查詢</button>
      </form>

      <div id="packages" className="cards" aria-live="polite">
        {packages && !packages.length && <p>沒有符合條件的行程，請調整預算或人數。</p>}
        {packages?.map((item) => (
          <article key={item.id} className="card">
            <h3>{item.name}</h3>
            <p>{`${item.destination}｜${item.days} 天｜剩 ${item.seats_left} 位`}</p>
            <p>{item.description}</p>
            <strong>{`${money(item.price_per_person)} / 人`}</strong>
            <button type="button" onClick={() => choose(item)}>選擇</button>
          </article>
        ))}
      </div>

      <form id="quote-form" className="panel" hidden={!selected} ref={quoteRef} onSubmit={createQuote}>
        <h2>2. 建立報價</h2>
        <p>已選行程：<strong id="selected-package">{selected?.name}</strong></p>
        <div className="fields">
          <label>飯店
            <select id="hotel" value={form.hotelId} onChange={setField(setForm, "hotelId")}>
              {hotels.map((hotel) => (
                <option key={hotel.id} value={hotel.id}>
                  {`${hotel.name}（${hotel.room_type}，每晚 ${money(hotel.price_per_night)}）`}
                </option>
              ))}
            </select>
          </label>
          <label>出發日期<input id="departure-date" type="date" required min={isoDay(DAY)} max={isoDay(365 * DAY)}
                            value={form.departure} onChange={setField(setForm, "departure")} /></label>
          <label>姓名<input id="customer-name" maxLength={50} required value={form.name}
                          onChange={setField(setForm, "name")} /></label>
        </div>
        <button type="submit">建立報價</button>
      </form>

      <div id="result" className="panel result" hidden={!quote} aria-live="polite">
        {quote && (
          <>
            <h2>{`報價單 #${quote.id}`}</h2>
            <p>{`${quote.customer_name}｜${quote.package}｜${quote.hotel}`}</p>
            <p>{`${quote.people} 人，${quote.rooms} 間房，${quote.nights} 晚`}</p>
            {quote.departure_date && <p>{`出發 ${quote.departure_date}，回程 ${quote.return_date}`}</p>}
            <strong>{`總價 ${money(quote.total_price)}`}</strong>
            <p>模擬資料，非真實報價</p>
          </>
        )}
      </div>
    </section>
  );
}
