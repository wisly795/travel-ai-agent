import React, { useState } from "react";
import { Link } from "react-router-dom";
import Policy from "../Policy.jsx";

export default function Guide() {
  const [error, setError] = useState("");
  return (
    <>
      <section className="s-banner">
        <div className="s-container s-banner-body">
          <p className="s-crumb"><Link to="/">首頁</Link> ／ 旅遊須知</p>
          <h1>旅遊須知</h1>
          <p>取消退費、行李、簽證、保險、付款與特殊需求。用自己的話搜尋，系統會找出最相關的條文。</p>
        </div>
      </section>
      <div className="s-container s-guide">
        {error && <p className="s-error">{error}</p>}
        <Policy hidden={false} onError={setError} />
      </div>
    </>
  );
}
