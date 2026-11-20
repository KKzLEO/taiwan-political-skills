# 實際執行的範例

每個資料夾都是一次完整查核的所有紀錄，任何人都可以檢查報告是怎麼得出來的：

```bash
python3 skills/factcheck/scripts/fc.py status --run examples/<資料夾>
```

把資料夾複製出來（名稱不要改）執行 `fc.py render --run <複本>`，會得到一模一樣的 `report.md`。

| 資料夾 | 輸入 | 結果 | 主體 | 席位 | 時間 |
|---|---|---|---|---|---|
| `20261120-1441-機車大燈罰三千` | LINE 轉傳文字 | 不符｜可信度 0｜信心度 高（100）｜可公開 | Claude Code | A、B、C（Claude Fable 5.2，推理強度 xhigh）、X1（Codex，推理強度 high） | 48 分鐘 |

- 這一則是 0.2.0 發版前的真實主體實測：用無人值守的 `claude -p` 載入這個外掛，只給 `prompt.txt` 裡那一句話，中途沒有人介入。經過寫在 `evals/results/2026-11-20-hosts.md`。
- `report.md` 不列操弄手法（原因見 README 的「已知限制」）；標記留在 `trace.json` 和 `verdicts.json`。
- `models.json` 記的是指令名稱，沒有執行者電腦上的路徑。
- 0.1.0 的舊範例（`20261117-機車大燈罰三千`，舊格式）已經移除，要看可以翻 git 歷史。
