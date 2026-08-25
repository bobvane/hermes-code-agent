#!/usr/bin/env python3
"""Self-test for hca_gate.py — run: python tests/test_hca_gate.py"""

import json
import os
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

# --- semantic doom: same failure set 3x in a row → exit 2 ---
d = fresh_git_repo()
(d / "pyproject.toml").write_text("[project]\nname='t'\n")
(d / "tests").mkdir()
(d / "tests" / "test_a.py").write_text(
    "def test_one():\n    assert 1 == 2\n"
    "def test_two():\n    assert 2 == 3\n")
venv_py = d / ".venv" / "bin"
venv_py.mkdir(parents=True)
venv_py.joinpath("python").write_text(
    "#!/bin/sh\nexec " + sys.executable + " \"$@\"\n")
venv_py.joinpath("python").chmod(0o755)
codes = []
for _ in range(3):
    r = sh(["verify"], d)
    codes.append(r.returncode)
check("semantic doom: red, red, then exit 2",
      codes[:2] == [1, 1] and codes[2] == 2, str(codes))
check("semantic doom message shown", "DOOM" in r.stdout
      and "Same failure set" in r.stdout, r.stdout[-200:])
st_file = d / ".hca_state.json"
if st_file.exists():
    st = json.loads(st_file.read_text())
    fps = st.get("fail_fp") or []
    check("fail_fp history kept (capped at threshold)",
          len(fps) <= 3 and len(set(fps)) == 1, str(fps))

# --- recovery: a different failure set resets the streak ---
# make only test_two fail now (fix test_one): fingerprint changes → not doom
(d / "tests" / "test_a.py").write_text(
    "def test_one():\n    assert 1 == 1\n"
    "def test_two():\n    assert 2 == 3\n")
r = sh(["verify"], d)
check("changed failure set → back to plain RED (not doom)", r.returncode == 1,
      f"rc={r.returncode}")

# --- budget hard stop: token overspend → exit 2 + escalation hint ---
d = fresh_git_repo()
(d / "pyproject.toml").write_text("[project]\nname='t'\n")
(d / "tests").mkdir()
(d / "tests" / "test_bad.py").write_text(
    "def test_x():\n    assert 1 == 2\n")
venv_py = d / ".venv" / "bin"
venv_py.mkdir(parents=True)
venv_py.joinpath("python").write_text(
    "#!/bin/sh\nexec " + sys.executable + " \"$@\"\n")
venv_py.joinpath("python").chmod(0o755)
# simulate heavy prior spend directly in state
st = {"steps": 0, "redfix": {"verify": 4}, "doom": [],
      "tokens_verify": [9000, 7000]}
(d / ".hca_state.json").write_text(json.dumps(st))
r = sh(["verify"], d)
check("token overspend → exit 2", r.returncode == 2, f"rc={r.returncode}")
check("overspend reason shown", "cost ~16000 tok" in r.stdout
      or "cap" in r.stdout, r.stdout[-200:])
check("escalation hint suggests stronger model",
      "stronger" in r.stdout and "model" in r.stdout, r.stdout[-300:])
check("escalation hint is bilingual + red",
      "此模型不胜任此编程任务" in r.stdout and "\033[1;31m" in r.stdout,
      repr(r.stdout[-200:]))
shutil.rmtree(d)

# --- ⑥ auto-commit: green verify lands a checkpoint commit ---
d = fresh_git_repo()
(d / "pyproject.toml").write_text("[project]\nname='t'\n")
(d / "tests").mkdir()
(d / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
venv_py = d / ".venv" / "bin"
venv_py.mkdir(parents=True)
venv_py.joinpath("python").write_text(
    "#!/bin/sh\nexec " + sys.executable + " \"$@\"\n")
venv_py.joinpath("python").chmod(0o755)
subprocess.run(["git", "add", "-A"], cwd=d)
subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "-qm", "base"], cwd=d)
(d / "mod.py").write_text("x = 1\n")   # dirty tree
r = sh(["verify"], d)
check("auto-commit: green verify lands checkpoint",
      r.returncode == 0 and "auto-committed checkpoint #1" in r.stdout,
      r.stdout[-200:])
log = subprocess.run(["git", "log", "--oneline", "-2"], cwd=d,
                     capture_output=True, text=True).stdout
check("auto-commit message in log", "green checkpoint" in log, log)
r = sh(["verify"], d)   # clean tree now
n_commits = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=d,
                           capture_output=True, text=True).stdout.strip()
check("auto-commit skips clean tree",
      r.returncode == 0 and n_commits == "3", f"{n_commits} commits")
shutil.rmtree(d)

# --- ⑤ patch: three-tier fallback ---
d = fresh_git_repo()
(d / "app.py").write_text(
    "def alpha():\n"
    "    return   1      \n"
    "\n"
    "def beta():\n"
    "    return 2\n")
subprocess.run(["git", "add", "-A"], cwd=d)
subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "-qm", "init"], cwd=d)
pf = d / "p.diff"
# tier-1 exact
pf.write_text("--- a/app.py\n+++ b/app.py\n"
              "@@ -4,2 +4,2 @@\n"
              " def beta():\n"
              "-    return 2\n"
              "+    return 22\n")
r = sh(["patch", "p.diff"], d)
check("patch tier1 exact apply",
      r.returncode == 0 and "[exact]" in r.stdout, r.stdout)
check("tier1 content landed", "return 22" in (d / "app.py").read_text())
subprocess.run(["git", "checkout", "--", "app.py"], cwd=d)
# tier-2 whitespace drift
pf.write_text("--- a/app.py\n+++ b/app.py\n"
              "@@ -2 +2 @@\n"
              "-    return   1      \n"
              "+    return 11\n")
r = sh(["patch", "p.diff"], d)
check("patch tier2 fuzzy apply",
      r.returncode == 0 and ("[fuzzy" in r.stdout or "[exact]" in r.stdout),
      r.stdout)
subprocess.run(["git", "checkout", "--", "app.py"], cwd=d)
# tier-3 anchor (wrong context lines, unique removed core)
pf.write_text("--- a/app.py\n+++ b/app.py\n"
              "@@ -10,3 +10,3 @@\n"
              " WRONG CONTEXT LINE\n"
              "-    return 2\n"
              "+    return 222\n"
              " ANOTHER WRONG LINE\n")
r = sh(["patch", "p.diff"], d)
check("patch tier3 anchor apply",
      r.returncode == 0 and "[anchor]" in r.stdout, r.stdout)
check("tier3 content landed", "return 222" in (d / "app.py").read_text())
# all tiers fail
pf.write_text("--- a/app.py\n+++ b/app.py\n"
              "@@ -1,2 +1,2 @@\n"
              "-NO SUCH CONTENT XYZ\n"
              "+whatever\n")
r = sh(["patch", "p.diff"], d)
check("patch all-tiers fail → RED exit1",
      r.returncode == 1 and "FAILED" in r.stdout, r.stdout[-200:])
shutil.rmtree(d)

# --- ④ repomap ---
d = fresh_git_repo()
(d / "big.py").write_text(
    "".join(f"def fn{i}():\n    pass\n\n" for i in range(6)))
(d / "small.py").write_text("def only_one():\n    pass\n")
os.makedirs(d / "node_modules", exist_ok=True)
(d / "node_modules" / "junk.js").write_text("function junk() {}\n")
r = sh(["repomap"], d)
check("repomap lists files ranked by symbols",
      r.returncode == 0 and "big.py" in r.stdout
      and "small.py" in r.stdout, r.stdout)
lines = [ln for ln in r.stdout.splitlines() if ".py (" in ln]
check("repomap big.py ranks first",
      bool(lines) and "big.py" in lines[0], str(lines[:2]))
check("repomap skips node_modules", "junk.js" not in r.stdout)
shutil.rmtree(d)

# --- ⑦ overflow forced deterministic compression ---
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "_gate", os.path.join(os.path.dirname(__file__), "..", "scripts",
                          "hca_gate.py"))
_gate = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_gate)
huge = "E " + "x" * 50000          # one pathological line
out = _gate.trim_output(huge, 1000)
check("overflow compressed under cap", len(out) <= 1100,
      f"len={len(out)}")
check("overflow marker present", "overflow compressed" in out)
check("overflow deterministic",
      _gate.trim_output(huge, 1000) == out)

# --- ⑧ locate: Aider did-you-mean fuzzy rescue (read-only) ---
d = Path(tempfile.mkdtemp(prefix="hca_locate_"))
(d / "s.py").write_text(
    "def foo():\n    return 1\n\n\ndef bar(x):\n    y = x * 22\n    return y + 1\n")
probe = "def bar(x):\n    y = x * 2\n    return y + 1\n"
r = subprocess.run([sys.executable, GATE, "locate", str(d / "s.py")],
                   input=probe, capture_output=True, text=True)
check("locate finds near-match with high similarity",
      r.returncode == 0 and "similarity 9" in r.stdout
      and "def bar(x):" in r.stdout, r.stdout[:200])
(d / "s.py").write_text("class TotallyDifferent:\n    pass\n")
r = subprocess.run([sys.executable, GATE, "locate", str(d / "s.py")],
                   input=probe, capture_output=True, text=True)
check("locate rejects no-anchor file",
      r.returncode == 1 and "no fuzzy anchor" in r.stdout, r.stdout[:200])
hunk = "-    y = x * 22\n+    y = x * 33\n     return y + 1\n"
(d / "s.py").write_text("def foo():\n    return 1\n\n\ndef bar(x):\n"
                        "    y = x * 22\n    return y + 1\n")
r = subprocess.run([sys.executable, GATE, "locate", str(d / "s.py")],
                   input=hunk, capture_output=True, text=True)
check("locate strips diff markers from probe",
      r.returncode == 0, r.stdout[:200])
shutil.rmtree(d)

# --- ⑨ check_cmd: Codex execpolicy x Gemini substitution scan ---
d = Path(tempfile.mkdtemp(prefix="hca_cmd_"))
def cc(cmd):
    return subprocess.run([sys.executable, GATE, "check_cmd", cmd],
                          capture_output=True, text=True, cwd=d)
r = cc("git status")
check("check_cmd allows read-only git status", r.returncode == 0)
r = cc("git reset --hard HEAD~1")
check("check_cmd denies reset --hard", r.returncode == 1 and "DENY" in r.stdout)
r = cc("git log && rm -rf /tmp/x")
check("check_cmd compound: safe && dangerous → deny",
      r.returncode == 1 and "rm" in r.stdout)
r = cc("echo $(cat /etc/passwd)")
check("check_cmd substitution in allowed verb → confirm",
      r.returncode == 3 and "substitution" in r.stdout)
r = cc("terraform apply")
check("check_cmd unmatched command → default confirm (fail-closed)",
      r.returncode == 3)
r = cc("grep '$(not real)' file.txt")
check("check_cmd quoted $() not flagged (quote-aware)",
      r.returncode == 0, r.stdout[:150])
shutil.rmtree(d)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
