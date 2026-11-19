"""Find which model CLIs exist on this machine and assign debate seats.

A CLI counts only if it is on PATH (or overridden with FC_<ENGINE>_CMD),
belongs to a different vendor than the host, is on the same-tier whitelist,
and — when probed — actually answered.
"""

from __future__ import annotations

import fnmatch
import shlex
import shutil
import subprocess

INTERNAL_SEATS = [("A", "evidence"), ("B", "counter"), ("C", "stance")]


def _list_ollama(cmd):
    try:
        out = subprocess.run(cmd + ["list"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=20)  # not the locale's encoding (Big5, cp950)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    lines = out.stdout.strip().splitlines()[1:]
    return [line.split()[0] for line in lines if line.strip()]


def _command(e, which, env):
    override = env.get(f"FC_{e['id'].upper()}_CMD")
    if override:
        return shlex.split(override)
    # Store the bare name, not the absolute path: run folders are shared and must not leak $HOME.
    return [e["cli"]] if which(e["cli"]) else None


def detect(host, tiers, which=shutil.which, env=None, list_ollama=_list_ollama, probe=None):
    env = env or {}
    host_vendor = tiers["hosts"][host]
    patterns = tiers.get("local", {}).get("same_tier_patterns", [])
    engines = []
    for e in tiers["engine"]:
        cmd = _command(e, which, env)
        # The model and effort the roles will run with, so the report can show them; build_command reads these first.
        base = {"engine": e["id"], "vendor": e["vendor"], "available": cmd is not None, "cmd": cmd,
                "cross_model": e["vendor"] != host_vendor, "can_search": e["can_search"],
                "same_tier": e["same_tier"], "model": env.get(f"FC_{e['id'].upper()}_MODEL") or None,
                "probe": "skipped", "isolation": "unknown"}
        if e["id"] == "codex":  # always given to codex, whose CLI default was none (run_model.build_command)
            base["effort"] = env.get("FC_CODEX_EFFORT") or "high"
        elif e["id"] == "claude" and env.get("FC_CLAUDE_EFFORT"):  # the other engines take no effort setting
            base["effort"] = env["FC_CLAUDE_EFFORT"]
        if e["id"] == "ollama":
            if cmd is None:
                engines.append(base)
                continue
            for name in list_ollama(cmd):
                same = any(fnmatch.fnmatch(name, p) for p in patterns)
                engines.append({**base, "model": name, "same_tier": same})
            continue
        engines.append(base)

    if probe is not None:
        for e in engines:
            if e["available"] and e["cross_model"] and e["same_tier"]:
                e.update(probe(e))
    return {"host": host, "host_vendor": host_vendor, "engines": engines}


def assign_seats(models, mode):
    host = models["host"]
    external = [e for e in models["engines"]
                if e["available"] and e["cross_model"] and e["same_tier"] and e["probe"] != "failed"]
    ext_seats = [{"seat": f"X{i}", "engine": e["engine"], "model": e.get("model"), "kind": "external",
                  "lens": "external", "vendor": e["vendor"], "can_search": e["can_search"]}
                 for i, e in enumerate(external, start=1)]
    internal = [{"seat": s, "engine": host, "model": None, "kind": "internal", "lens": lens,
                 "vendor": models["host_vendor"], "can_search": True} for s, lens in INTERNAL_SEATS]
    if mode == "quick":
        return ext_seats[:1] if ext_seats else [internal[1]]
    return internal + ext_seats


def seat_status(run):
    """Summarise every opponent seat for scoring. cross_model is computed here, never read from model output.
    A seat assigned in models.json without an opponent file is listed as missing."""
    from pathlib import Path

    from . import io

    run = Path(run)
    models = io.read_json(run / "models.json")
    host_vendor = models["host_vendor"]
    by_engine = {}
    for e in models.get("engines", []):
        by_engine.setdefault(e["engine"], e)

    def entry(seat, engine, status, lens):
        if engine == models["host"] or not str(seat).startswith("X"):
            vendor, can_search, isolation = host_vendor, True, "host"
        else:
            info = by_engine.get(engine, {})
            vendor = info.get("vendor", "unknown")
            can_search = bool(info.get("can_search", False))
            isolation = info.get("isolation", "unknown")
        return {"seat": seat, "engine": engine, "status": status,
                "cross_model": vendor not in (host_vendor, "unknown"), "can_search": can_search,
                "isolation": isolation, "lens": lens}

    out = []
    for path in sorted(run.glob("opponent-*.json")):
        data = io.read_json(path)
        out.append(entry(data.get("seat"), data.get("engine"), data.get("status", "ok"), data.get("lens")))
    present = {s["seat"] for s in out}
    out += [entry(s["seat"], s.get("engine"), "missing", s.get("lens"))
            for s in models.get("seats", []) if s["seat"] not in present]
    return sorted(out, key=lambda s: str(s["seat"]))
