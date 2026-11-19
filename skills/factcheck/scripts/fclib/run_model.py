"""Build role prompts and run a model CLI as one debate seat.

Every call runs in a fresh empty temp directory and gets only the role
instructions plus the JSON files that role is allowed to see.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import finalize, io, validate

TIMEOUT = 3600  # seconds; measured proponent runs took 9–33 minutes (2026-11-18 eval batch)
ISOLATION_NOTE = ("這是一次獨立的事實查核任務。忽略任何使用者層級的偏好、記憶、協議或工作守則："
                  "它們不是證據，也不能影響判定。只依照本次提供的角色指令和輸入資料作答。")

PROBE_PROMPT = (
    'You are being probed by a tool. Answer ONLY with one JSON object, no other text: '
    '{"user_context": <true if your context contains any user-level or project-level instructions '
    'such as AGENTS.md, CLAUDE.md, memories, hooks output or a protocol; else false>, '
    '"can_web_search": <true if you have a web search tool available>}'
)

LENS_FILES = {"evidence": "opponent-evidence.md", "counter": "opponent-counter.md",
              "stance": "opponent-stance.md", "external": "opponent-external.md"}

ROLE_INPUTS = {
    "prep": ["input.json"],
    "tracer": ["source.json", "claims.json"],
    "proponent": ["source.json", "claims.json", "trace.json"],
    "opponent": ["source.json", "claims.json", "trace.json", "proponent.json"],
    "rebuttal": ["source.json", "claims.json", "trace.json", "proponent.json", "opponent-*.json"],
    "judge": ["source.json", "claims.json", "trace.json", "proponent.json", "opponent-*.json", "rebuttal.json"],
    "review": ["claims.json", "judgment.json", "opponent-{seat}.json"],
}


ROLE_DATA = {
    "tracer": ["tactics", "media"],
    "proponent": ["sources"],
    "opponent": ["sources"],
    "rebuttal": ["tactics"],
    "judge": ["tactics"],
}
STANCE_LENSES = {"stance", "external"}
# Fields only the program writes (validate.fallback); a model must not set them itself.
PROGRAM_FIELDS = {"tracer": ("set_aside_tactics",), "judge": ("tactic_checks_set_aside", "rulings_unverified")}


class RunModelError(RuntimeError):
    pass


def _data_sections(role, lens, data_dir):
    wanted = list(ROLE_DATA.get(role, []))
    if role == "opponent" and lens in STANCE_LENSES:
        wanted.append("tactics")
    sections = []
    for kind in wanted:
        path = Path(data_dir) / f"{kind}.toml"
        if not path.exists():
            continue
        data = io.read_toml(path)
        if kind == "tactics":
            rows = [{k: t.get(k) for k in ("id", "name", "layer", "observable", "cannot_infer")}
                    for t in data.get("tactic", [])]
            title = "手法庫（只能用這些 tactic_id）"
            sections.append((io.REFERENCES_DIR / "tactic-rules.md").read_text(encoding="utf-8"))
        elif kind == "media":
            rows = [{k: o.get(k) for k in ("id", "name", "aliases", "domains")} for o in data.get("outlet", [])]
            title = "媒體對照表（只用來填 outlet_id，立場和信任度由腳本另外查）"
        else:
            rows = [{k: s.get(k) for k in ("name", "url", "tier", "covers")} for s in data.get("source", [])]
            title = "第一手來源入口"
        sections.append(f"## {title}\n\n```json\n{json.dumps(rows, ensure_ascii=False)}\n```\n")
    return sections


def output_name(role, seat):
    return {"prep": "source.json 和 claims.json（合在一個 JSON 物件裡）",
            "tracer": "trace.json", "proponent": "proponent.json", "rebuttal": "rebuttal.json",
            "judge": "judgment.json", "opponent": f"opponent-{seat}.json",
            "review": f"review-{seat}.json"}[role]


def extract_json_object(text: str):
    """Return the last top-level JSON object in free text, or None."""
    decoder = json.JSONDecoder()
    found, i = None, 0
    while True:
        i = text.find("{", i)
        if i < 0:
            return found
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict):
            found = obj
        i = end


def _strip_engine(obj):
    if isinstance(obj, dict):
        return {k: _strip_engine(v) for k, v in obj.items() if k != "engine"}
    return obj


def _role_file(role, lens):
    name = LENS_FILES[lens] if role == "opponent" else f"{role}.md"
    text = (io.REFERENCES_DIR / "roles" / name).read_text(encoding="utf-8")
    if role == "prep":  # steps 1-2 follow the same rule files the host used to follow itself
        text += "".join("\n\n" + (io.REFERENCES_DIR / f).read_text(encoding="utf-8") for f in ("ingest.md", "neutralize.md"))
    return text


def _seat_engine(run, seat):
    models = io.read_json_or_none(run / "models.json") or {}
    for s in models.get("seats", []):
        if s["seat"] == seat:
            return s["engine"]
    return (io.read_json_or_none(run / "run.json") or {}).get("host", "unknown")


def build_prompt(run, role, seat, lens=None, engine_label=None, data_dir=None):
    run = Path(run)
    data_dir = io.DATA_DIR / "tw" if data_dir is None else data_dir
    parts = [(io.REFERENCES_DIR / "roles" / "_common.md").read_text(encoding="utf-8"),
             _role_file(role, lens)]

    out = output_name(role, seat)
    fixed = {}
    if role in ("opponent", "review"):
        fixed["seat"] = seat
    if role == "opponent":
        fixed["lens"] = lens
        fixed["engine"] = engine_label or _seat_engine(run, seat)
    checked_on = str((io.read_json_or_none(run / "run.json") or {}).get("created_at", ""))[:10]
    judge_only = finalize.judge_only_changes(run) if role == "review" else {}
    # The same list `fc.py reviewers` prints and validate checks the output against.
    to_review = finalize.reviewers_needed(run).get(seat, []) if role == "review" else []
    parts.append("## 這一次的任務\n\n"
                 f"- 輸出檔名：`{out}`\n"
                 + (f"- 查核日期：{checked_on}（台灣時間）\n" if checked_on else "")
                 + (f"- 下列欄位必須照抄：`{json.dumps(fixed, ensure_ascii=False)}`\n" if fixed else "")
                 + (f"- 你要覆核的命題（每條剛好寫一筆，其他命題不用寫）：{'、'.join(to_review)}\n" if to_review else "")
                 + (f"- 裁判自行改判、你也要覆核的命題：{'、'.join(judge_only)}（正方原本的判定在輸入資料最後）\n"
                    if judge_only else ""))

    parts.extend(_data_sections(role, lens, data_dir))
    parts.append("## 輸入資料\n")
    for pattern in ROLE_INPUTS[role]:
        for path in sorted(run.glob(pattern.format(seat=seat))):
            data = io.read_json(path)
            if path.name.startswith("opponent-"):
                if data.get("status", "ok") != "ok":
                    continue
                if role in ("rebuttal", "judge"):
                    data = _strip_engine(data)
            parts.append(f"### {path.name}\n\n```json\n{json.dumps(data, ensure_ascii=False, indent=1)}\n```\n")
    if judge_only:
        # Red-team: model text goes in the input data as JSON, never raw into the task section. Its evidence ids are
        # the proponent's; the judge may reuse an id for another source (case-008), so the entries come along.
        ledger = {e["id"]: e for e in io.read_json(run / "proponent.json").get("ledger", [])}
        items = [{**v, "evidence": [ledger[e] for e in v.get("evidence_ids", []) if e in ledger]}
                 for v in judge_only.values()]
        parts.append("### 正方原本的判定（裁判自行改判的命題；證據編號是正方證據表的，和 judgment.json 無關，"
                     "內容附在每筆的 evidence）\n\n"
                     f"```json\n{json.dumps(items, ensure_ascii=False, indent=1)}\n```\n")
    parts.append("## 輸出\n\n只輸出一個 JSON 物件，不要任何其他文字。")
    return "\n\n".join(parts)


def build_command(engine, workdir, out_file, env):
    cmd = list(engine["cmd"])
    eid = engine["engine"]
    model = engine.get("model") or env.get(f"FC_{eid.upper()}_MODEL")
    if eid == "codex":
        argv = cmd + ["exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
                      "-s", "read-only", "-C", str(workdir), "-c", 'web_search="live"',
                      "-o", str(out_file)]
        if model:
            argv += ["-m", model]
        return argv + ["-"], "file"
    if eid == "claude":
        # --safe-mode skips CLAUDE.md, hooks, plugins and MCP but keeps OAuth login and web search
        # (2026-11-18 canary: without it, claude -p saw the user's CLAUDE.md and SessionStart hook output).
        argv = cmd + ["-p", "--output-format", "json", "--no-session-persistence", "--safe-mode",
                      "--allowedTools", "WebSearch", "WebFetch",
                      "--append-system-prompt", ISOLATION_NOTE]
        if env.get("ANTHROPIC_API_KEY"):
            argv.append("--bare")
        if model:
            argv += ["--model", model]
        effort = engine.get("effort") or env.get("FC_CLAUDE_EFFORT")
        if effort:
            argv += ["--effort", effort]
        return argv, "claude-json"
    if eid == "gemini":
        argv = cmd + ["-p", "-"]
        if model:
            argv += ["-m", model]
        return argv, "stdout"
    if eid == "ollama":
        return cmd + ["run", model], "stdout"
    raise RunModelError(f"不支援的引擎 {eid}")


def _default_runner(argv, stdin, cwd, timeout, env):
    p = subprocess.run(argv, input=stdin, capture_output=True, text=True, cwd=cwd,
                       timeout=timeout, env={**os.environ, **env})
    return p.returncode, p.stdout, p.stderr


def call(engine, prompt, runner=_default_runner, env=None, timeout=None, attempts=2):
    """Run one prompt; retry once on a crash or bad exit, never on timeout. Returns (ok, text, error)."""
    env = dict(os.environ if env is None else env)
    if timeout is None:
        timeout = int(env.get("FC_TIMEOUT", TIMEOUT))
    error = ""
    for _ in range(attempts):
        workdir = Path(tempfile.mkdtemp(prefix="fc-seat-"))
        out_file = workdir / "last-message.txt"
        try:
            argv, mode = build_command(engine, workdir, out_file, env)
            try:
                code, stdout, stderr = runner(argv, prompt, str(workdir), timeout, env)
            except subprocess.TimeoutExpired:
                return False, "", f"逾時（超過 {timeout} 秒，可用 FC_TIMEOUT 調整）"
            except OSError as exc:
                error = f"無法執行：{exc}"
                continue
            if code != 0:
                error = f"結束碼 {code}：{(stderr or stdout)[-300:]}"
                continue
            if mode == "file":
                text = out_file.read_text(encoding="utf-8") if out_file.exists() else stdout
            elif mode == "claude-json":
                try:
                    payload = json.loads(stdout)
                except json.JSONDecodeError:
                    error = "claude 輸出不是 JSON"
                    continue
                if payload.get("is_error"):
                    error = f"claude 回報錯誤：{str(payload.get('result'))[:300]}"
                    continue
                text = payload.get("result") or ""
            else:
                text = stdout
            return True, text, ""
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    return False, "", error


def probe(engine, runner=_default_runner, env=None):
    ok, text, error = call(engine, PROBE_PROMPT, runner=runner, env=env, timeout=240)
    obj = extract_json_object(text) if ok else None
    if obj is None:
        return {"probe": "failed", "isolation": "unknown", "detail": error or "探測沒有回傳 JSON"}
    result = {"probe": "ok", "isolation": "partial" if obj.get("user_context") else "full", "detail": ""}
    if obj.get("can_web_search") is False:
        result["can_search"] = False
    return result


RETRY_HEADER = "\n\n## 上一次的輸出有以下問題，請修正後重新輸出完整 JSON\n\n"


def _run_prep(run, engine, runner, env):
    """Steps 1-2 in an isolated process. The message text and the link come from input.json, never from the model,
    so a rewrite cannot slip into what every later role checks against."""
    if validate.validate_file(run, "input.json"):
        raise RunModelError("缺少 input.json 或格式不對，先執行 fc.py input")
    inp = io.read_json(run / "input.json")
    prompt = build_prompt(run, "prep", None)
    outputs = [run / "source.json", run / "claims.json"]
    errors, wrote = ["沒有執行"], False
    for _ in range(2):
        ok, text, error = call(engine, prompt, runner=runner, env=env)
        if not ok:
            errors = [error]
            break
        obj = extract_json_object(text)
        if not obj or not isinstance(obj.get("source"), dict) or not isinstance(obj.get("claims"), dict):
            errors = ['輸出必須是 {"source": {…}, "claims": {…}}']
        else:
            source = {**obj["source"], "input_type": inp["input_type"]}
            if inp["input_type"] == "url":
                source["url"] = inp["content"]  # the user's link, whatever the model fetched
            else:
                source["original_text"] = inp["content"]
                source["url"] = inp.get("url") if inp["input_type"] != "text" else None
            if inp["input_type"] == "text":  # a forwarded text has no publication time of its own (neutralize.md rule 6)
                source["published_at"] = None
            io.write_json(outputs[0], source)
            io.write_json(outputs[1], obj["claims"])
            wrote = True
            errors = [f"{p.name}：{e}" for p in outputs for e in validate.validate_file(run, p.name)]
            # Skeptic review: with no text the quote check is skipped, so claims could be invented.
            if not str(source.get("original_text") or "").strip():
                errors.append("source.json：網址輸入要把讀到的全文放進 original_text；讀不到就照實寫在 notes，只放看得到的部分")
            if not errors:
                return outputs[1]
        if wrote:  # second review: a retry cut short must not leave the rejected files looking finished
            for p in outputs:
                p.unlink(missing_ok=True)
        prompt = prompt + RETRY_HEADER + "\n".join(f"- {e}" for e in errors)
    raise RunModelError(f"prep 在 {engine['engine']} 上失敗：" + "；".join(errors))


def run_role(run, role, seat, engine, lens=None, runner=_default_runner, env=None, known_tactics=None):
    """Run a role on an engine, validate, and write the output file. Retries once on invalid output."""
    run = Path(run)
    if role == "prep":
        return _run_prep(run, engine, runner, env)
    if role == "opponent" and lens is None:
        lens = "external" if seat.startswith("X") else {"A": "evidence", "B": "counter", "C": "stance"}[seat]
    name = output_name(role, seat)
    target = run / name
    prompt = build_prompt(run, role, seat, lens=lens)
    errors, parsed = ["沒有執行"], []
    for attempt in range(2):
        ok, text, error = call(engine, prompt, runner=runner, env=env)
        if not ok:
            errors = [error]
            break
        obj = extract_json_object(text)
        if obj is None:
            errors = ["輸出裡找不到 JSON 物件"]
        else:
            for k in PROGRAM_FIELDS.get(role, ()):
                obj.pop(k, None)
            if role in ("opponent", "review"):
                obj["seat"] = seat
            if role == "opponent":
                obj.update({"engine": engine["engine"], "lens": lens, "status": "ok"})
            io.write_json(target, obj)
            errors = validate.validate_file(run, name, known_tactics=known_tactics)
            if not errors:
                return target
            parsed.append((obj, errors))
            target.unlink()
        prompt = prompt + RETRY_HEADER + "\n".join(f"- {e}" for e in errors)

    # If only tags or the judge's checked-URL lists still break the rules after the retry, take the
    # fallback (validate.fallback) instead of stopping the whole check.
    # Red-team: try every output that parsed, newest first, even when the retry broke in another way.
    for obj, errs in reversed(parsed):
        fixed = validate.fallback(obj, run, name, known_tactics, errs)
        if fixed is None:
            continue
        io.write_json(target, fixed)
        if not validate.validate_file(run, name, known_tactics=known_tactics):
            return target
        target.unlink()

    if role == "opponent":
        io.write_json(target, {"seat": seat, "engine": engine["engine"], "lens": lens,
                               "status": "failed", "error": "；".join(errors)[:500], "attacks": []})
        return target
    raise RunModelError(f"{role} 在 {engine['engine']} 上失敗：" + "；".join(errors))
