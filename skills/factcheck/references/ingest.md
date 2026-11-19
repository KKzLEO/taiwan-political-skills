# 讀入：產出 `source.json`

```json
{
  "input_type": "url | text | image | video",
  "original_text": "要查的完整內容（新聞全文、轉傳文字、截圖文字、影片逐字稿）",
  "url": "原始網址或 null",
  "outlet": "媒體名稱或 null",
  "byline": "記者署名原文或 null",
  "published_at": "發布時間（ISO 8601，例如 2025-09-26T10:00:00+08:00）；內容本身看不到完整的年月日就填 null",
  "retrieved_at": "取得時間（ISO 8601，台灣時間）",
  "notes": "取得方式、限制"
}
```

| 輸入 | 怎麼做 |
|---|---|
| 新聞網址 | 用網頁工具讀全文。保留標題、內文、記者署名、發布和更新時間。付費牆或讀不到全文時，`notes` 寫清楚，`original_text` 只放讀得到的部分。`url` 由程式照使用者給的網址填，分享追蹤碼（`utm_`、`fbclid` 這類）由程式去掉 |
| 貼上的文字 | 原文由程式照 `input.json` 填進 `original_text`，不用填 |
| 截圖 | `content` 是主體照畫面抄下來的文字，由程式填進 `original_text`。`[辨識不清]` 是主體看不清楚的字，不要猜。`notes` 寫「沒有判斷圖片是否偽造」 |
| 影片 | `content` 是主體備好的逐字稿（上傳者自己放的字幕，或使用者提供的逐字稿），由程式填進 `original_text`。`notes` 寫「沒有判斷影片是否為 AI 合成」 |

