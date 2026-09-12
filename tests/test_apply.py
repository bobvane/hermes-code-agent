#!/usr/bin/env python3
"""Regression checks for hca_gate.py — apply / path safety / secret guard.

    python tests/test_apply.py      # stdlib only, no pytest needed
    python -m pytest tests/         # also works

One file, no fixtures, no framework: each check builds its own throwaway git
repo under /tmp. These pin the v2.4.0 fixes specifically — delete a
regression test only when the behaviour it pins is deliberately dropped.
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
GATE = SCRIPTS / "hca_gate.py"
sys.path.insert(0, str(SCRIPTS))
import hca_gate  # noqa: E402  (module-level constants only; no side effects)

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        FAILED.append(name)


def new_repo():
    d = Path(tempfile.mkdtemp(prefix="hca-test-"))
    for cmd in (["git", "init", "-q"],
                ["git", "config", "user.email", "t@t.t"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=d, check=True, capture_output=True)
    return d


def gate(cwd, *argv):
    return subprocess.run([sys.executable, str(GATE), *argv],
                          cwd=cwd, capture_output=True, text=True)


def apply(cwd, patch_text):
    """Write the patch beside the repo and apply it."""
    pf = cwd / "_t.diff"
    pf.write_text(patch_text)
    return gate(cwd, "apply", pf.name)


# ---------------------------------------------------------------- apply cases

def test_modify_and_multihunk():
    d = new_repo()
    (d / "m.txt").write_text("a\nb\nc\nd\ne\n")
    r = apply(d, """--- a/m.txt
+++ b/m.txt
@@ -1,2 +1,2 @@
-a
+a1
 b
@@ -4,2 +4,2 @@
 d
-e
+e1
""")
    got = (d / "m.txt").read_text()
    check("apply: multi-hunk single file", r.returncode == 0 and got == "a1\nb\nc\nd\ne1\n",
          f"rc={r.returncode} got={got!r}")


def test_same_file_two_blocks_chain():
    """CG-2 regression: block 2 must build on block 1, not on stale disk."""
    d = new_repo()
    (d / "dup.txt").write_text("A\nB\nC\nD\nE\n")
    r = apply(d, """--- a/dup.txt
+++ b/dup.txt
@@ -1,2 +1,2 @@
-A
+A1
 B
--- a/dup.txt
+++ b/dup.txt
@@ -4,2 +4,2 @@
 D
-E
+E2
""")
    got = (d / "dup.txt").read_text()
    check("apply: two blocks, same file, both land",
          r.returncode == 0 and got == "A1\nB\nC\nD\nE2\n",
          f"rc={r.returncode} got={got!r}")


def test_new_file():
    d = new_repo()
    r = apply(d, """--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+def f():
+    return 1
""")
    check("apply: create new file",
          r.returncode == 0 and (d / "new.py").read_text().startswith("def f():"),
          f"rc={r.returncode}")


def test_multifile_rollback():
    """CG-1 regression: file N failing at COMMIT must restore files 1..N-1.
    Second target lives under a path whose parent is a regular file, so phase 1
    (in-memory) succeeds but phase 2 (mkdir/commit) raises."""
    d = new_repo()
    (d / "good.txt").write_text("g\n")
    (d / "blocked").write_text("i am a regular file, not a dir\n")
    r = apply(d, """--- a/good.txt
+++ b/good.txt
@@ -1 +1 @@
-g
+g_changed
--- /dev/null
+++ b/blocked/child.txt
@@ -0,0 +1 @@
+new line
""")
    got = (d / "good.txt").read_text()
    check("apply: multi-file failure rolls back earlier files",
          r.returncode == 1 and got == "g\n",
          f"rc={r.returncode} good.txt={got!r} (expected unchanged 'g\\n')")
    check("apply: rollback reports it (no raw traceback)",
          "Traceback" not in r.stdout + r.stderr and "ROLLED BACK" in r.stdout,
          f"stdout={r.stdout[-220:]!r}")


def test_binary_file_rejected():
    d = new_repo()
    (d / "bin.dat").write_bytes(b"\x00\x01\x02\xff")
    r = apply(d, """--- a/bin.dat
+++ b/bin.dat
@@ -1 +1 @@
-abc
+def
""")
    out = r.stdout + r.stderr
    check("apply: binary file → structured error, not a traceback",
          r.returncode == 1 and "Traceback" not in out and "binary" in out.lower(),
          f"rc={r.returncode} out={out[-200:]!r}")


def test_delete_and_rename_rejected():
    d = new_repo()
    (d / "del.txt").write_text("x\n")
    rd = apply(d, """--- a/del.txt
+++ /dev/null
@@ -1 +0,0 @@
-x
""")
    check("apply: delete patch → clear 'not supported'",
          rd.returncode == 1 and "delete-file patches are not supported" in rd.stdout,
          f"rc={rd.returncode} out={rd.stdout[-160:]!r}")
    rr = apply(d, """diff --git a/o.txt b/n.txt
similarity index 100%
rename from o.txt
rename to n.txt
""")
    check("apply: rename patch → clear 'not supported'",
          rr.returncode == 1 and "rename patches are not supported" in rr.stdout,
          f"rc={rr.returncode} out={rr.stdout[-160:]!r}")


# ------------------------------------------------------------- path safety

def test_path_safety():
    d = new_repo()
    (d / "ok.txt").write_text("x\n")
    cases = {
        "traversal": "../../etc/passwd",
        "absolute": "/etc/passwd",
        "dotgit": ".git/HEAD",
        "state file": ".hca_state.json",
    }
    for name, target in cases.items():
        r = apply(d, f"--- a/{target}\n+++ b/{target}\n@@ -1 +1 @@\n-a\n+b\n")
        check(f"path: {name} rejected",
              r.returncode == 1 and "Traceback" not in r.stdout + r.stderr,
              f"rc={r.returncode} out={(r.stdout + r.stderr)[-160:]!r}")


def test_repo_root_anchoring():
    """P1 regression: run from a subdir — paths must anchor to the REPO root."""
    d = new_repo()
    (d / "root.txt").write_text("root\n")
    sub = d / "sub"
    sub.mkdir()
    r = apply(sub, """--- a/root.txt
+++ b/root.txt
@@ -1 +1 @@
-root
+patched
""")
    check("path: subdir run anchors to repo root",
          r.returncode == 0
          and (d / "root.txt").read_text() == "patched\n"
          and not (sub / "root.txt").exists(),
          f"rc={r.returncode} root={ (d/'root.txt').read_text()!r} "
          f"stray_subdir_copy={(sub/'root.txt').exists()}")


# ------------------------------------------------------- autocommit secrets

def test_autocommit_refuses_secrets():
    """P0 regression: `git add -A` must not sweep .env into a checkpoint."""
    d = new_repo()
    (d / "app.py").write_text("print(1)\n")
    (d / ".env").write_text("SECRET=leaked\n")
    (d / "server.key").write_text("-----BEGIN KEY-----\n")
    r = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); "
         "import hca_gate; hca_gate.autocommit({'redfix': {}})"],
        cwd=d, capture_output=True, text=True)
    ls = subprocess.run(["git", "log", "--name-only", "--format="],
                        cwd=d, capture_output=True, text=True).stdout.split()
    check("autocommit: .env / *.key never committed",
          ".env" not in ls and "server.key" not in ls,
          f"committed={ls} out={r.stdout[-200:]!r}")
    check("autocommit: legitimate file still committed",
          "app.py" in ls, f"committed={ls}")


# ----------------------------------------------------------------- timeout

def test_run_timeout_kills_group():
    t0 = time.time()
    rc, out = hca_gate.run([sys.executable, "-c",
                            "import time; time.sleep(30)"], timeout=1)
    dt = time.time() - t0
    check("run(): timeout returns 124 promptly (group killed)",
          rc == 124 and dt < 10, f"rc={rc} dt={dt:.1f}s out={out[:80]!r}")


def test_dangerous_command_verdicts():
    """cmd_policy + interpreter-escape backstops."""
    d = new_repo()
    def verdict(cmd):
        r = gate(d, "check_cmd", cmd)
        return r.returncode
    cases = [
        ("rm -rf /", 1),                     # deny
        ("find . -name '*.py' -delete", 3),  # allowlisted verb + destructive flag
        ("find . -name '*.py' -exec rm {} ;", 3),
        ("python -c 'print(1)'", 3),
        ("bash -c 'ls'", 3),
        ("ls -la", 0),                       # clean allow
    ]
    for cmd, want in cases:
        got = verdict(cmd)
        check(f"check_cmd: {cmd[:34]!r} -> exit {want}", got == want,
              f"got exit {got}")


def test_git_dir_case_insensitive():
    """.GIT/.Git are the same directory as .git on macOS/Windows."""
    d = new_repo()
    for name in (".GIT/config", ".Git/config"):
        r = apply(d, f"--- a/{name}\n+++ b/{name}\n@@ -1 +1 @@\n-a\n+b\n")
        check(f"path: {name} rejected",
              r.returncode == 1 and "Traceback" not in r.stdout + r.stderr,
              f"rc={r.returncode} out={(r.stdout + r.stderr)[-160:]!r}")


def test_update_pending_snooze():
    """--snooze is the only writer of next_prompt_ts; without it the upgrade
    prompt comes back on the very next task."""
    d = Path(tempfile.mkdtemp(prefix="hca-skill-"))
    (d / "scripts").mkdir()
    for f in ("hca_gate.py", "cmd_policy.yaml"):
        (d / "scripts" / f).write_bytes((SCRIPTS / f).read_bytes())
    (d / "SKILL.md").write_text("---\nversion: 9.9.9\n---\n")
    (d / "skill_state.json").write_text(
        '{"last_check_ts": 0, "next_prompt_ts": 0, '
        '"pending": {"remote": "9.9.9", "local": "1.0.0"}}')
    r = subprocess.run([sys.executable, str(d / "scripts" / "hca_gate.py"),
                        "update-pending", "--snooze"],
                       cwd=d, capture_output=True, text=True)
    npt = json.loads((d / "skill_state.json").read_text())["next_prompt_ts"]
    check("update-pending --snooze arms the cooldown",
          r.returncode == 0 and npt > time.time() + 2 * 86400,
          f"rc={r.returncode} next_prompt_ts={npt} out={r.stdout[-120:]!r}")
    r2 = subprocess.run([sys.executable, str(d / "scripts" / "hca_gate.py"),
                         "update-pending"],
                        cwd=d, capture_output=True, text=True)
    check("update-pending after snooze stays quiet",
          "none pending" in r2.stdout, f"out={r2.stdout[-120:]!r}")


ALL = [test_modify_and_multihunk, test_same_file_two_blocks_chain,
       test_new_file, test_multifile_rollback, test_binary_file_rejected,
       test_delete_and_rename_rejected, test_path_safety,
       test_repo_root_anchoring, test_autocommit_refuses_secrets,
       test_run_timeout_kills_group, test_dangerous_command_verdicts,
       test_git_dir_case_insensitive, test_update_pending_snooze]

if __name__ == "__main__":
    for t in ALL:
        t()
    print()
    if FAILED:
        print(f"FAILED {len(FAILED)}/{len(ALL)}: {', '.join(FAILED)}")
        sys.exit(1)
    print(f"all {len(ALL)} checks passed")
