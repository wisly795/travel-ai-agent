"""RAG：把旅遊規定切成一條一條、轉成向量存進 pgvector，查詢時找意思最接近的條文。"""
import hashlib
import os
import re
from pathlib import Path

from .db import connect, query

BASE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# 用旅遊問答微調過的版本（tools/finetune/train.py 產生）；有檔案就用它，RAG_MODEL=base 可切回原始模型
FINETUNED_MODEL = "travel/minilm-travel-finetuned"
FINETUNED_DIR = Path(os.environ.get("FINETUNED_DIR", "/code/models/finetuned"))
MODEL_DIR = os.environ.get("MODEL_DIR", "/models")
POLICY_DIR = Path(os.environ.get("POLICY_DIR", "/code/data/policies"))
# 相似度低於門檻就當作「文件沒有提到」，避免硬湊不相關的條文。
# 兩個模型的分數分布不同，門檻各自用驗證題挑選（tools/rag_compare.py）。
MIN_SCORES = {BASE_MODEL: 0.35, FINETUNED_MODEL: 0.35}


def pick_model(name=None):
    if name:
        return name
    if os.environ.get("RAG_MODEL", "finetuned") != "base" and (FINETUNED_DIR / "model.onnx").exists():
        return FINETUNED_MODEL
    return BASE_MODEL


EMBED_MODEL = pick_model()
MIN_SCORE = MIN_SCORES[EMBED_MODEL]

_models = {}


def model(name=None):
    name = name or EMBED_MODEL
    if name not in _models:
        from fastembed import TextEmbedding
        if name == FINETUNED_MODEL:
            from fastembed.common.model_description import ModelSource, PoolingType
            if FINETUNED_MODEL not in {m["model"] for m in TextEmbedding.list_supported_models()}:
                TextEmbedding.add_custom_model(model=FINETUNED_MODEL, pooling=PoolingType.MEAN, normalization=True,
                                               sources=ModelSource(hf=FINETUNED_MODEL), dim=384,
                                               model_file="model.onnx")
            _models[name] = TextEmbedding(FINETUNED_MODEL, specific_model_path=str(FINETUNED_DIR))
        else:
            _models[name] = TextEmbedding(name, cache_dir=MODEL_DIR)
    return _models[name]


def model_fingerprint():
    """模型名稱＋微調檔案內容；重新訓練後啟動時會自動重建向量。"""
    if EMBED_MODEL == FINETUNED_MODEL:
        return EMBED_MODEL.encode() + hashlib.sha256((FINETUNED_DIR / "model.onnx").read_bytes()).digest()
    return EMBED_MODEL.encode()


def info():
    return {"model": EMBED_MODEL, "finetuned": EMBED_MODEL == FINETUNED_MODEL, "min_score": MIN_SCORE}


def embed(texts, name=None):
    return [vector.tolist() for vector in model(name).embed(texts)]


def to_pg(vector):
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


def parse(path):
    """一個 Markdown 檔：第一行 # 是文件名稱，每個「## 第N條 標題」是一個段落。"""
    doc, chunks, current = None, [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            doc = line[2:].strip()
        elif match := re.match(r"## (第\d+條)\s*(.*)", line):
            current = {"doc": doc, "article": match[1], "title": match[2].strip(), "lines": []}
            chunks.append(current)
        elif current and line.strip() and not line.startswith(">"):
            current["lines"].append(line.strip())
    for chunk in chunks:
        chunk["content"] = "\n".join(chunk.pop("lines"))
    return chunks


def load_documents():
    return [chunk for path in sorted(POLICY_DIR.glob("*.md")) for chunk in parse(path)]


def sync():
    """文件內容有變才重新建立向量，啟動時呼叫。"""
    files = sorted(POLICY_DIR.glob("*.md"))
    digest = hashlib.sha256(b"".join(p.read_bytes() for p in files) + model_fingerprint()).hexdigest()
    stored = query("SELECT value FROM app_meta WHERE key = 'policy_hash'")
    if stored and stored[0]["value"] == digest:
        return False
    chunks = load_documents()
    vectors = embed([f"{c['doc']}｜{c['title']}：{c['content']}" for c in chunks])
    with connect() as conn:
        conn.execute("DELETE FROM policy_chunks")
        for chunk, vector in zip(chunks, vectors):
            conn.execute(
                "INSERT INTO policy_chunks (doc, article, title, content, embedding) VALUES (%s, %s, %s, %s, %s::vector)",
                (chunk["doc"], chunk["article"], chunk["title"], chunk["content"], to_pg(vector)),
            )
        conn.execute(
            "INSERT INTO app_meta (key, value) VALUES ('policy_hash', %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (digest,),
        )
    return True


def search(question, limit=3):
    vector = to_pg(embed([question])[0])
    rows = query(
        """
        SELECT doc, article, title, content, 1 - (embedding <=> %s::vector) AS score
        FROM policy_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (vector, vector, limit),
    )
    return [
        {
            "source": f"{row['doc']} {row['article']} {row['title']}",
            "content": row["content"],
            "score": round(float(row["score"]), 3),
        }
        for row in rows
        if row["score"] >= MIN_SCORE
    ]


def list_policies():
    rows = query("SELECT doc, article, title, content FROM policy_chunks ORDER BY id")
    docs = {}
    for row in rows:
        docs.setdefault(row["doc"], []).append(
            {"article": row["article"], "title": row["title"], "content": row["content"]}
        )
    return [{"doc": doc, "articles": articles} for doc, articles in docs.items()]
