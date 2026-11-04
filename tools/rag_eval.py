"""RAG 檢索評測（不花 API 額度）：每題問法都和條文用字不同，檢查正確條文有沒有排在前 3 名。

在 app 容器內執行：python rag_eval.py
"""
from app import rag

# (客人可能的問法, 應該找到的「文件 條號」)；None 代表文件沒有相關內容，應該回空清單
CASES = [
    ("出發前一週不去了可以退多少錢", "取消與退費規定 第3條"),
    ("錢什麼時候會退回來", "取消與退費規定 第4條"),
    ("人數不夠會不會開團", "取消與退費規定 第5條"),
    ("颱風來了沒辦法出發怎麼辦", "取消與退費規定 第6條"),
    ("行李箱可以帶多重", "行李規定 第1條"),
    ("充電寶可以放託運嗎", "行李規定 第4條"),
    ("去沖繩要辦簽證嗎", "簽證與入境說明 第2條"),
    ("護照快過期了還能出國嗎", "簽證與入境說明 第1條"),
    ("去花蓮要帶護照嗎", "簽證與入境說明 第4條"),
    ("生病看醫生保險有賠嗎", "旅遊保險說明 第2條"),
    ("尾款要什麼時候付", "付款與發票規定 第1條"),
    ("可以刷卡分期嗎", "付款與發票規定 第2條"),
    ("報價單多久會失效", "付款與發票規定 第4條"),
    ("三歲小孩怎麼收費", "兒童、長者與特殊需求 第1條"),
    ("我吃素可以嗎", "兒童、長者與特殊需求 第4條"),
    ("可以帶狗狗去嗎", "兒童、長者與特殊需求 第5條"),
    ("今天天氣如何", None),
    ("推薦我好看的電影", None),
]

# 已知弱點：口語用字和條文差太多，小型向量模型找不到；靠 AI 換說法再查（見 docs/錯誤紀錄.md B-1）。
KNOWN_WEAK = {"人數不夠會不會開團"}


def main():
    print("向量模型：", rag.EMBED_MODEL, "　門檻：", rag.MIN_SCORE)
    top1 = top3 = empty_ok = 0
    weak_missed = 0
    for question, expected in CASES:
        results = rag.search(question)
        sources = [" ".join(r["source"].split()[:2]) for r in results]
        if expected is None:
            ok = not results
            empty_ok += ok
            print("PASS" if ok else "FAIL", question, "→", sources or "無結果")
            continue
        hit1 = bool(sources) and sources[0] == expected
        hit3 = expected in sources
        top1 += hit1
        top3 += hit3
        score = results[sources.index(expected)]["score"] if hit3 else "-"
        weak = question in KNOWN_WEAK and not hit3
        weak_missed += weak
        label = "WEAK" if weak else "PASS" if hit3 else "FAIL"
        print(label, f"{'第1名' if hit1 else '前3名' if hit3 else '沒找到'}", question, "→", sources[:3], score)

    answerable = sum(1 for _, e in CASES if e)
    print(f"\n第 1 名命中：{top1}/{answerable}　前 3 名命中：{top3}/{answerable}"
          f"（其中已知弱點未命中 {weak_missed} 題）　無關問題回空：{empty_ok}/{len(CASES) - answerable}")
    passed = top3 + weak_missed == answerable and empty_ok == len(CASES) - answerable
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
