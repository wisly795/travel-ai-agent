"""H6 評測機制本身的測試（不花 API 額度）：評分規則、題組完整、用假 AI 跑一輪確認存檔與清理。

在 app 容器內執行：python eval_test.py
"""
import json
from types import SimpleNamespace

from app import agent, evals
from app.db import query

results = []


def check(name, passed, detail=""):
    results.append(passed)
    print(("PASS" if passed else "FAIL"), name, detail)


# 1. 評分規則
g = evals.grade
check("全部通過回空清單", g({"all": ["48,000"], "tools": ["calculate_quote"]}, "總價 NT$ 48,000", ["calculate_quote"], False) == [])
check("缺金額", "回答缺少「48,000」" in g({"all": ["48,000"]}, "總價 NT$ 50,000", [], False))
check("任一關鍵字", g({"any": ["無法", "不能"]}, "抱歉不能打折", [], False) == [])
check("不該出現的字", g({"none": ["先生"]}, "杜先生您好", [], False) == ["回答不該出現「先生」"])
check("沒用到工具", g({"tools": ["search_policy"]}, "x", ["search_packages"], False) == ["沒有使用工具 search_policy"])
check("用了不該用的工具", g({"no_tools": ["create_quote"]}, "x", ["create_quote"], False) == ["不該使用工具 create_quote"])
check("條文出處（有）", g({"cite": True}, "依規定（取消與退費規定 第3條）", [], False) == [])
check("條文出處（沒有）", g({"cite": True}, "依規定辦理", [], False) == ["沒有附條文出處"])
check("必須建立報價", g({"quote": True}, "x", [], False) == ["沒有建立報價單"])

# 2. 題組
cases = evals.cases()
check("題組 20 題、題號不重複", len(cases) == 20 and len({c[0] for c in cases}) == 20)
check("涵蓋 7 種類別", {c[1] for c in cases} == {"報價", "邊界", "查無資料", "安全", "規定", "退費", "多輪"})

# 3. 用假 AI 跑一輪：存檔、分數、清理
class Block(SimpleNamespace):
    def model_dump(self, mode="python", exclude_none=False):
        return dict(vars(self))


class FakeClient:
    def __init__(self):
        self.messages = self
        self.beta = self

    def create(self, **kwargs):
        usage = SimpleNamespace(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=0, cache_read_input_tokens=0)
        return SimpleNamespace(stop_reason="end_turn", content=[Block(type="text", text="（假回答）總價 NT$ 48,000")], usage=usage)


first_turn = query("SELECT coalesce(max(id), 0) AS n FROM ai_turns")[0]["n"]
agent._client = FakeClient()
agent.DAILY_CHAT_LIMIT, agent.DAILY_COST_LIMIT_USD = 10**6, 10**6
latest = evals.run("假 AI 測試")
check("跑完 20 題並存檔", latest["total"] == 20 and len(latest["results"]) == 20)
q01 = next(r for r in latest["results"] if r["case_id"] == "Q01")
check("假回答 Q01 金額對但沒用工具 → 不通過", not q01["passed"] and "沒有使用工具 calculate_quote" in q01["failures"])
check("分數 = 通過題數", latest["passed"] == sum(r["passed"] for r in latest["results"]))
check("類別統計", sum(c["total"] for c in latest["by_category"]) == 20)

# 清掉假的評測與用量
query("DELETE FROM eval_results WHERE run_id = %s RETURNING id", (latest["id"],))
query("DELETE FROM eval_runs WHERE id = %s RETURNING id", (latest["id"],))
query("DELETE FROM ai_tool_calls WHERE turn_id > %s RETURNING id", (first_turn,))
query("DELETE FROM ai_turns WHERE id > %s RETURNING id", (first_turn,))
agent._client = None

print(f"\n{sum(results)}/{len(results)} 通過")
raise SystemExit(0 if all(results) else 1)
