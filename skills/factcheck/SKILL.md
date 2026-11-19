---
name: factcheck
description: 查核使用者收到的訊息是否正確，並用「一個正方對三個反方」加上跨模型抗辯的方式驗證，產出附出處、可以重現的查核報告與光譜量表。支援新聞網址、LINE 轉傳文字、截圖、影片連結。會做傳播溯源、媒體背景、記者署名、用詞中立、公眾人物發言核對、法條原文查證、操弄手法辨識。觸發詞：查核、這是真的嗎、假新聞、謠言、幫我查證、事實查核、他真的說過嗎、fact-check、is this true、verify this claim。不適用：純意見討論、預測未來、要求替某一方寫文宣。
---

# 訊息查核

把一則訊息拆成命題，由獨立的子程序擔任溯源員、正方、三個反方、裁判，再找另一家模型當外部反方，最後由腳本套固定規則算分、產報告。

**你（主 agent）只負責收集輸入、安排流程和執行腳本。** 你看得到使用者的記憶和原始提問，所以不拆題、不參與判定、不當任何辯論角色，也不把自己的看法寫進任何角色的指令。

## 準備

下面的指令裡，`$SKILL` 是這個 skill 的資料夾，`$RUN` 是第 0 步建立的查核資料夾。**每次執行指令都要把兩個都寫成完整路徑**（例如開頭寫 `SKILL=/完整/路徑; RUN=/完整/路徑;`），因為每個指令可能在新的 shell 裡執行，變數不會保留。

需要 Python 3.11 以上。

**第 2 步以後的角色都用 `fc.py run-model` 執行，** 它會自己檢查格式、重試一次。重試後只剩下面兩種錯誤時，它會自動走退路，流程繼續；原內容都保留在檔案裡：
- **手法標記不合格：** 移出，報告不列出。手法標記不影響分數，不值得因此停掉整次查核。
- **裁判判附證據的攻擊成立，卻沒列出實際核對過的網址：** 判決照用，報告開頭會註明，這份報告不能標「可公開」。

其他錯誤時，讀入與拆題、溯源員、正方、答辯、裁判會以非零結束碼停止。這時停下來，告訴使用者是哪一步出錯，**不要自己重跑或補檔**。

### 0. 建立資料夾、偵測模型

1. **模式：** 預設完整模式。使用者說「快速」「簡單查一下」才用快速模式。先告訴使用者：完整模式實測短訊息約 20–35 分鐘、新聞或長訊息約 50–90 分鐘，角色的子程序會用掉上百萬 token；快速模式也要 20 到 40 分鐘，而且報告不能標「可公開」。
2. 建立資料夾：
   ```bash
   RUN=$(python3 "$SKILL/scripts/fc.py" init --mode full --host <claude 或 codex> --slug <幾個字的主題>)
   ```
3. 偵測模型（`--probe` 會實際呼叫每個外部 CLI 一次，確認有登入、能不能上網、讀不讀得到使用者設定）：
   ```bash
   python3 "$SKILL/scripts/fc.py" detect --run "$RUN" --probe
   ```
   Claude Code 上要另外加 `--host-model` 和 `--host-effort`，見 host-claude.md。把列出的席位告訴使用者。沒有任何外部席位時，提醒他報告的信心度會扣 20 分，可以裝 Codex、Claude Code 或 Gemini CLI 補上。
4. **中斷後重跑：** 先執行 `python3 "$SKILL/scripts/fc.py" status --run "$RUN"`，標「完成」的步驟直接跳過。

### 1. 收集輸入 → `input.json`

把使用者給的內容原封不動交給程式，不摘要、不改寫。使用者給的文字和網址一律先用檔案工具存成檔案，**不要放進指令列**，因為 shell 會吃掉或執行裡面的 `$`、反引號、引號：
- `$RUN/prompt.txt`：使用者這次怎麼問，照抄（例如「這是不是又在騙人？」）。裡面的立場由下一步判斷。
- `$RUN/message.txt`：要查的內容，見下表。
- `$RUN/url.txt`：網址，見下表。

| 輸入 | 怎麼做 |
|---|---|
| 貼上的文字 | 訊息原文存成 `$RUN/message.txt`，執行 `fc.py input --run "$RUN" --type text --file "$RUN/message.txt" --prompt-file "$RUN/prompt.txt"` |
| 新聞網址 | 網址存成 `$RUN/url.txt`，執行 `fc.py input --run "$RUN" --type url --url-file "$RUN/url.txt" --prompt-file "$RUN/prompt.txt"`，全文由下一步的子程序自己讀 |
| 截圖 | 逐字抄下畫面上的所有文字，連同帳號名稱、時間、平台，存成 `$RUN/message.txt`。看不清楚的字寫 `[辨識不清]`，不要猜，也不要判斷圖片真假。再用 `--type image --file` 執行 |
| 影片 | 網址存成 `$RUN/url.txt`，執行 `fc.py video --url-file "$RUN/url.txt" --out "$RUN/transcript.txt"`，成功的話用 `--type video --file "$RUN/transcript.txt" --url-file "$RUN/url.txt"`。沒有字幕時，有裝 whisper 可以轉文字，或請使用者提供逐字稿；都沒有就停止 |

完全無法上網就停止，告訴使用者這次沒辦法查核，不要只靠記憶回答。

### 2. 讀入與拆題 → `source.json`、`claims.json`

```bash
python3 "$SKILL/scripts/fc.py" run-model --run "$RUN" --role prep
```

由獨立的子程序照 [references/ingest.md](references/ingest.md) 和 [references/neutralize.md](references/neutralize.md) 做，它看不到你的記憶和這段對話。文字、截圖、影片的原文由程式照 `input.json` 填寫，子程序改不了；網址輸入的全文由子程序自己讀取。

### 3–8. 辯論

每個角色都用 `fc.py run-model` 開一個獨立的子程序執行。各平台另外要注意的事：

- Claude Code → [references/host-claude.md](references/host-claude.md)
- Codex → [references/host-codex.md](references/host-codex.md)

順序（每一步完成，才進下一步）：

| 步驟 | 角色 | 指令參數 | 產出 |
|---|---|---|---|
| 3 | 溯源員 | `--role tracer` | `trace.json` |
| 4 | 正方 | `--role proponent` | `proponent.json` |
| 5 | 所有反方，**同時派出** | `--role opponent --seat <A/B/C/X1…>` | `opponent-<席位>.json` |
| 6 | 正方答辯 | `--role rebuttal` | `rebuttal.json` |
| 7 | 裁判 | `--role judge` | `judgment.json` |
| 8 | 覆核：`python3 "$SKILL/scripts/fc.py" reviewers --run "$RUN"` 列出的每個席位 | `--role review --seat <席位>` | `review-<席位>.json` |

```bash
python3 "$SKILL/scripts/fc.py" run-model --run "$RUN" --role tracer     # 第 4、6、7 步換成 proponent、rebuttal、judge
```

第 5 步所有反方同時跑，放在同一個指令裡：

```bash
for s in $(python3 -c "import json,sys;print(' '.join(x['seat'] for x in json.load(open(sys.argv[1]))['seats']))" "$RUN/models.json"); do
  python3 "$SKILL/scripts/fc.py" run-model --run "$RUN" --role opponent --seat "$s" &
done
wait
```

第 8 步：`fc.py reviewers` 列出的每個席位，各跑一次 `--role review --seat <席位>`，可以同時跑。沒有列出任何席位就跳過。

- 第 5 步的席位以 `models.json` 的 `seats` 為準：完整模式是 A、B、C 加每個外部模型，快速模式只有一席。A、B、C 用主體的模型，X 席位用對應的外部 CLI。
- 反方席位失敗時會被記成 `failed`，流程繼續：
  - 外部席位（X 開頭）全部失敗，照規則扣信心度。
  - 完整模式少了 A、B、C 任何一席（失敗或沒有執行），報告不能標「可公開」。

### 9. 結算

```bash
python3 "$SKILL/scripts/fc.py" finalize --run "$RUN" && python3 "$SKILL/scripts/fc.py" score --run "$RUN" && python3 "$SKILL/scripts/fc.py" render --run "$RUN"
```

### 10. 回報使用者

- 第一行是 `report.md` 裡的結果行（結果、可信度、信心度、模式、可公開與否），接著是光譜量表。
- 再用三到五行說明核心命題的判定和最關鍵的證據，最後附上 `report.md` 的路徑。
- **不要改寫或「潤飾」判定。** 報告怎麼寫就怎麼轉述。分數由腳本決定，你不能調整。結果行寫了「不調整重要性的話是…」時，兩個結果都要轉述。
- 報告沒有標「可公開」時，提醒使用者不要拿去公開貼文。
- 標了「可公開」也提醒使用者：這不保證結論正確，公開貼文前先看過證據。

## 特殊狀況

- **社群平台原始貼文抓不到**（Facebook、Instagram、Threads 常擋自動存取）：先請使用者貼上貼文連結或截圖。只有使用者明確要求、而且你有瀏覽器工具時，才可以用他自己的登入狀態去抓；動手前先警告：這可能違反 Meta 的服務條款，帳號有被鎖的風險。
- **涉及法條：** 正方會到全國法規資料庫查條文原文。角色在隔離的子程序裡跑，用不到法規 MCP。報告的法條區塊一律標「非法律意見」。
- **追到一般民眾：** 不追查真實身分，背景調查只做媒體和公眾人物。
- **使用者要求「判他錯」「幫我反駁」：** 照樣跑中立流程，結果照實回報。

## 參考

- 判定、證據、來源層級的共同規則：[references/roles/_common.md](references/roles/_common.md)
- 分數和信心度怎麼算：[references/scoring.md](references/scoring.md)
