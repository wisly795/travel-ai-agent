// 前台共用的小元件
import React, { useState } from "react";
import { Link } from "react-router-dom";
import { money } from "../api.js";
import DestinationArt from "./DestinationArt.jsx";
import { meta } from "./destinations.js";

// 開放資料的照片放在各單位網站：載入失敗就顯示替代畫面，不留破圖
export function Photo({ src, alt, fallback, className }) {
  const [failed, setFailed] = useState(!src);
  if (failed) return fallback || <div className="s-photo-fallback" role="img" aria-label={alt}>暫無照片</div>;
  return <img className={className} src={src} alt={alt} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />;
}

export function TourCard({ tour }) {
  const info = meta(tour.destination);
  return (
    <Link to={`/tours/${tour.id}`} className="s-card" data-tour={tour.id}>
      <div className="s-card-media">
        <DestinationArt art={info.art} label={tour.destination} />
        <span className="s-tag">{info.country}・{tour.destination}</span>
      </div>
      <div className="s-card-body">
        <h3>{tour.name}</h3>
        <p>{tour.description}</p>
        <div className="s-card-foot">
          <span className="s-note">{tour.days} 天｜剩 {tour.seats_left} 位</span>
          <span className="s-price">{money(tour.price_per_person)}<small> 起／人</small></span>
        </div>
      </div>
    </Link>
  );
}

export function SectionHead({ title, sub, action }) {
  return (
    <div className="s-section-head">
      <div><h2>{title}</h2>{sub && <p>{sub}</p>}</div>
      {action}
    </div>
  );
}
