# 在 Claude Code 上派出角色

流程和指令見 SKILL.md 的第 2–8 步。第 2 步的讀入與拆題和主模型的席位都跑 `claude -p --safe-mode`。2026-11-18 的金絲雀實測顯示，它看不到使用者的 CLAUDE.md 和專案記憶；Agent 子代理看得到，所以**不要用 Agent 工具派角色**。

**第 0 步偵測時，記下你自己的模型：**

```bash
python3 "$SKILL/scripts/fc.py" detect --run "$RUN" --probe --host-model <你自己的模型 ID> --host-effort xhigh
```

- 主模型的每個角色都照 `models.json` 記的模型和推理強度跑，和第二輪評測一樣。detect 會印出這一行；沒帶參數時，會寫「沒有指定模型」。
- `xhigh` 比較花額度和時間。使用者要求省額度時，可以改用 `high`。
- 重跑 detect 也要帶這兩個參數，不然會被清掉。

**每個 `run-model` 都用 `run_in_background` 執行：**
- 等完成通知再進下一步，不要輪詢。每個角色要跑幾分鐘到半小時以上，超過 Bash 工具 10 分鐘的上限。
- 背景指令還沒結束時，不要重跑同一步。`fc.py status` 會把還在跑的步驟顯示成「缺少」。

**detect 印出「找不到主體的 CLI」時：** 通常是只裝了桌面版或 IDE 外掛，終端機裡沒有 `claude` 指令。停下來告訴使用者，請他選一個做法，再重跑第 0 步：
- 安裝 Claude Code 的命令列版本，或把 `claude` 所在的資料夾加進 PATH。
- 用 `FC_CLAUDE_CMD` 指定完整路徑。這個路徑會寫進 `models.json`，分享查核資料夾時會帶出帳號名稱。

**detect 印出「偵測到 ANTHROPIC_API_KEY」時：**
- 每個角色都會另外加 `--bare`，費用算在那把 key 上。這條路沒有做過金絲雀實測。
- 開始前先告訴使用者，不要自己印出 key 的內容。
