"""微調 RAG 的向量模型，輸出成正式系統（fastembed）讀得懂的 ONNX 檔。

執行（約 5–10 分鐘，CPU 即可）：
  docker run --rm -v <專案>:/p travelquote-finetune python /p/tools/finetune/train.py

做法：
1. 每一題「客人口語問法」配上「正確條文」當一組，用 MultipleNegativesRankingLoss 訓練：
   拉近問題和正確條文的向量，同時推開同一批裡其他條文。
2. 每訓練一輪就用驗證題（VAL）評一次，留下分數最好的那一輪，避免越訓練越死背。
3. 輸出 ONNX 並做 int8 量化（檔案變小、速度變快），放到 models/finetuned/。
測試題（TEST）不在這裡評，交給 app 容器裡的 tools/rag_compare.py，用正式系統同一套流程比較。
"""
import json
import random
import re
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import InputExample, SentenceTransformer, losses
from sentence_transformers.datasets import NoDuplicatesDataLoader

sys.path.insert(0, str(Path(__file__).parent))
from dataset import TRAIN, VAL, check_no_overlap, key  # noqa: E402

ROOT = Path("/p")
BASE = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
OUT = ROOT / "models" / "finetuned"
WORK = Path("/tmp/ft")
EPOCHS, BATCH, LR = 6, 16, 2e-5

random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def load_articles():
    """和 backend/app/rag.py 同樣的切法與同樣的文字格式。"""
    articles = {}
    for path in sorted((ROOT / "data" / "policies").glob("*.md")):
        doc, current = None, None
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                doc = line[2:].strip()
            elif m := re.match(r"## (第\d+條)\s*(.*)", line):
                current = {"doc": doc, "article": m[1], "title": m[2].strip(), "lines": []}
                articles[f"{doc} {m[1]}"] = current
            elif current and line.strip() and not line.startswith(">"):
                current["lines"].append(line.strip())
    return {k: f"{a['doc']}｜{a['title']}：{chr(10).join(a['lines'])}" for k, a in articles.items()}


def evaluate(model, articles, cases):
    keys = list(articles)
    doc_vecs = model.encode([articles[k] for k in keys], normalize_embeddings=True)
    answerable = [(q, key(*t)) for q, t in cases if t]
    q_vecs = model.encode([q for q, _ in answerable], normalize_embeddings=True)
    top1 = top3 = 0
    mrr = 0.0
    for (q, expected), vec in zip(answerable, q_vecs):
        ranked = [keys[i] for i in np.argsort(-(doc_vecs @ vec))]
        rank = ranked.index(expected) + 1
        top1 += rank == 1
        top3 += rank <= 3
        mrr += 1 / rank
    n = len(answerable)
    return {"top1": top1 / n, "top3": top3 / n, "mrr": round(mrr / n, 4)}


def main():
    n_train, n_val, n_test = check_no_overlap()
    articles = load_articles()
    assert len(articles) == 29, len(articles)
    for t in TRAIN:
        assert key(*t) in articles, t
    print(f"條文 {len(articles)} 條；訓練 {n_train} 題、驗證 {n_val} 題、測試 {n_test} 題")

    examples = [InputExample(texts=[q, articles[key(*t)]]) for t, qs in TRAIN.items() for q in qs]
    model = SentenceTransformer(BASE, device="cpu")
    log = {"base_model": BASE, "epochs_max": EPOCHS, "batch": BATCH, "lr": LR, "train_pairs": len(examples),
           "history": [{"epoch": 0, **evaluate(model, articles, VAL)}]}
    print("訓練前 驗證題：", log["history"][0])

    best = log["history"][0]
    loss = losses.MultipleNegativesRankingLoss(model)
    for epoch in range(1, EPOCHS + 1):
        loader = NoDuplicatesDataLoader(examples, batch_size=BATCH)
        start = time.time()
        model.fit(train_objectives=[(loader, loss)], epochs=1, warmup_steps=5 if epoch == 1 else 0,
                  optimizer_params={"lr": LR}, show_progress_bar=False)
        score = {"epoch": epoch, **evaluate(model, articles, VAL), "seconds": round(time.time() - start)}
        log["history"].append(score)
        print(f"第 {epoch} 輪 驗證題：", score)
        if (score["mrr"], score["top3"]) > (best["mrr"], best["top3"]):
            best = score
            if WORK.exists():
                shutil.rmtree(WORK)
            model.save(str(WORK / "st"))
    log["best_epoch"] = best["epoch"]
    if best["epoch"] == 0:
        raise SystemExit("微調沒有讓驗證題變好，不輸出模型")
    print("選用第", best["epoch"], "輪")

    # 轉成 ONNX 並做 int8 動態量化
    from optimum.onnxruntime import ORTModelForFeatureExtraction, ORTQuantizer
    from optimum.onnxruntime.configuration import AutoQuantizationConfig
    onnx_dir = WORK / "onnx"
    ORTModelForFeatureExtraction.from_pretrained(str(WORK / "st"), export=True).save_pretrained(onnx_dir)
    ORTQuantizer.from_pretrained(onnx_dir).quantize(
        save_dir=WORK / "q", quantization_config=AutoQuantizationConfig.avx2(is_static=False, per_channel=False))

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copy(WORK / "q" / "model_quantized.onnx", OUT / "model.onnx")
    for name in ("tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "config.json",
                 "sentencepiece.bpe.model"):
        src = WORK / "st" / name
        if src.exists():
            shutil.copy(src, OUT / name)
    (OUT / "train_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    size = (OUT / "model.onnx").stat().st_size / 1024 / 1024
    print(f"完成：{OUT}（model.onnx {size:.0f} MB）")


if __name__ == "__main__":
    main()
