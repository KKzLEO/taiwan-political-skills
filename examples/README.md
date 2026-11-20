# 實際執行的範例

每個資料夾都是一次完整查核的所有紀錄，任何人都可以檢查報告是怎麼得出來的：

```bash
python3 skills/factcheck/scripts/fc.py status --run examples/<資料夾>
```

把資料夾複製出來（名稱不要改）執行 `fc.py render --run <複本>`，會得到一模一樣的 `report.md`。

| 資料夾 | 輸入 | 結果 | 主體 | 席位 | 時間 |
|---|---|---|---|---|---|
| `20261120-1441-機車大燈罰三千` | LINE 轉傳文字 | 不符｜可信度 0｜信心度 高（100）｜可公開 | Claude Code | A、B、C（Claude Fable 5.2，推理強度 xhigh）、X1（Codex，推理強度 high） | 48 分鐘 |
| `20261120-2249-garbage-truck-broadcast` | 針對蔣萬安的流傳說法 | 無法判定｜可信度 —｜信心度 高（90）｜不可公開 | Claude Code | A、B、C（Claude Fable 5.2，推理強度 xhigh）、X1（Codex，推理強度 high） | 34 分鐘 |
| `20261121-0238-shen-kickback-recording` | 針對沈伯洋的流傳說法 | 不符｜可信度 0｜信心度 高（100）｜可公開 | Claude Code | A、B、C（Claude Fable 5.2，推理強度 xhigh）、X1（Codex，推理強度 high） | 37 分鐘 |
| `20261121-0315-taipei-debt-400yi` | 蔣萬安的辯論會發言 | 符合｜可信度 90｜信心度 高（90）｜可公開 | Claude Code | A、B、C（Claude Fable 5.2，推理強度 xhigh）、X1（Codex，推理強度 high） | 42 分鐘 |
| `20261121-0357-shen-7599-urban-renewal` | 沈伯洋的辯論會發言 | 符合｜可信度 80｜信心度 高（90）｜可公開 | Claude Code | A、B、C（Claude Fable 5.2，推理強度 xhigh）、X1（Codex，推理強度 high） | 35 分鐘 |

- 第一則（機車大燈）是 0.2.0 發版前的真實主體實測：用無人值守的 `claude -p` 載入這個外掛，只給 `prompt.txt` 裡那一句話，中途沒有人介入。經過寫在 `evals/results/2026-11-20-hosts.md`。
- 後面四則是 2026 年台北市長選舉的四則說法，選哪四則、怎麼跑在開跑前登記（`evals/results/2026-11-20-taipei-preregistration.md`），結果和實際經過寫在 `evals/results/2026-11-21-taipei.md`。跑法和第一則相同。其中錄音那一則第一次跑到一半因為額度用完中斷，資料夾裡是整則重跑的結果。
- `report.md` 不列操弄手法（原因見 README 的「已知限制」）；標記留在 `trace.json` 和 `verdicts.json`。
- `models.json` 記的是指令名稱，沒有執行者電腦上的路徑。
- 0.1.0 的舊範例（`20261117-機車大燈罰三千`，舊格式）已經移除，要看可以翻 git 歷史。
