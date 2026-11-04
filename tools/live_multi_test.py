"""多 Agent 真實 AI 抽測（會花少量額度，約 0.005 美元）：同時問報價與規定，看回答有沒有互相推給對方。

在 app 容器內執行：python live_multi_test.py
"""
from app import multi_agent

QUESTION = "4 個人去沖繩住海風飯店，海島放鬆 4 日多少錢？另外出發前一週取消會扣多少？"
result = multi_agent.chat(None, QUESTION)
print("經過：", " → ".join(step["agent"] for step in result["agents"]))
for step in result["agents"]:
    print("  ", step["agent"], "：", step["detail"])
print("工具：", result["tools_used"])
print("回答：\n" + result["reply"])
problems = [word for word in ("報價專員", "規定專員", "請洽", "轉接單") if word in result["reply"]]
has_price = "NT$" in result["reply"]
has_rule = "第3條" in result["reply"] or "第 3 條" in result["reply"]
print("\n檢查：有報價金額", has_price, "｜有退費條文", has_rule, "｜提到其他專員或轉接", problems or "無")
raise SystemExit(0 if has_price and has_rule and not problems else 1)
