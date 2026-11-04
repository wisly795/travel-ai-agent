"""比較 RAG 原始模型與微調模型（不花 API 額度，不改資料庫）。

在 app 容器內執行：python rag_compare.py
用正式系統同一套程式（fastembed）算向量，兩個模型都：
1. 只用驗證題（VAL）挑相似度門檻
2. 用測試題（TEST＋rag_eval 的 18 題）評分；測試題從未拿來訓練或挑門檻
"""
import json
import sys

import numpy as np

from app import rag
from finetune.dataset import TEST, VAL, check_no_overlap, key
from rag_eval import CASES as EVAL_CASES

def as_case(question, expected):
    if expected is None:
        return question, None
    doc, article = expected.split()
    return question, (doc, int(article[1:-1]))


EVAL = [as_case(q, e) for q, e in EVAL_CASES]


def score_all(name, cases, chunks, doc_vecs):
    q_vecs = np.array(rag.embed([q for q, _ in cases], name))
    q_vecs /= np.linalg.norm(q_vecs, axis=1, keepdims=True)
    keys = [f"{c['doc']} {c['article']}" for c in chunks]
    rows = []
    for (q, t), vec in zip(cases, q_vecs):
        sims = doc_vecs @ vec
        order = np.argsort(-sims)
        rows.append({"q": q, "expected": key(*t) if t else None,
                     "ranked": [(keys[i], float(sims[i])) for i in order[:3]]})
    return rows


def judge(rows, threshold):
    """門檻套用後的結果：有答案的題目要在前 3 名，無關的題目要回空。"""
    out = {"top1": 0, "top3": 0, "answerable": 0, "reject_ok": 0, "unrelated": 0, "misses": []}
    for r in rows:
        kept = [k for k, s in r["ranked"] if s >= threshold]
        if r["expected"] is None:
            out["unrelated"] += 1
            ok = not kept
            out["reject_ok"] += ok
            if not ok:
                out["misses"].append(f"無關題卻找到 {kept[0]}：{r['q']}（{r['ranked'][0][1]:.3f}）")
        else:
            out["answerable"] += 1
            out["top1"] += bool(kept) and kept[0] == r["expected"]
            hit = r["expected"] in kept
            out["top3"] += hit
            if not hit:
                out["misses"].append(f"沒找到 {r['expected']}：{r['q']}（第 1 名 {r['ranked'][0][0]} {r['ranked'][0][1]:.3f}）")
    return out


def pick_threshold(rows):
    best = None
    for t in np.arange(0.10, 0.90, 0.01):
        j = judge(rows, t)
        total = j["top3"] + j["reject_ok"]
        if best is None or total > best[0]:
            best = (total, [round(float(t), 2)])
        elif total == best[0]:
            best[1].append(round(float(t), 2))
    ties = best[1]
    return ties[len(ties) // 2]  # 同分取中間值，離兩邊都最遠


def main():
    check_no_overlap(q for q, _ in EVAL_CASES)
    chunks = rag.load_documents()
    names = [rag.BASE_MODEL]
    if (rag.FINETUNED_DIR / "model.onnx").exists():
        names.append(rag.FINETUNED_MODEL)
    report = {}
    for name in names:
        texts = [f"{c['doc']}｜{c['title']}：{c['content']}" for c in chunks]
        doc_vecs = np.array(rag.embed(texts, name))
        doc_vecs /= np.linalg.norm(doc_vecs, axis=1, keepdims=True)
        scored = {label: score_all(name, cases, chunks, doc_vecs)
                  for label, cases in (("VAL", VAL), ("TEST", TEST), ("rag_eval", EVAL))}
        picked = pick_threshold(scored["VAL"])
        report[name] = {"picked_threshold": picked}
        for kind, threshold in (("驗證題挑的門檻", picked), ("系統目前設定", rag.MIN_SCORES[name])):
            result = {label: judge(rows, threshold) for label, rows in scored.items()}
            report[name][f"{kind} {threshold}"] = result
            print(f"\n== {name}　{kind} {threshold}")
            for label, j in result.items():
                print(f"{label:8} 第1名 {j['top1']}/{j['answerable']}　前3名 {j['top3']}/{j['answerable']}　"
                      f"無關回空 {j['reject_ok']}/{j['unrelated']}")
                for m in j["misses"]:
                    print("   ", m)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
