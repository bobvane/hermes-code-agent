#!/usr/bin/env python3
"""Self-test for hca_gate.py — run: python tests/test_hca_gate.py"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GATE = str(Path(__file__).resolve().parent.parent / "scripts" / "hca_gate.py")
PASS = 0
FAIL = 0


def sh(cmd, cwd):
    return subprocess.run([sys.executable, GATE] + cmd, cwd=cwd,
                          capture_output=True, text=True)


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f" FAIL {name} {detail}")


def fresh_git_repo():
    d = Path(tempfile.mkdtemp(prefix="hca_test_"))
    subprocess.run(["git", "init", "-q"], cwd=d)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "--allow-empty", "-qm", "init"], cwd=d)
    return d


# --- test 1: quickcheck green/red on Python files
d = fresh_git_repo()
(d / "good.py").write_text("x = 1\n")
(d / "bad.py").write_text("def broken(:\n")
r = sh(["quickcheck", "good.py"], d)
check("quickcheck pass → exit 0", r.returncode == 0, r.stdout + r.stderr)
r = sh(["quickcheck", "bad.py"], d)
check("quickcheck syntax error → exit !=0",
      r.returncode != 0 and "HCA-GATE-RED" in (r.stdout + r.stderr))
shutil.rmtree(d)

# --- test 2: doomcheck fires at threshold with same tag
d = fresh_git_repo()
tags = ["doomcheck", "doomcheck", "doomcheck"]
codes = [sh([t, "edit:same:spot"], d).returncode for t in tags]
check("doomcheck 3x same tag → exit 2 on third",
      codes == [0, 0, 2], f"got {codes}")
r = sh(["doomcheck", "different:action"], d)
check("doomcheck different tag → exit 0", r.returncode == 0)
shutil.rmtree(d)

# --- test 3: verify fails hard when no tests exist (never fake green)
d = fresh_git_repo()
r = sh(["verify"], d)
check("verify without any test command → RED (no fake green)",
      r.returncode != 0 and "no test command" in r.stdout)
shutil.rmtree(d)

# --- test 4: verify passes a real pytest project / records state
d = fresh_git_repo()
(d / "pyproject.toml").write_text("[project]\nname='t'\n")
(d / "tests").mkdir()
(d / "tests" / "test_ok.py").write_text(
    "def test_ok():\n    assert 1 == 1\n")
# provide a project-local venv whose python has pytest, so verify can
# self-bootstrap onto it regardless of the outer environment
venv_py = d / ".venv" / "bin"
venv_py.mkdir(parents=True)
venv_py.joinpath("python").write_text(
    "#!/bin/sh\nexec " + sys.executable + " \"$@\"\n")
venv_py.joinpath("python").chmod(0o755)
r = sh(["verify"], d)
st_file = d / ".hca_state.json"
check("verify pytest pass (venv bootstrap) → exit 0", r.returncode == 0,
      r.stdout[-300:])
check("state file written", st_file.exists())
if st_file.exists():
    st = json.loads(st_file.read_text())
    check("git_head recorded in state", bool(st.get("git_head")))

# --- test 5: verify red increments redfix counter
(d / "tests" / "test_bad.py").write_text(
    "def test_bad():\n    assert 1 == 2\n")
codes = []
for _ in range(2):
    r = sh(["verify"], d)
    codes.append(r.returncode)
st = json.loads(st_file.read_text())
check("verify red → exit !=0 twice", all(c != 0 for c in codes))
check("redfix counter incremented to 2",
      st.get("redfix", {}).get("verify") == 2, str(st.get("redfix")))

# --- test 6: plancheck detects source edits during PLAN
subprocess.run(["git", "add", "-A"], cwd=d)
subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "-qm", "wip"], cwd=d)
(d / "src_edit.py").write_text("y = 2\n")
r = sh(["plancheck"], d)
check("plancheck flags new source file → exit !=0",
      r.returncode != 0 and "PLAN step must not modify" in r.stdout)
(d / "src_edit.py").unlink()
r = sh(["plancheck"], d)
check("plancheck clean tree → exit 0", r.returncode == 0)

# --- test 7: state stale detection after head moves
st = json.loads(st_file.read_text())
st["git_head"] = "0" * 40
st_file.write_text(json.dumps(st))
r = sh(["state", "show"], d)
check("stale state detected → exit !=0", r.returncode != 0)
r = sh(["state", "reset"], d)
check("state reset works", r.returncode == 0)

# --- test 8: snapshot records ids
subprocess.run(["git", "add", "-A"], cwd=d)
subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "-qm", "wip2"], cwd=d)
r = sh(["snapshot"], d)
st = json.loads((d / ".hca_state.json").read_text())
check("snapshot recorded", r.returncode == 0 and len(st["snapshots"]) >= 1)

shutil.rmtree(d)

# --- test 9: guard record/check detects judge tampering
d = fresh_git_repo()
(d / "pyproject.toml").write_text("[project]\nname='t'\n")
(d / "tests").mkdir()
judge = d / "tests" / "test_ok.py"
judge.write_text("def test_ok():\n    assert 1 == 1\n")
r = sh(["guard", "record"], d)
check("guard record → exit 0", r.returncode == 0)
r = sh(["guard", "check"], d)
check("guard check clean → exit 0", r.returncode == 0)
# tamper: modify the oracle
judge.write_text("def test_ok():\n    assert True  # weakened\n")
r = sh(["guard", "check"], d)
check("guard check tampered → exit 3 + TAMPER msg",
      r.returncode == 3 and "TAMPER" in r.stdout)
# verify must refuse (exit 3) when oracle tampered
r = sh(["verify"], d)
check("verify with tampered judge → exit 3",
      r.returncode == 3 and "TAMPER" in r.stdout)
# restore and confirm clean
judge.write_text("def test_ok():\n    assert 1 == 1\n")
r = sh(["guard", "check"], d)
check("guard check after restore → exit 0", r.returncode == 0)

# --- test 10: verify unavailable runner prints concrete FIX with .venv
d = fresh_git_repo()
(d / "pyproject.toml").write_text("[project]\nname='t'\n")
(d / "tests").mkdir()
(d / "tests" / "test_x.py").write_text("def test_x():\n    assert 1\n")
r = sh(["verify"], d)  # system python lacks pytest in this venv-less repo
out = r.stdout
check("verify w/o runner → RED with FIX hint or venv retry",
      r.returncode != 0 and ("FIX:" in out or "venv" in out
                             or "no test command" in out), out[-300:])
shutil.rmtree(d)

# --- test 11: transactional snapshot captures untracked files, restore works
d = fresh_git_repo()
(d / "tracked.txt").write_text("v1\n")
subprocess.run(["git", "add", "-A"], cwd=d)
subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "-qm", "base"], cwd=d)
r = sh(["snapshot"], d)
check("transactional snapshot records ref",
      r.returncode == 0 and "ref=refs/hca/snapshots/" in r.stdout, r.stdout)
# dirty the worktree: modify tracked + create untracked
(d / "tracked.txt").write_text("v2 broken\n")
(d / "untracked_new.py").write_text("garbage\n")
r = sh(["restore"], d)   # restore to last snapshot
out = r.stdout
check("restore → exit 0 + clean status",
      r.returncode == 0 and "clean" in out, out)
check("restore recovered tracked content", (d / "tracked.txt").read_text() == "v1\n")
check("restore removed untracked file", not (d / "untracked_new.py").exists())
# QA condition: state records restored_from
st = json.loads((d / ".hca_state.json").read_text())
check("restored_from recorded in state", "restored_from" in st)
shutil.rmtree(d)

# --- test 12: budget soft reminders fire once per tier (deduped)
d = fresh_git_repo()
sh(["state", "reset"], d)
for _ in range(4):
    sh(["state", "bump"], d)
st = json.loads((d / ".hca_state.json").read_text())
st["tokens_verify"] = [3500]  # above tier-1 (3000), below tier-2
(d / ".hca_state.json").write_text(json.dumps(st))
r = sh(["verify"], d)  # will be RED (no tests); reminder may appear in msg
st2 = json.loads((d / ".hca_state.json").read_text())
fired1 = st2.get("budget_fired", [])
# second verify: same spend → tiers already fired, must NOT re-append
r2 = sh(["verify"], d)
st3 = json.loads((d / ".hca_state.json").read_text())
fired2 = st3.get("budget_fired", [])
check("budget tiers dedupe across runs",
      fired1 and "steps" in fired1 and "tok3000" in fired1
      and fired1 == fired2,
      f"{fired1} vs {fired2}")
shutil.rmtree(d)

# --- test 13: compact trims old snapshots deterministically, keeps tail
d = fresh_git_repo()
st = {"steps": 1, "redfix": {}, "doom": [], "snapshots":
      [{"id": f"s{i:040d}", "ref": None} for i in range(15)],
      "git_head": "x" * 40}
(d / ".hca_state.json").write_text(json.dumps(st))
r = sh(["compact"], d)
st2 = json.loads((d / ".hca_state.json").read_text())
check("compact keeps last 10 snapshots",
      len(st2["snapshots"]) == 11
      and st2["snapshots"][0].startswith("compacted:"), str(len(st2["snapshots"])))
r = sh(["compact"], d)
check("second compact is a no-op",
      r.returncode == 0 and ("nothing to compact" in r.stdout
                             or "compacted" in r.stdout), r.stdout)
shutil.rmtree(d)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
