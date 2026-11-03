"""用真的 Claude 跑幾個代表情境（會花一點 API 額度）。在 app 容器內執行。"""
import json
import urllib.request

BASE = "http://localhost:8000"


def say(conversation_id, message):
    body = json.dumps({"conversation_id": conversation_id, "message": message}).encode()
    request = urllib.request.Request(BASE + "/api/chat", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read())
    print(f"\n客人：{message}\nAI：{data['reply']}\n工具：{data['tools_used']}")
    if data["quote"]:
        print("建立報價：", data["quote"]["id"], data["quote"]["total_price"])
    return data["conversation_id"]


cid = say(None, "4 個人想去沖繩，每人預算 3 萬，住哪間比較划算？")
cid = say(cid, "就選最便宜的行程和飯店，幫我算總價")
cid = say(cid, "可以打 5 折嗎？")
cid = say(cid, "好，就照原價，我叫測試小明，幫我建立報價單")
say(None, "出發前 7 天取消可以退多少錢？")
say(None, "有去火星的行程嗎？")
