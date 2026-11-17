# 實際執行的範例

每個資料夾都是一次完整查核的所有紀錄，可以用 `python3 skills/factcheck/scripts/fc.py status --run <資料夾>` 檢查每一步的格式，用 `score` 和 `render` 重新產生分數和報告，結果會完全一樣。

| 資料夾 | 輸入 | 結果 | 主體 | 席位 |
|---|---|---|---|---|
| `20261117-機車大燈罰三千` | LINE 轉傳文字 | 不符｜可信度 0｜信心度 高（100） | Claude Code | A、B、C（Claude）、X1（Codex） |

`models.json` 裡的 CLI 路徑已經改成指令名稱，避免洩漏執行者的家目錄。
