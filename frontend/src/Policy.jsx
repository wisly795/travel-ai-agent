import React, { useEffect, useState } from "react";
import { api } from "./api.js";

export default function Policy({ hidden, onError }) {
  const [docs, setDocs] = useState([]);
  const [model, setModel] = useState(null);
  const [question, setQuestion] = useState("");
  const [results, setResults] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api("/api/policies"), api("/api/policies/model")])
      .then(([list, info]) => { setDocs(list); setModel(info); })
      .catch((err) => onError(err.message));
  }, []);

  async function search(event) {
    event.preventDefault();
    setError("");
    try {
      setResults(await api(`/api/policies/search?q=${encodeURIComponent(question)}`));
    } catch (err) {
      setResults(null);
      setError(err.message);
    }
  }

  return (
    <section id="policy" hidden={hidden}>
      <form id="policy-form" className="panel" onSubmit={search}>
        <h2>查規定</h2>
        <p className="hint">用自己的話描述問題，系統會用向量搜尋找出意思最接近的條文（AI 客服回答規定時也是用這個方法）。</p>
        <p id="policy-model" className="hint">
          {model && `向量模型：${model.finetuned ? "旅遊問答微調版" : "原始多語模型"}（相似度門檻 ${model.min_score}）`}
        </p>
        <div className="chat-form">
          <input id="policy-input" maxLength={300} required value={question} onChange={(e) => setQuestion(e.target.value)}
                 placeholder="例如：出發前一週取消可以退多少？" aria-label="要查的規定問題" />
          <button type="submit">搜尋</button>
        </div>
        <div id="policy-results" className="policy-results" aria-live="polite">
          {error && <p className="message">{error}</p>}
          {results && !results.length && <p>規定文件中找不到相關內容。</p>}
          {results?.map((item) => (
            <div key={item.source} className="policy-hit">
              <strong>{item.source}</strong>
              <small>{`相似度 ${item.score}`}</small>
              <p className="policy-text">{item.content}</p>
            </div>
          ))}
        </div>
      </form>
      <div id="policy-list">
        {docs.map((doc) => (
          <details key={doc.doc} className="panel">
            <summary>{`${doc.doc}（${doc.articles.length} 條）`}</summary>
            {doc.articles.map((item) => (
              <React.Fragment key={item.article}>
                <h3>{`${item.article} ${item.title}`}</h3>
                <p className="policy-text">{item.content}</p>
              </React.Fragment>
            ))}
          </details>
        ))}
      </div>
    </section>
  );
}
