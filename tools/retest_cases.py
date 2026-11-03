"""修改規則後重測第 9、14 題（會花一點 API 額度）。在 app 容器內執行。"""
import json
import urllib.request

for message in ["每人預算 5000 去京都", "我是杜正威"]:
    body = json.dumps({"message": message}).encode()
    request = urllib.request.Request("http://localhost:8000/api/chat", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read())
    print(f"\n客人：{message}\nAI：{data['reply']}\n工具：{data['tools_used']}")
