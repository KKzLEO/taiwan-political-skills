import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "factcheck"
sys.path.insert(0, str(SKILL / "scripts"))


def make_run(files: dict) -> Path:
    """Create a temp run dir with the given {name: obj} JSON files."""
    d = Path(tempfile.mkdtemp(prefix="fc-test-"))
    for name, obj in files.items():
        (d / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return d
