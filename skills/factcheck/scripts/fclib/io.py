"""Small file helpers. Paths in, plain data out."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = SKILL_DIR / "data"
REFERENCES_DIR = SKILL_DIR / "references"


class ReadError(ValueError):
    pass


def read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ReadError(f"找不到檔案：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ReadError(f"{Path(path).name} 不是合法的 JSON（第 {exc.lineno} 行）：{exc.msg}") from exc


def read_json_or_none(path: Path):
    try:
        return read_json(path)
    except ReadError:
        return None


def write_json(path: Path, obj) -> None:
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_toml(path: Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def known_tactic_ids(region: str = "tw"):
    path = DATA_DIR / region / "tactics.toml"
    if not path.exists():
        return None
    return {t["id"] for t in read_toml(path).get("tactic", [])}
