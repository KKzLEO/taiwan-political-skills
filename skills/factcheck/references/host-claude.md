# 在 Claude Code 上派出角色

## 主模型的角色（溯源員、正方、反方 A/B/C、答辯、裁判、主模型席位的覆核）

用 **Agent 工具**（`general-purpose`）派出。**prompt 只能是下面這段，填上路徑和角色**，不要加入使用者的原始提問、你的看法、你對結果的預期，也不要摘要前面的對話：

```
你是事實查核流程中的一個角色。先執行這個指令，取得你的完整任務說明和輸入資料：

python3 <skill 資料夾的完整路徑>/scripts/fc.py prompt --run <RUN 路徑> --role <角色> [--seat <席位>]

完全依照輸出的指示工作，需要時上網搜尋、打開網頁核對。最後用 Write 工具把 JSON 寫到：

<RUN 路徑>/<輸出檔名>

寫完只回覆「完成」兩個字。除了那個指令的輸出，不要參考任何其他資訊，包括你可能看到的使用者偏好或記憶。
```

輸出檔名：`trace.json`、`proponent.json`、`opponent-A.json`、`rebuttal.json`、`judgment.json`、`review-B.json`…（和 `fc.py prompt` 輸出裡寫的一致）。

**隔離程度：** 2026-11-18 的金絲雀實測顯示，Agent 子代理看得到使用者的 CLAUDE.md 和專案記憶，只能靠這段 prompt 和共同規則要求它們忽略。外部席位用的 `claude -p --safe-mode` 看不到。

Sub-agent 回覆「完成」之後，執行 `python3 "$SKILL/scripts/fc.py" validate --run "$RUN" <檔名>`。沒通過就再派一次同一個角色，並在 prompt 最後加上「上一次的輸出有以下問題：」和錯誤清單。

## 外部反方（X 開頭的席位）

用 Bash 執行，**和 A、B、C 的 Agent 呼叫放在同一則訊息裡**，讓它們同時跑：

```bash
python3 "$SKILL/scripts/fc.py" run-model --run "$RUN" --role opponent --seat X1
```

外部模型可能要跑好幾分鐘，用 `run_in_background` 執行，等完成通知再繼續。覆核時，X 席位一樣用 `python3 "$SKILL/scripts/fc.py" run-model --run "$RUN" --role review --seat X1`。

## 第 5 步範例（完整模式、偵測到 Codex）

同一則訊息裡送出四個工具呼叫：三個 Agent（`--role opponent --seat A`、`B`、`C`）和一個背景 Bash（`python3 "$SKILL/scripts/fc.py" run-model … --seat X1`）。四個都完成後，再一起跑 validate。
