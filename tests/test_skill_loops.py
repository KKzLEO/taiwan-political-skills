import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

SKILL_MD = (ROOT / "skills" / "factcheck" / "SKILL.md").read_text(encoding="utf-8")

# Stands in for fc.py: a seat succeeds only once every seat has started, so seats run one after another all fail.
STUB = '''import pathlib, sys, time
args = sys.argv[1:]
here = pathlib.Path(__file__).resolve().parent
if args[0] == "reviewers":
    print("A\\tC1\\nB\\tC1\\nC\\tC1")
    sys.exit(0)
(here / ("started-" + args[args.index("--seat") + 1])).write_text("")
deadline = time.time() + 2
while time.time() < deadline:
    if len(list(here.glob("started-*"))) == 3:
        sys.exit(0)
    time.sleep(0.02)
sys.exit(1)
'''


def block_after(sentence):
    """The shell block a host copies, the first one after `sentence` in SKILL.md."""
    return SKILL_MD.split(sentence, 1)[1].split("```bash\n", 1)[1].split("```", 1)[0]


class SeatsStartTogetherTest(unittest.TestCase):
    """2026-11-20 real-host runs: zsh puts only the last command of `a || b &` in the background, so the loops for
    the opponents and for the reviews ran one seat at a time on macOS, where both hosts' shell is zsh."""

    def run_loop(self, shell, sentence):
        skill, run = Path(tempfile.mkdtemp(prefix="fc-skill-")), Path(tempfile.mkdtemp(prefix="fc-run-"))
        (skill / "scripts").mkdir()
        (skill / "scripts" / "fc.py").write_text(STUB)
        (run / "models.json").write_text(json.dumps({"seats": [{"seat": s} for s in "ABC"]}))
        script = f'SKILL="{skill}"; RUN="{run}";\n' + block_after(sentence)
        p = subprocess.run([shell, "-c", script], capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout + p.stderr

    def check(self, shell):
        for sentence, failed in (("第 5 步所有反方同時跑", "反方沒有跑起來"), ("第 8 步：`fc.py reviewers` 列出的每個席位", "覆核失敗")):
            with self.subTest(shell=shell, loop=failed):
                code, out = self.run_loop(shell, sentence)
                self.assertEqual(code, 0, out)
                self.assertNotIn(failed, out)

    def test_in_bash(self):
        self.check("/bin/bash")

    @unittest.skipUnless(os.path.exists("/bin/zsh"), "no zsh here")
    def test_in_zsh(self):
        self.check("/bin/zsh")


if __name__ == "__main__":
    unittest.main()
