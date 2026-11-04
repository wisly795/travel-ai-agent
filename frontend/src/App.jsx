import React, { useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import Staff from "./staff/Staff.jsx";
import Explore from "./site/Explore.jsx";
import ExploreCity from "./site/ExploreCity.jsx";
import Guide from "./site/Guide.jsx";
import Home from "./site/Home.jsx";
import Layout from "./site/Layout.jsx";
import TourDetail from "./site/TourDetail.jsx";
import Tours from "./site/Tours.jsx";

// 前台（旅遊網站）與後台（/admin）是兩個不同的版面
export default function App() {
  return (
    <Routes>
      <Route path="/admin" element={<AdminApp />} />
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="tours" element={<Tours />} />
        <Route path="tours/:id" element={<TourDetail />} />
        <Route path="explore" element={<Explore />} />
        <Route path="explore/:city" element={<ExploreCity />} />
        <Route path="guide" element={<Guide />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

function AdminApp() {
  const [message, setMessage] = useState("");
  return (
    <div className="admin-app">
      <header>
        <h1>晴空旅遊・業務後台</h1>
        <p className="demo">模擬資料，非真實報價｜<Link to="/">回到網站</Link></p>
      </header>
      <main>
        <Staff hidden={false} onError={setMessage} />
        <p id="message" className="message" role="alert" hidden={!message}>{message}</p>
      </main>
    </div>
  );
}

function NotFound() {
  return (
    <section className="s-container s-empty">
      <h1>找不到這個頁面</h1>
      <Link className="s-btn" to="/">回首頁</Link>
    </section>
  );
}
