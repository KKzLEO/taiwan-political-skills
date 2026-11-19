#!/usr/bin/env python3
"""Single entry point for the fact-check skill's deterministic steps.

Run `python3 fc.py <command> -h` for details. Requires Python 3.11+, standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fclib import detect, evalcmp, finalize, io, media, render, run_model, score, validate, video  # noqa: E402
from fclib.labels import HOSTS, MODES  # noqa: E402

VERSION = "0.1.0"
TZ = dt.timezone(dt.timedelta(hours=8))
STAGES = ["run.json", "models.json", "input.json", "source.json", "claims.json", "trace.json", "proponent.json",
          "opponent-*.json", "rebuttal.json", "judgment.json", "review-*.json", "verdicts.json",
          "score.json", "report.md"]


def _run_dir(args) -> Path:
    run = Path(args.run).resolve()
    if not (run / "run.json").exists():
        sys.exit(f"錯誤：{run} 不是查核資料夾（找不到 run.json）")
    return run


def cmd_init(args):
    now = dt.datetime.now(TZ)
    slug = re.sub(r"[^\w\-]+", "-", args.slug).strip("-")[:40] or "check"
    base = Path(args.base or os.getcwd()) / "factcheck-runs"
    run = base / f"{now:%Y%m%d-%H%M}-{slug}"
    n = 2
    while run.exists():
        run = base / f"{now:%Y%m%d-%H%M}-{slug}-{n}"
        n += 1
    run.mkdir(parents=True)
    io.write_json(run / "run.json", {"mode": args.mode, "host": args.host, "created_at": now.isoformat(timespec="seconds"),
                                     "skill_version": VERSION, "slug": slug})
    print(run)


def cmd_detect(args):
    run = _run_dir(args)
    rj = io.read_json(run / "run.json")
    tiers = io.read_toml(io.DATA_DIR / "model-tiers.toml")
    probe = (lambda e: run_model.probe(e)) if args.probe else None
    models = detect.detect(rj["host"], tiers, env=dict(os.environ), probe=probe)
    for e in models["engines"]:  # recorded in the run folder, so every host-model role uses the same model
        if e["engine"] == models["host"]:
            e.update({k: v for k, v in (("model", args.host_model), ("effort", args.host_effort)) if v})
    models["seats"] = detect.assign_seats(models, rj["mode"])
    host = next((e for e in models["engines"] if e["engine"] == models["host"]), None)
    if host is not None:
        if not host["available"]:
            print(f"# 警告：找不到主體的 CLI（{host['engine']}），主模型的角色沒辦法跑", file=sys.stderr)
        print(f"# 主模型的角色：{host['engine']}，"
              + (f"模型 {host['model']}" if host.get("model") else "沒有指定模型（用 CLI 的預設）")
              + (f"，推理強度 {host['effort']}" if host.get("effort") else ""), file=sys.stderr)
    if os.environ.get("ANTHROPIC_API_KEY") and any(e["engine"] == "claude" and e["available"] for e in models["engines"]):
        print("# 偵測到 ANTHROPIC_API_KEY（不印內容）：claude 的角色會加 --bare，費用算在這把 key 上", file=sys.stderr)
    io.write_json(run / "models.json", models)
    for s in models["seats"]:
        print(f"{s['seat']}\t{s['kind']}\t{s['engine']}{'/' + s['model'] if s.get('model') else ''}\t{s['lens']}")
    for e in models["engines"]:
        if e["available"] and e["cross_model"]:
            reason = f"（原因：{e['detail']}）" if e["probe"] == "failed" and e.get("detail") else ""
            print(f"# {e['engine']}: probe={e['probe']} isolation={e['isolation']} same_tier={e['same_tier']}{reason}",
                  file=sys.stderr)


def cmd_prompt(args):
    run = _run_dir(args)
    lens = args.lens
    if args.role == "opponent" and lens is None:
        lens = "external" if args.seat.startswith("X") else {"A": "evidence", "B": "counter", "C": "stance"}[args.seat]
    print(run_model.build_prompt(run, args.role, args.seat, lens=lens))


def _engine_for(run: Path, role: str, seat, name):
    models = io.read_json(run / "models.json")
    if name is None:
        seat_info = next((s for s in models.get("seats", []) if s["seat"] == seat), None) if seat else None
        name = seat_info["engine"] if seat_info else models["host"]
        model = seat_info.get("model") if seat_info else None
    else:
        model = None
    for e in models["engines"]:
        if e["engine"] == name and (model is None or e.get("model") == model) and e["available"]:
            return e
    sys.exit(f"錯誤：找不到可用的引擎 {name}（先跑 detect，或確認 CLI 有裝）")


def cmd_run_model(args):
    run = _run_dir(args)
    engine = _engine_for(run, args.role, args.seat, args.engine)
    try:
        path = run_model.run_role(run, args.role, args.seat, engine, lens=args.lens,
                                  known_tactics=io.tactic_library())
    except run_model.RunModelError as exc:
        sys.exit(f"錯誤：{exc}")
    print(path)


def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        sys.exit("錯誤：檔案不是 UTF-8 編碼，先轉成 UTF-8 再執行")
    except OSError as exc:
        sys.exit(f"錯誤：讀不到檔案：{exc}")


def cmd_input(args):
    """Step 1: store what the user gave, verbatim, for the isolated prep role (step 2). User text arrives only
    through files: as shell arguments, $ and backticks were eaten, $(...) ran, and a URL could close quotes."""
    run = _run_dir(args)
    if (run / "source.json").exists():  # a new message would mix with the old debate files
        sys.exit("錯誤：這個資料夾已經讀入過訊息；要查另一則，先用 fc.py init 開新的資料夾")
    url = _read_text(args.url_file).strip() if args.url_file else None
    content = url if args.type == "url" else (_read_text(args.file) if args.file else "")
    data = {"input_type": args.type, "content": content or "", "prompt": _read_text(args.prompt_file).strip(), "url": url}
    errors = validate.input_errors(data)
    if errors:  # checked before writing, so a failed rerun keeps the previous input.json
        sys.exit("錯誤：輸入沒有通過檢查：\n" + "\n".join(errors))
    io.write_json(run / "input.json", data)
    print(run / "input.json")


def cmd_validate(args):
    run = _run_dir(args)
    known = io.tactic_library()
    bad = False
    for name in args.files:
        errors = validate.validate_file(run, name, known_tactics=known)
        if errors:
            bad = True
            print(f"✗ {name}")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"✓ {name}")
    sys.exit(1 if bad else 0)


def cmd_media(args):
    hit = media.lookup(args.query, media.load(args.region))
    if hit is None:
        print("對照表裡沒有這個媒體。報告會寫「對照表沒有收錄」，不要自己推斷立場。")
        sys.exit(1)
    print(json.dumps(hit, ensure_ascii=False, indent=2))


def cmd_video(args):
    url = _read_text(args.url_file).strip() if args.url_file else args.url
    if not url:
        sys.exit("錯誤：需要影片網址（--url-file）")
    text, note = video.fetch_transcript(url)
    print(note, file=sys.stderr)
    if text is None:
        sys.exit(1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)


def cmd_finalize(args):
    run = _run_dir(args)
    for name in ("proponent.json", "judgment.json"):  # finalize compares the two (judge-only changes)
        errors = validate.validate_file(run, name, known_tactics=io.tactic_library())
        if errors:
            sys.exit(f"錯誤：{name} 沒有通過檢查：\n" + "\n".join(errors))
    io.write_json(run / "verdicts.json", finalize.finalize(run))
    # A review that never arrived overturns the judge's label; this is the one place the host is told which seat.
    missing = {s: ids for s, ids in finalize.reviewers_needed(run).items() if not (run / f"review-{s}.json").exists()}
    if missing:
        claims = sorted({c for ids in missing.values() for c in ids}, key=lambda c: (len(c), c))
        print(f"注意：席位 {'、'.join(missing)} 沒有覆核檔，{'、'.join(claims)} 記成「覆核未完成」，改列「無法證實」。"
              "回報時要告訴使用者是哪一席沒有覆核。", file=sys.stderr)
    print(run / "verdicts.json")


def cmd_reviewers(args):
    run = _run_dir(args)
    needed = finalize.reviewers_needed(run)
    if not needed:
        print("不需要派覆核")
    for seat, ids in needed.items():
        print(f"{seat}\t{','.join(ids)}")


def cmd_score(args):
    run = _run_dir(args)
    try:
        result = score.compute(io.read_json(run / "verdicts.json"), io.read_json(run / "run.json"),
                               detect.seat_status(run))
    except (score.ScoreError, io.ReadError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        sys.exit(2)
    io.write_json(run / "score.json", result)
    cred = result["credibility"] or {}  # the host reads this line: no number where the report shows none (無法判定)
    print(json.dumps({"result": result["result"], "credibility": cred.get("score") if cred.get("show_on_spectrum") else None,
                      "confidence": result["confidence"]["score"], "publishable": result["publishable"]},
                     ensure_ascii=False))


def cmd_render(args):
    run = _run_dir(args)
    (run / "report.md").write_text(render.render(run), encoding="utf-8")
    print(run / "report.md")


def cmd_status(args):
    run = _run_dir(args)
    known = io.tactic_library()
    for pattern in STAGES:
        paths = sorted(run.glob(pattern))
        if not paths:
            print(f"{pattern:<18} 缺少")
            continue
        for p in paths:
            if p.suffix == ".json" and p.name != "score.json":
                errs = validate.validate_file(run, p.name, known_tactics=known)
                print(f"{p.name:<18} {'完成' if not errs else '格式錯誤（' + str(len(errs)) + '）'}")
            else:
                print(f"{p.name:<18} 完成")


def cmd_eval_compare(args):
    run = _run_dir(args)
    case = io.read_toml(Path(args.case))
    r = evalcmp.compare(case, io.read_json(run / "claims.json"), io.read_json(run / "verdicts.json"),
                        io.read_json(run / "score.json"))
    print(json.dumps(r, ensure_ascii=False, indent=2))


def cmd_set_aside_tactics(args):
    """After a role has redone its output once and only the tags (trace.json) or tag checks
    (judgment.json) are still wrong: move those out, keep them in the file, and carry on."""
    run = _run_dir(args)
    known = io.tactic_library()
    for name in args.files:
        errors = validate.validate_file(run, name, known_tactics=known)
        if not errors:
            print(f"✓ {name}：沒有問題，不需要移出")
            continue
        fixed = validate.set_aside_tactics(io.read_json(run / name), run, name, known, errors)
        if fixed is None:
            print(f"✗ {name}：錯誤不只在手法標記，不能移出，請照錯誤訊息重做")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        io.write_json(run / name, fixed)
        left = validate.validate_file(run, name, known_tactics=known)
        if left:
            print(f"✗ {name}：移出之後仍有錯誤")
            for e in left:
                print(f"  - {e}")
            sys.exit(1)
        print(f"✓ {name}：已移出不合格的手法標記（原內容保留在檔案裡），報告不會列出它們")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fc.py", description="台灣訊息查核 skill 的固定步驟")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, run=True):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
        if run:
            p.add_argument("--run", required=True, help="查核資料夾")
        return p

    p = add("init", cmd_init, run=False)
    p.add_argument("--mode", required=True, choices=sorted(MODES))
    p.add_argument("--host", required=True, choices=sorted(HOSTS))
    p.add_argument("--slug", required=True)
    p.add_argument("--base", help="放 factcheck-runs/ 的目錄，預設是目前目錄")

    p = add("detect", cmd_detect)
    p.add_argument("--probe", action="store_true", help="實際呼叫外部 CLI，確認登入、能否上網、隔離程度")
    p.add_argument("--host-model", help="主模型角色用的模型 ID，記在 models.json（例如 claude-opus-5-5）")
    p.add_argument("--host-effort", choices=["low", "medium", "high", "xhigh", "max"],
                   help="主模型角色的推理強度，記在 models.json（目前只有 claude 會用到）")

    for name, fn in (("prompt", cmd_prompt), ("run-model", cmd_run_model)):
        p = add(name, fn)
        p.add_argument("--role", required=True, choices=sorted(run_model.ROLE_INPUTS))
        p.add_argument("--seat")
        p.add_argument("--lens", choices=sorted(run_model.LENS_FILES))
        if name == "run-model":
            p.add_argument("--engine", help="預設用 models.json 裡該席位的引擎；其他角色用主體平台")

    p = add("input", cmd_input)
    p.add_argument("--type", required=True, choices=["text", "url", "image", "video"])
    p.add_argument("--file", help="文字、截圖抄寫或影片逐字稿的檔案（UTF-8），原文照存")
    p.add_argument("--url-file", help="存著網址的檔案：網址輸入必填，影片可以附上影片網址")
    p.add_argument("--prompt-file", required=True, help="存著使用者這次怎麼問的檔案（UTF-8），原文照抄")

    p = add("validate", cmd_validate)
    p.add_argument("files", nargs="+")

    p = add("set-aside-tactics", cmd_set_aside_tactics)
    p.add_argument("files", nargs="+", choices=["trace.json", "judgment.json"])

    p = add("media", cmd_media, run=False)
    p.add_argument("query", help="網址、媒體名稱或代號")
    p.add_argument("--region", default="tw")

    p = add("video", cmd_video, run=False)
    p.add_argument("url", nargs="?", help="影片網址（在 shell 裡請用 --url-file）")
    p.add_argument("--url-file", help="存著影片網址的檔案")
    p.add_argument("--out")

    add("reviewers", cmd_reviewers)
    add("finalize", cmd_finalize)
    add("score", cmd_score)
    add("render", cmd_render)
    add("status", cmd_status)

    p = add("eval-compare", cmd_eval_compare)
    p.add_argument("--case", required=True)

    args = ap.parse_args(argv)
    if args.cmd in ("prompt", "run-model") and args.role in ("opponent", "review") and not args.seat:
        ap.error("opponent 和 review 需要 --seat")
    try:
        args.fn(args)
    except io.ReadError as exc:  # a missing or broken file is one line that names it, not a traceback
        sys.exit(f"錯誤：{exc}")


if __name__ == "__main__":
    main()
