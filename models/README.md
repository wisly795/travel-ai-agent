# 模型檔

`finetuned/`：微調過的 RAG 向量模型（ONNX，int8 量化），由 `tools/finetune/train.py` 產生。
檔案約 100 MB 以上，不放進 Git。沒有這個資料夾時，系統自動改用原始多語模型，功能照常。

重新產生：
```
docker build -t travelquote-finetune tools/finetune
docker run --rm -v <專案資料夾>:/p travelquote-finetune python /p/tools/finetune/train.py
```
