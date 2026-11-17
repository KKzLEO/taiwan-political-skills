# 讀入：產出 `source.json`

```json
{
  "input_type": "url | text | image | video",
  "original_text": "要查的完整內容（新聞全文、轉傳文字、截圖文字、影片逐字稿）",
  "url": "原始網址或 null",
  "outlet": "媒體名稱或 null",
  "byline": "記者署名原文或 null",
  "published_at": "發布時間或 null",
  "retrieved_at": "取得時間（ISO 8601，台灣時間）",
  "notes": "取得方式、限制"
}
```

| 輸入 | 怎麼做 |
|---|---|
| 新聞網址 | 用平台的網頁工具抓全文。保留標題、內文、記者署名、發布和更新時間；移除追蹤參數（`utm_` 等），但不要改變實際網址。付費牆或抓不到全文時，`notes` 寫清楚，只用看得到的部分 |
| 貼上的文字 | 原文照抄進 `original_text`，不修改、不摘要 |
| 截圖 | 讀出畫面上的所有文字，連同介面上看得到的帳號名稱、時間、平台。看不清楚的字寫 `[辨識不清]`，不要猜。人名、數字、日期、法條、網址要特別再核對一次。**不判斷圖片是否偽造**，這一點寫進 `notes` |
| 影片 | 執行 `python3 "$SKILL/scripts/fc.py" video <網址> --out "$RUN/transcript.txt"`，成功的話把逐字稿放進 `original_text`。沒有字幕時，如果有裝 whisper 可以轉文字；都沒有就請使用者提供逐字稿。還是沒有的話，`notes` 寫「未取得逐字稿」。**不判斷影片是否為 AI 合成**，這一點寫進 `notes` |

使用者同時給了多種輸入（例如截圖加說明文字），全部放進 `original_text`，並在 `notes` 說明各段的來源。

寫完執行 `python3 "$SKILL/scripts/fc.py" validate --run "$RUN" source.json`。
