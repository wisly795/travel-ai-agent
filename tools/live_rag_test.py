"""用真的 Claude 測 RAG 規定問答（會花一點 API 額度）。在 app 容器內執行。"""
import json
import urllib.request

QUESTIONS = [
    "出發前 7 天取消，團費 107,200 元可以退多少？",
    "人數不夠會不會開團？",
    "去沖繩要辦簽證嗎？",
    "充電寶可以放託運行李嗎？",
    "三歲小孩怎麼收費？",
    "可以在飛機上抽菸嗎？",
    "可以帶我的倉鼠一起去嗎？",
]

for question in QUESTIONS:
    body = json.dumps({"message": question}).encode()
    request = urllib.request.Request("http://localhost:8000/api/chat", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read())
    print(f"\n客人：{question}\nAI：{data['reply']}\n工具：{data['tools_used']}")
