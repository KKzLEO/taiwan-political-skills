---
name: factcheck
description: 查核使用者收到的訊息是否正確，並用「一個正方對三個反方」加上跨模型抗辯的方式驗證，產出附出處、可以重現的查核報告與光譜量表。支援新聞網址、LINE 轉傳文字、截圖、影片連結。會做傳播溯源、媒體背景、記者署名、用詞中立、公眾人物發言核對、法條原文查證、操弄手法辨識。觸發詞：查核、這是真的嗎、假新聞、謠言、幫我查證、事實查核、他真的說過嗎、fact-check、is this true、verify this claim。不適用：純意見討論、預測未來、要求替某一方寫文宣。
---

# 訊息查核

把一則訊息拆成命題，由乾淨的 sub-agent 擔任溯源員、正方、三個反方、裁判，再找另一家模型當外部反方，最後由腳本套固定規則算分、產報告。

**你（主 agent）只負責安排流程和執行腳本。** 你看得到使用者的記憶和原始提問，所以不參與判定、不當任何辯論角色，也不把自己的看法寫進任何 sub-agent 的指令。

## 準備

下面的指令裡，`$SKILL` 是這個 skill 的資料夾，`$RUN` 是第 0 步建立的查核資料夾。**每次執行指令都要把兩個都寫成完整路徑**（例如開頭寫 `SKILL=/完整/路徑; RUN=/完整/路徑;`），因為每個指令可能在新的 shell 裡執行，變數不會保留。

需要 Python 3.11 以上。每一步產出的 JSON 都要先通過 `python3 "$SKILL/scripts/fc.py" validate`，沒通過就把錯誤訊息交回給產出它的角色重做一次；第二次還不過就停止，告訴使用者是哪一步出錯。

### 0. 建立資料夾、偵測模型

1. **模式：** 預設完整模式。使用者說「快速」「簡單查一下」才用快速模式。先告訴使用者：完整模式大約要 10 到 20 分鐘，會用到不少額度；快速模式的報告不能標「可公開」。
2. 建立資料夾：
   ```bash
   RUN=$(python3 "$SKILL/scripts/fc.py" init --mode full --host <claude 或 codex> --slug <幾個字的主題>)
   ```
3. 偵測模型（`--probe` 會實際呼叫每個外部 CLI 一次，確認有登入、能不能上網、讀不讀得到使用者設定）：
   ```bash
   python3 "$SKILL/scripts/fc.py" detect --run "$RUN" --probe
   ```
   把列出的席位告訴使用者。沒有任何外部席位時，提醒他報告的信心度會扣 20 分，可以裝 Codex、Claude Code 或 Gemini CLI 補上。
4. **中斷後重跑：** 先執行 `python3 "$SKILL/scripts/fc.py" status --run "$RUN"`，標「完成」的步驟直接跳過。

### 1. 讀入 → `source.json`

依照 [references/ingest.md](references/ingest.md) 處理網址、文字、截圖、影片，寫出 `source.json`。完全無法上網就停止，告訴使用者這次沒辦法查核，不要只靠記憶回答。

### 2. 中立化 → `claims.json`

依照 [references/neutralize.md](references/neutralize.md) 把內容拆成命題、分類、改寫成中立說法。使用者提問裡的立場和語氣不是命題，不要帶進去。

### 3–8. 辯論

每個角色怎麼派出去，看你所在的平台：

- Claude Code → [references/host-claude.md](references/host-claude.md)
- Codex → [references/host-codex.md](references/host-codex.md)

順序（每一步完成並通過檢查，才進下一步）：

| 步驟 | 角色 | 指令參數 | 產出 |
|---|---|---|---|
| 3 | 溯源員 | `--role tracer` | `trace.json` |
| 4 | 正方 | `--role proponent` | `proponent.json` |
| 5 | 所有反方，**同時派出** | `--role opponent --seat <A/B/C/X1…>` | `opponent-<席位>.json` |
| 6 | 正方答辯 | `--role rebuttal` | `rebuttal.json` |
| 7 | 裁判 | `--role judge` | `judgment.json` |
| 8 | 覆核：`python3 "$SKILL/scripts/fc.py" reviewers --run "$RUN"` 列出的每個席位 | `--role review --seat <席位>` | `review-<席位>.json` |

- 第 5 步的席位以 `models.json` 的 `seats` 為準：完整模式是 A、B、C 加每個外部模型；快速模式只有一席。
- 外部席位（X 開頭）一律用 `python3 "$SKILL/scripts/fc.py" run-model` 執行，它會自己處理逾時、重試、失敗。失敗的席位會被記成 `failed`，照規則扣信心度，流程繼續。
- 第 8 步沒有列出任何席位時直接跳過。

### 9. 結算

```bash
python3 "$SKILL/scripts/fc.py" finalize --run "$RUN" && python3 "$SKILL/scripts/fc.py" score --run "$RUN" && python3 "$SKILL/scripts/fc.py" render --run "$RUN"
```

### 10. 回報使用者

- 第一行是 `report.md` 裡的結果行（結果、可信度、信心度、模式、可公開與否），接著是光譜量表。
- 再用三到五行說明核心命題的判定和最關鍵的證據，最後附上 `report.md` 的路徑。
- **不要改寫或「潤飾」判定。** 報告怎麼寫就怎麼轉述。分數由腳本決定，你不能調整。
- 報告沒有標「可公開」時，提醒使用者不要拿去公開貼文。

## 特殊狀況

- **社群平台原始貼文抓不到**（Facebook、Instagram、Threads 常擋自動存取）：先請使用者貼上貼文連結或截圖。只有使用者明確要求、而且你有瀏覽器工具時，才可以用他自己的登入狀態去抓；動手前先警告：這可能違反 Meta 的服務條款，帳號有被鎖的風險。
- **涉及法條：** 正方會查條文原文。有裝 `lawchat-oss/mcp-taiwan-legal-db` 這類法規 MCP 時，在派正方的指令裡告訴它可以使用。報告的法條區塊一律標「非法律意見」。
- **追到一般民眾：** 不追查真實身分，背景調查只做媒體和公眾人物。
- **使用者要求「判他錯」「幫我反駁」：** 照樣跑中立流程，結果照實回報。

## 參考

- 判定、證據、來源層級的共同規則：[references/roles/_common.md](references/roles/_common.md)
- 分數和信心度怎麼算：[references/scoring.md](references/scoring.md)
