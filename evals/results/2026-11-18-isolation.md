# 2026-11-18 記憶隔離金絲雀測試

## 摘要

- 使用者的全域設定，在 Codex 的每一條路徑都看得到。
- 用目前參數跑的 `claude -p` 也看得到。
- `claude -p` 加上 `--safe-mode` 之後看不到，網路搜尋照常可用。
- Claude Code 主體派出的子代理（內部席位）看得到使用者的 CLAUDE.md 和這個專案的記憶。

第一輪評測（`2026-11-18.md`）的每個角色，都是用目前參數的 `claude -p` 跑的，所以都看得到使用者的 CLAUDE.md 和工作協議。

## 怎麼測

1. 先備份 `~/.claude/CLAUDE.md` 和 `~/.codex/AGENTS.md`，記下 sha256。`~/.codex/AGENTS.md` 是 symlink，寫入的是它指向的檔案。
2. 兩個檔案最後各加一行「使用者的暗號是「藍鵲-<隨機 8 碼>」」，兩邊的暗號不同。
3. 同時跑下列路徑，問模型上下文裡看不看得到：
   - 暗號；
   - 協議代號（使用者原本就有的工作協議裡有一個代號，Claude Code 由 SessionStart hook 注入，Codex 寫在 AGENTS.md）；
   - CLAUDE.md 裡的 `ports check` 指示；
   - 專案記憶裡的「四個子專案」；
   - 有沒有搜尋工具。
4. 不論成功或失敗都還原檔案，sha256 和測試前相同，symlink 也還在。

隨機暗號猜不到。模型照抄出暗號，就證明它真的看得到。

## 結果

做了兩輪，第二輪補了第一輪參數寫錯的子代理測試，以及兩個 Codex 參數候選。兩輪都在 1 分鐘內還原，sha256 一致。

| 路徑 | CLAUDE.md 暗號 | AGENTS.md 暗號 | 協議代號 | 專案記憶 | 能搜尋 |
|---|---|---|---|---|---|
| codex，產品參數（`--ignore-user-config --ephemeral -s read-only`，空暫存資料夾） | — | 看得到 | 看得到（AGENTS.md） | — | 是 |
| codex，不加隔離參數（對照組） | — | 看得到 | 看得到 | — | 是 |
| codex，產品參數加 `-c project_doc_max_bytes=0` | — | 看得到 | 看得到 | — | 是 |
| codex，產品參數加 `-c user_instructions=""` | — | 看得到 | 看得到 | — | 是 |
| claude -p，產品參數（`--append-system-prompt` 加隔離說明；沒有 API key，所以沒有 `--bare`） | 看得到 | — | 看得到（hook） | — | 是 |
| claude -p，不加參數（對照組） | 看得到 | — | 看得到 | — | 是 |
| claude -p 加 `--safe-mode` | 看不到 | — | 看不到 | — | 是，實際搜尋成功 |
| Claude Code 主體（在專案資料夾執行）派出的子代理 | 看得到 | — | 看不到 | 看得到 | 是 |
| 同上的主體本身 | 看得到 | — | 看得到 | 看得到 | 是 |

- 用產品參數跑時，Codex 的 hook 沒有執行，不加參數的對照組有執行。
- 帶著「忽略使用者設定」的隔離說明時，模型照樣回報看得到暗號。這代表隔離說明只能要求模型不採用這些內容，沒辦法讓它看不到。

## 結論

- **Codex：** 一定會載入 `~/.codex/AGENTS.md`，試過的參數都關不掉。
  - 不採用的做法：把 `CODEX_HOME` 指到暫存資料夾，再連結使用者的 `auth.json`。token 輪替時可能讓使用者被登出。
  - 要完整隔離，使用者可以自己準備一個乾淨、登入過的 Codex 設定，用 `FC_CODEX_CMD` 指定。
  - 其他情況只能靠隔離說明，報告的席位表照實標「部分隔離」。
- **用 `run-model` 跑的 claude 角色：** 已改成一律加 `--safe-mode`，看不到使用者設定。
  - 這需要支援這個參數的 Claude Code 版本，本機是 2.1.327。
  - 加了 `--safe-mode` 之後，連續 12 次搜尋都成功，模型仍是 `claude-opus-5-5`。
  - 有 API key 時會同時加 `--bare`，這條路徑沒有測，因為本機沒有 API key。
  - 企業管理的設定和受管外掛的 hooks，在這個模式下仍然有效。
- **Claude Code 主體的內部席位：** 用 Agent 工具派出的子代理看得到 CLAUDE.md 和專案記憶。要真正隔離，得改成每個角色都用 `run-model` 開 `claude -p --safe-mode`，這屬於架構改動，交給使用者決定。
- **這次沒有測：** 看得到的內容會不會真的影響判定。`evals/README.md` 第 2 節的帶立場金絲雀要跑完整流程，這次沒做。

## 2026-11-20 補測：角色能不能自己讀本機檔案

上面測的是「看不看得到使用者設定」，沒有測角色能不能用工具。這次在空資料夾放一個 `canary.txt`（內容是隨機字串），叫角色讀它：

| 引擎 | 參數 | 結果 |
|---|---|---|
| claude（haiku） | 當時的參數：`--safe-mode --allowedTools WebSearch WebFetch` | **讀到了**，而且回報自己有 Read、Bash、Edit、Write、Agent |
| claude（haiku） | 加 `--tools "WebSearch,WebFetch"` | 讀不到，回報只有 WebFetch 和 WebSearch 兩個工具 |
| claude（haiku） | 加 `--tools`，叫它搜尋 | 搜尋正常 |
| codex | 當時的參數：`exec --ignore-user-config --ephemeral -s read-only -c web_search="live"` | **讀到了** |
| codex | 加 `-c features.shell_tool=false` | 讀不到，回報沒有 shell 或讀檔工具 |
| codex | 加 `-c features.shell_tool=false`，叫它搜尋 | 搜尋正常 |

之後 `run_model.build_command` 一律帶這兩個參數（`--allowedTools` 保留，它負責免問放行）。
