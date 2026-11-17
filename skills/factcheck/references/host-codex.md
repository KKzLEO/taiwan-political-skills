# 在 Codex 上派出角色

Codex 當主體時，所有角色都用 `fc.py run-model` 開一個獨立的 `codex exec` 子程序執行。子程序在空的暫存資料夾裡跑，只拿到該角色的指令和輸入資料，看不到這段對話。

```bash
python3 "$SKILL/scripts/fc.py" run-model --run "$RUN" --role tracer
python3 "$SKILL/scripts/fc.py" run-model --run "$RUN" --role proponent
```

## 第 5 步：所有反方同時跑

```bash
for s in $(python3 -c "import json,sys;print(' '.join(x['seat'] for x in json.load(open(sys.argv[1]))['seats']))" "$RUN/models.json"); do
  python3 "$SKILL/scripts/fc.py" run-model --run "$RUN" --role opponent --seat "$s" &
done
wait
```

- A、B、C 席位跑在 Codex 上，X 席位會自動用 `models.json` 裡對應的外部 CLI（例如 `claude -p`）。
- `run-model` 會自己檢查輸出格式、重試一次，所以不需要另外 validate。主模型的角色（溯源員、正方、答辯、裁判）重試後還是失敗，指令會以非零結束碼停止，這時告訴使用者是哪一步出錯。

## 接下來

```bash
python3 "$SKILL/scripts/fc.py" run-model --run "$RUN" --role rebuttal
python3 "$SKILL/scripts/fc.py" run-model --run "$RUN" --role judge
python3 "$SKILL/scripts/fc.py" reviewers --run "$RUN"            # 列出要覆核的席位
python3 "$SKILL/scripts/fc.py" run-model --run "$RUN" --role review --seat B   # 每個列出的席位跑一次
```

每個子程序可能要跑好幾分鐘，`claude -p` 當外部反方時可能超過 10 分鐘。`run-model` 的逾時上限預設 3600 秒，可以用環境變數 `FC_TIMEOUT` 調整；你自己執行指令時，工具的 timeout 也要設得比它長。
