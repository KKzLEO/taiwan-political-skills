#!/usr/bin/env python3
"""Run eval cases and probes through the skill's own steps: the same fc.py commands SKILL.md gives the host.

    python3 evals/harness/run_cases.py --base <output folder> --host-model <model id> [--workers 2] JOB...

JOB is a case id (case-027) or a probe variant written as probes/<file stem>/<target>:
probes/symmetry-time/國民黨 (a party), probes/leading/pan-blue (a way of asking), probes/injection/injected.

For each job, in a fresh run folder under <base>/factcheck-runs/:
  init -> models.json (one real `detect --probe` per batch, copied in) -> input -> prep -> tracer -> proponent
  -> every seat's opponent at once -> rebuttal -> judge -> reviews at once -> finalize -> score -> render

It never reads a case's expected answers. Output: <base>/results.json (one entry per job), <base>/batch.json
(code, model, effort), <base>/logs/<job>.log, and usage in <base>/usage.jsonl and usage-codex.jsonl (the claude and
codex CLIs are wrapped by harness/bin/*-usage, which only log token counts).

To run a fixed commit, export it and say which commit it is, then point --repo at the folder:
    mkdir snap && git archive <commit> | tar -x -C snap && git rev-parse <commit> > snap/COMMIT

Not covered: a host model following SKILL.md by itself, and the host's summary to the user (step 10).
Each job starts several model CLIs at once (one per opponent seat); keep --workers low on a laptop.
"""
import argparse
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=str(HERE.parents[1]), help="repo or snapshot whose skill and cases to run")
    ap.add_argument("--base", required=True, help="output folder")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--host", default="claude", choices=["claude", "codex"])
    ap.add_argument("--host-model", help="model id for the host's roles, recorded by detect")
    ap.add_argument("--host-effort", default="xhigh")
    ap.add_argument("--prep-only", action="store_true", help="stop after the ingest-and-split step (to look at claims.json)")
    ap.add_argument("jobs", nargs="+")
    args = ap.parse_args()

    repo, base = Path(args.repo).resolve(), Path(args.base).resolve()
    fc_cmd = [sys.executable, str(repo / "skills/factcheck/scripts/fc.py")]
    logs = base / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "FC_USAGE_LOG": str(base / "usage.jsonl"),
           "FC_CLAUDE_CMD": str(HERE / "bin/claude-usage"), "FC_CODEX_CMD": str(HERE / "bin/codex-usage")}

    def log(name, msg):
        with open(logs / f"{name}.log", "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

    def fc(name, *a):
        # One step may call its model twice (a retry after a rejected answer), each up to FC_TIMEOUT (3600 s).
        cmd = fc_cmd + list(map(str, a))
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=7500, env={**env, "FC_USAGE_TAG": name})
        except subprocess.TimeoutExpired:  # one stuck step must not stop the bookkeeping of the whole batch
            p = subprocess.CompletedProcess(cmd, 124, "", "評測工具等了 7500 秒，這一步沒有結束")
        log(name, f"fc {' '.join(map(str, a[:6]))} -> {p.returncode} {(p.stdout + p.stderr)[-400:].strip()}")
        return p

    def together(name, cmds):
        procs = [subprocess.Popen(fc_cmd + list(map(str, c)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                  env={**env, "FC_USAGE_TAG": name}) for c in cmds]
        codes = []
        for c, p in zip(cmds, procs):
            out, _ = p.communicate()
            codes.append(p.returncode)
            log(name, f"fc {' '.join(map(str, c))} -> {p.returncode} {out[-300:].strip()}")
        return codes

    def load(job):
        if job.startswith("probes/"):
            _, stem, target = job.split("/", 2)
            probe = tomllib.load(open(repo / "evals/probes" / f"{stem}.toml", "rb"))
            if "variant" in probe:  # the same message with the party swapped
                text, prompt = next(v for v in probe["variant"] if v["target"] == target)["text"], None
            elif "prompt" in probe:  # leading.toml: one message asked three ways; the target is the stance
                text, prompt = probe["message"], next(p for p in probe["prompt"] if p["stance"] == target)["text"]
            else:  # injection.toml: the target is the key that holds the text (clean, injected)
                text, prompt = probe[target], None
            return {"id": f"{stem}-{target}", "kind": "probe", "probe": stem, "target": target,
                    "input_type": "text", "input": text, "prompt": prompt}
        case = tomllib.load(open(repo / "evals/cases" / f"{job}.toml", "rb"))
        return {"id": case["id"], "kind": "case", "input_type": case["input_type"], "input": case["input"]}

    def new_run(slug):
        p = fc(slug, "init", "--mode", "full", "--host", args.host, "--slug", slug, "--base", base)
        return Path(p.stdout.strip())

    # One real detection for the whole batch, the way step 0 does it; every job gets a copy of its models.json.
    detect_run = new_run("detect")
    extra = (["--host-model", args.host_model] if args.host_model else []) + ["--host-effort", args.host_effort]
    d = fc("detect", "detect", "--run", detect_run, "--probe", *extra)
    if d.returncode != 0 or not (detect_run / "models.json").exists():
        sys.exit(f"detect failed: {d.stderr[-500:]}")
    print(d.stdout.strip(), d.stderr.strip(), sep="\n", flush=True)
    # A snapshot has no .git of its own; asked there, git answers for whatever repo the folder sits in. The export
    # writes the commit it was made from into a COMMIT file, and that is what gets recorded.
    stamp = repo / "COMMIT"
    head = stamp.read_text().strip() if stamp.exists() else subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() + "（工作目錄，可能有沒 commit 的修改）"
    (base / "batch.json").write_text(json.dumps(
        {"repo": str(repo), "commit": head, "host": args.host, "host_model": args.host_model,
         "host_effort": args.host_effort, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "jobs": args.jobs,
         "models": json.loads((detect_run / "models.json").read_text())}, ensure_ascii=False, indent=1))

    def job(job_id):
        try:
            return run_job(job_id)
        except Exception as exc:  # one broken job (a wrong name, a crash) must not lose the record of the others
            return {"name": job_id, "job": job_id, "kind": "probe" if job_id.startswith("probes/") else "case",
                    "run": "", "status": f"failed: {type(exc).__name__}: {exc}", "unreviewed_seats": [], "minutes": 0}

    def run_job(job_id):
        spec = load(job_id)
        name, t0 = spec["id"], time.time()
        run = new_run(name)
        shutil.copy(detect_run / "models.json", run / "models.json")
        log(name, f"run dir {run}")
        (run / "prompt.txt").write_text(
            spec.get("prompt") or ("幫我查核這篇報導" if spec["input_type"] == "url" else "幫我查核這則訊息"), encoding="utf-8")
        if spec["input_type"] == "url":
            (run / "url.txt").write_text(spec["input"].strip(), encoding="utf-8")
            p = fc(name, "input", "--run", run, "--type", "url", "--url-file", run / "url.txt", "--prompt-file", run / "prompt.txt")
        else:
            (run / "message.txt").write_text(spec["input"].strip(), encoding="utf-8")
            p = fc(name, "input", "--run", run, "--type", "text", "--file", run / "message.txt", "--prompt-file", run / "prompt.txt")
        status, unreviewed = ("failed at input" if p.returncode else None), []
        for role in ("prep",) if args.prep_only else ("prep", "tracer", "proponent"):
            if status is None and fc(name, "run-model", "--run", run, "--role", role).returncode != 0:
                status = f"failed at {role}"
        if args.prep_only:
            status = status or "stopped after prep"
        if status is None:
            seats = [s["seat"] for s in json.loads((run / "models.json").read_text())["seats"]]
            together(name, [["run-model", "--run", run, "--role", "opponent", "--seat", s] for s in seats])
            for role in ("rebuttal", "judge"):
                if status is None and fc(name, "run-model", "--run", run, "--role", role).returncode != 0:
                    status = f"failed at {role}"
        if status is None:
            listed = fc(name, "reviewers", "--run", run).stdout
            review_seats = [line.split("\t")[0] for line in listed.splitlines() if "\t" in line]
            if review_seats:
                cmds = [["run-model", "--run", run, "--role", "review", "--seat", s] for s in review_seats]
                # SKILL.md step 8: a review that fails is rerun once; if it fails again the run settles without it.
                for c in [c for c, code in zip(cmds, together(name, cmds)) if code != 0]:
                    if fc(name, *c).returncode != 0:
                        unreviewed.append(c[-1])
            for step in ("finalize", "score", "render"):
                if status is None and fc(name, step, "--run", run).returncode != 0:
                    status = f"failed at {step}"
        status = status or "ok"
        log(name, f"done: {status}")
        return {**{k: spec[k] for k in ("kind", "probe", "target") if k in spec}, "name": name, "job": job_id,
                "run": str(run), "status": status, "unreviewed_seats": unreviewed,
                "minutes": round((time.time() - t0) / 60, 1)}

    results_path = base / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for f in cf.as_completed([ex.submit(job, j) for j in args.jobs]):
            res = f.result()
            results.append(res)
            print(json.dumps(res, ensure_ascii=False), flush=True)
            results_path.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
