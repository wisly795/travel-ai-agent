"""執行真實 AI 評測並產生報告（會花少量 API 額度，約 20–25 次對話）。

在 app 容器內執行：python ai_eval.py [說明文字] [single|multi]
報告寫到 /tmp/AI評測報告.md，再複製到 docs/評測/。multi＝測多 Agent 協作版。
"""
import sys

from app import evals

label = sys.argv[1] if len(sys.argv) > 1 else "命令列執行"
mode = sys.argv[2] if len(sys.argv) > 2 else "single"
result = evals.run(label, mode)
lines = [
    f"# AI 自動評測報告",
    "",
    f"- 時間：{result['finished_at']:%Y-%m-%d %H:%M}（UTC）",
    f"- 模型：{result['model']}",
    f"- 分數：**{result['passed']} / {result['total']}**（{result['passed'] * 100 // result['total']}%）",
    f"- 花費：US$ {result['cost_usd']:.4f}",
    f"- 說明：{result['label']}",
    "",
    "## 各類別",
    "| 類別 | 通過 |",
    "|---|---|",
    *[f"| {c['category']} | {c['passed']} / {c['total']} |" for c in result["by_category"]],
    "",
    "## 每題結果",
    "| 題號 | 類別 | 問題 | 結果 | 沒通過的原因 | 用到的工具 |",
    "|---|---|---|---|---|---|",
]
for r in result["results"]:
    lines.append(f"| {r['case_id']} | {r['category']} | {r['question']} | {'✅' if r['passed'] else '❌'} | "
                 f"{'；'.join(r['failures'])} | {'、'.join(dict.fromkeys(r['tools']))} |")
lines += ["", "## 未通過題目的 AI 回答", ""]
for r in result["results"]:
    if not r["passed"]:
        lines += [f"### {r['case_id']} {r['question']}", "", "```text", r["reply"], "```", ""]
open("/tmp/AI評測報告.md", "w", encoding="utf-8").write("\n".join(lines))
print(f"{result['passed']}/{result['total']} 通過，US$ {result['cost_usd']:.4f}")
for r in result["results"]:
    if not r["passed"]:
        print("未通過", r["case_id"], r["question"][:30], r["failures"])
