# 台灣訊息查核 skill

收到一則訊息，想知道是真是假？這個 skill 會把它拆成一句一句可以查證的說法，請一個 AI 當正方查證，再派三個 AI 當反方專門挑毛病，最後找另一家公司的模型來交叉抗辯。分數由程式依固定規則算出來，同一份結果每次都得到同樣的分數。

可以在 **Claude Code** 和 **Codex** 裡使用。

## 它會做什麼

- **查核四種輸入：** 新聞網址、LINE 轉傳文字、截圖、影片連結（YouTube 等，需要 `yt-dlp`）
- **一個正方對三個反方：**
  - 反方 A 檢查證據
  - 反方 B 自己去找反證
  - 反方 C 檢查有沒有偏向任何一方
- **跨模型抗辯：** 自動偵測電腦上的 Codex、Claude Code、Gemini CLI，請不同公司的模型當外部反方
- **溯源：** 最早在哪裡出現、有哪些版本、是不是舊聞新炒
- **背景查核：** 媒體信任度（Reuters 調查）、學術研究對媒體立場的分類（有研究才列）、記者署名、用詞是否中立
- **查核機構也要被查核：** 事實查核中心、Cofacts、MyGoPen 的結論只當線索，會回到原始資料重新驗證
- **操弄手法辨識：** 例如斷章取義、舊圖新用、假語錄、急迫轉傳，並告訴你下次怎麼自己認出來
- **法條：** 一定引用條文原文，標明「非法律意見」

## 報告長這樣

下面是一則 LINE 轉傳「立法院昨天三讀通過，以後騎機車一律要開大燈，沒開罰三千！」的實際結果，完整紀錄在 [examples/](examples/)：

```text
錯誤 ▲━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 正確
     0
```

**結果：不符｜可信度 0｜信心度 高（100）｜完整模式・跨模型 1 席｜可公開**

報告的內容依序是：
- 逐項判定
- 溯源
- 報導品質
- 操弄手法
- 和既有查核的比對
- 爭議點
- 已檢驗的質疑
- 評分拆解
- 每一筆來源

## 三個數字

| | 意思 | 會受什麼影響 |
|---|---|---|
| **可信度** 0–100 | 這則訊息本身有多正確 | 只看每個命題的判定，依重要性加權 |
| **查核結果** | 符合／大致符合／部分符合／不符／無法判定 | 由可信度換算。查不到的東西太多時一律「無法判定」，因為查不到不等於假的 |
| **信心度** 0–100 | 這次查得多扎實 | 缺少第一手證據、沒有跨模型反方、覆核沒通過、來源被擋、拿不到法條原文、快速模式，都會扣分 |

媒體立場、記者署名、用詞、操弄手法**都不會影響可信度**。看是哪家媒體就先打折，正是我們要避免的偏見。

完整規則在 [skills/factcheck/references/scoring.md](skills/factcheck/references/scoring.md)。

## 安裝

需要 Python 3.11 以上，不用另外裝任何套件。影片查核需要 [yt-dlp](https://github.com/yt-dlp/yt-dlp)。

**Claude Code：**

```
/plugin marketplace add <GitHub 帳號>/taiwan-political-skills
/plugin install taiwan-factcheck@taiwan-political-skills
```

**Codex：**

```bash
git clone https://github.com/<GitHub 帳號>/taiwan-political-skills.git
ln -s "$PWD/taiwan-political-skills/skills/factcheck" ~/.codex/skills/factcheck
```

**建議另外裝一個不同公司的模型 CLI**（Claude Code 使用者裝 Codex，Codex 使用者裝 Claude Code），否則信心度固定扣 20 分，報告也不能標「可公開」。

**選裝：** 法規 MCP [lawchat-oss/mcp-taiwan-legal-db](https://github.com/lawchat-oss/mcp-taiwan-legal-db)，查法條會更準。

## 使用

直接說「幫我查核這則訊息」，然後貼上內容或網址就可以了。想快一點就說「快速查核」，但快速模式的報告不能標「可公開」。

每次查核都會在目前的資料夾底下產生 `factcheck-runs/<日期>-<主題>/`，裡面有完整的中間紀錄，任何人都可以檢查一份報告是怎麼得出來的。

## 已知限制

- **外部模型會讀到你自己的設定：**
  - `codex exec` 會讀到 `~/.codex/AGENTS.md`。
  - 沒有 API key 的 `claude -p` 會讀到 `~/.claude/CLAUDE.md`。
  - 每次偵測時都會實測，報告的席位表會標「部分隔離」。
  - 想要完整隔離有兩種做法：設定 `ANTHROPIC_API_KEY`，`claude -p` 會改用 `--bare`；或另外準備一個乾淨的 Codex 設定，用 `FC_CODEX_CMD="env CODEX_HOME=$HOME/.codex-factcheck codex"` 指定。
- **不判斷圖片或影片是不是偽造的，** 只查內容說了什麼。
- **社群平台常常抓不到原始貼文，** 這時會請你貼上連結或截圖。
- **分數門檻是第一版的數字，** 會用 `evals/` 的標準案例持續校正。
- **Gemini CLI 的串接還沒有實測過。**

## 開發

```bash
python3 -m unittest discover -s tests -t .
```

- 設計規格：[docs/superpowers/specs/2026-11-17-taiwan-factcheck-design.md](docs/superpowers/specs/2026-11-17-taiwan-factcheck-design.md)
- 發版前的評測：[evals/README.md](evals/README.md)

**資料可以提 PR 修正，但要附出處：**
- `skills/factcheck/data/tw/media.toml` 每一筆都要有網址和年份。
- `tactics.toml` 每種手法的案例，至少要涵蓋兩個不同的被攻擊方。

這兩條規則都由測試強制檢查。

## 授權

- 程式碼：MIT
- `skills/factcheck/data/`：CC BY-SA 4.0

詳見 [LICENSE](LICENSE)。報告引用查核機構與 Cofacts 的內容時，只附連結和簡短摘錄，著作權屬原機構。

---

**English summary:** An open-source fact-checking skill for Claude Code and Codex, focused on Taiwan. One proponent agent is attacked by three opponent agents (evidence, counter-evidence, neutrality lenses), plus each available cross-vendor model as an external opponent. A clean-context judge rules on each attack, and deterministic scripts compute a reproducible credibility score, a verdict, and a separate confidence score. Code is MIT; data is CC BY-SA 4.0.
