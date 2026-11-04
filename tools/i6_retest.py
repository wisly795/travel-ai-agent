"""I6 人工驗收問題修正後的重測（會花少量 API 額度）：
問題 1～3 轉成的評測題 Q21～Q23，單一與多 Agent 各跑 3 次，全部通過才算修好。

在 app 容器內執行：python i6_retest.py
"""
import json

from app import evals
from app.db import query

TIMES = 3
targets = [c for c in evals.cases() if c[0] in ("Q21", "Q22", "Q23")]
results = []
for mode in ("single", "multi"):
    for case in targets:
        for n in range(1, TIMES + 1):
            r = evals.run_case(*case, mode=mode)
            results.append({"mode": mode, "case": case[0], "n": n, "passed": r["passed"], "failures": r["failures"],
                            "tools": r["tools"], "reply": r["reply"]})
            # 重測不是真的客人：AI 建立的轉接單刪掉
            query("DELETE FROM handoffs WHERE conversation_id = %s RETURNING id", (r["conversation_id"],))
            print(f"{'PASS' if r['passed'] else 'FAIL'} {mode:6} {case[0]} 第 {n} 次 {r['failures'] or ''}")
            print("   工具：", "、".join(r["tools"]))
            print("   回答：", r["reply"].replace("\n", " ")[:260])

passed = sum(r["passed"] for r in results)
print(f"\n{passed}/{len(results)} 通過")
with open("/tmp/i6_retest.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=1)
raise SystemExit(0 if passed == len(results) else 1)
