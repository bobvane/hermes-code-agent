#!/usr/bin/env python3
"""hca_gate.py — hermes-code-agent verify-loop CLI

The "punch clock" of the verify loop. Rules that a model might forget
become commands that always run. Exit-code semantics:

    exit 0  → green
    exit !=0 → red / blocked

Subcommands:
    detect              Print detected test/lint/build commands for this repo
    snapshot            Create a reversible git snapshot; prints snapshot id
    quickcheck [files]  Fast per-file syntax gate (+ format when available)
    verify [--max-chars N]  Run full test suite; output trimmed to error lines
    state [show|reset|bump KEY]  Loop counters (.hca_state.json)
    plancheck           Verify plan/build separation: fail if source changed in PLAN
    doomcheck TAG       Doom-loop detection: same TAG 3x in a row → exit 2
    apply < patch.diff  Codex apply-patch port: seek_sequence 4-level match,
                        atomic per-file write, structured errors on failure

    update-check        Check GitHub for newer release (throttled 72h by default)
    update-pending      Non-empty output = there is a pending upgrade to offer
    update-status       Show version, throttle pointers, pending info
    update-apply [--version TAG]  Download & overwrite skill; skill_state.json exempt

Exit codes: 0 green · 1 red/blocked · 2 doom stop

Stdlib only. No third-party dependencies. Python 3.8+.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

STATE_FILE = ".hca_state.json"
DOOM_THRESHOLD = 3
MAX_VERIFY_CHARS_DEFAULT = 2000

# Paths autocommit must never stage (the skill's own hard rule: never commit
# secrets). Deliberately narrow — a false positive only means the agent must
# commit that file explicitly; a false negative leaks a key into git history.
SECRET_PATH_RE = re.compile(
    r"(^|/)(\.env(\.[^/]+)?|\.git-credentials|\.netrc|id_rsa|id_ed25519)$"
    r"|\.(pem|key|p12|pfx|keystore|jks)$"
    r"|(^|/)[^/]*(secret|credential|apikey|api[_-]?key)[^/]*"
    r"\.(json|ya?ml|txt|env|ini|toml)$",
    re.IGNORECASE)


# ---------------------------------------------------------------- utilities

def run(cmd, timeout=300):
    """Run a command in its own process group; return (returncode, output).
    On timeout the whole process GROUP is killed — we keep the Popen handle so
    we have a real pid to killpg (subprocess.run's TimeoutExpired carries no
    pid, so the v1.8.1 code below could never fire). Defends against a hung
    child/impl that forked subprocesses."""
    import signal
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True,
                             start_new_session=True)
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    try:
        out, err = p.communicate(timeout=timeout)
        return p.returncode, (out or "") + (err or "")
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, AttributeError,
                OSError):
            # Windows/odd platform: fall back to killing the leader only
            p.kill()
        try:
            p.communicate(timeout=5)   # reap, don't leave a zombie
        except Exception:
            pass
        return 124, f"timeout after {timeout}s: {' '.join(cmd)}"


def fail(msg):
    print(f"[HCA-GATE-RED] {msg}")
    sys.exit(1)


def repo_root() -> Path:
    """Repository root — git toplevel when inside a work tree, else cwd.
    Path validation must be anchored to the REPO, not to wherever the model
    happened to `cd` (a subdir run must not shrink the allowed write area)."""
    rc, out = run(["git", "rev-parse", "--show-toplevel"], timeout=10)
    if rc == 0 and out.strip():
        return Path(out.strip()).resolve()
    return Path.cwd().resolve()


def safe_repo_path(raw_path: str) -> Path:
    """Resolve and validate a patch path stays inside the repository.
    Rejects absolute paths, .. traversal, symlinks escaping repo, .git/, and
    protected state files. Raises ApplyPatchError on violation."""
    root = repo_root()
    candidate = (root / raw_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ApplyPatchError(
            "path", f"path escapes repository: {raw_path}")
    if candidate == root:
        raise ApplyPatchError("path", "cannot modify repository root")
    if ".git" in candidate.parts:
        raise ApplyPatchError("path", f"cannot modify .git internals: {raw_path}")
    if candidate.name in {STATE_FILE, "skill_state.json"}:
        raise ApplyPatchError("path", f"protected state file: {raw_path}")
    return candidate


# ------------------------------------------------- apply (Codex apply-patch port)
# Verbatim port of Codex codex-rs/apply-patch: seek_sequence four-level
# matching, defensive hunk parsing, structured errors, atomic application.

import unicodedata as _unicodedata


class ApplyPatchError(Exception):
    """Structured patch failure (Codex ApplyPatchError): distinguishes IO vs
    match errors and carries the hunk index + expected-vs-actual context so
    the model can self-heal on the next attempt."""

    def __init__(self, kind, message, hunk=None, expected=None, actual=None):
        self.kind = kind          # "io" | "parse" | "match"
        self.message = message
        self.hunk = hunk          # 1-based hunk index, None = whole patch
        self.expected = expected  # list[str] lines the patch looked for
        self.actual = actual      # list[str] lines actually at the location
        super().__init__(self.render())

    def render(self):
        parts = [f"[{self.kind.upper()}] {self.message}"]
        if self.hunk is not None:
            parts.append(f"hunk #{self.hunk}")
        if self.expected is not None:
            parts.append("expected:\n" + "\n".join(f"  | {l}" for l in self.expected[:8]))
        if self.actual is not None:
            parts.append("actually there:\n" + "\n".join(f"  | {l}" for l in self.actual[:8]))
        return "\n".join(parts)


def _seek_sequence(lines, pattern):
    """Codex seek_sequence.rs verbatim: locate `pattern` (list[str]) inside
    `lines` (list[str]). Four progressive levels — never skip a level:
      L1 exact · L2 rstrip (trailing ws) · L3 trim both sides ·
      L4 Unicode-normalized (curly quotes/dashes → ASCII)
    Returns the starting line index of the FIRST match at the loosest level
    that finds one, preferring matches near EOF for end-of-file anchors.
    Returns None when all four levels fail."""
    n, m = len(lines), len(pattern)
    if m == 0 or m > n:
        return None

    def norm(s):
        # L4 normalization: NFKC + typographic punctuation folded to ASCII
        s = _unicodedata.normalize("NFKC", s)
        table = str.maketrans({
            "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
            "\u2013": "-", "\u2014": "-", "\u2026": "...",
            "\u00a0": " ", "\u200b": "",
        })
        return s.translate(table)

    variants = [
        [ln for ln in pattern],                                  # L1 exact
        [ln.rstrip() for ln in pattern],                         # L2 rstrip
        [ln.strip() for ln in pattern],                          # L3 trim
        [norm(ln).strip() for ln in pattern],                    # L4 unicode
    ]
    targets = [
        list(lines),
        [ln.rstrip() for ln in lines],
        [ln.strip() for ln in lines],
        [norm(ln).strip() for ln in lines],
    ]
    for level in range(4):
        pat = variants[level]
        hay = targets[level]
        # scan from the END first: EOF-anchored patches prefer tail matches
        found = None
        for i in range(n - m, -1, -1):
            if hay[i:i + m] == pat:
                found = i
                break
        if found is not None:
            return found
    return None


_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_patch(patch_text):
    """Defensive patch parser (Codex parser.rs semantics, adapted to our
    unified-diff input): split into per-file blocks; each block is a list of
    hunks; each hunk = {"old": [...], "new": [...], "context_before": [...]}.
    Malformed input raises ApplyPatchError('parse', ...) — never crashes."""
    blocks = []
    cur = None
    for raw in patch_text.splitlines():
        # Unsupported diff semantics: reject explicitly instead of letting
        # them fall through to a confusing [PATH]/"no parseable blocks" error.
        if raw.startswith(("rename from ", "rename to ")):
            raise ApplyPatchError(
                "parse", "rename patches are not supported by apply "
                         "(use `git mv` + a normal modify patch)")
        if raw.startswith("deleted file mode"):
            raise ApplyPatchError(
                "parse", "delete-file patches are not supported by apply "
                         "(use `git rm` or the shell)")
        if raw.startswith("GIT binary patch"):
            raise ApplyPatchError(
                "parse", "binary patches are not supported by apply")
        m = re.match(r"\+\+\+ (?:b/)?(\S+)", raw)
        if m and not raw.startswith("---"):
            if m.group(1) == "/dev/null":
                raise ApplyPatchError(
                    "parse", "delete-file patches are not supported by apply "
                             "(use `git rm` or the shell)")
            cur = {"path": m.group(1), "lines": []}
            blocks.append(cur)
            continue
        if cur is not None:
            if raw.startswith(("diff --git",)) or (
                    raw.startswith("--- ") and not raw.startswith("--- \t")):
                cur = None
                continue
            cur["lines"].append(raw)
    if not blocks:
        raise ApplyPatchError("parse", "no parseable file blocks in patch")
    for b in blocks:
        hunks, old, new = [], [], []
        saw_header = False
        for ln in b["lines"]:
            hm = _HUNK_HEADER.match(ln)
            if hm:
                if old or new:
                    hunks.append({"old": old, "new": new})
                old, new = [], []
                saw_header = True
                continue
            if not saw_header and ln.startswith(("-", "+")) and not ln.startswith(("---", "+++")):
                pass  # tolerate missing @@ headers: treat as single hunk
            if ln.startswith("+") and not ln.startswith("+++"):
                new.append(ln[1:])
            elif ln.startswith("-") and not ln.startswith("---"):
                old.append(ln[1:])
            elif ln.startswith(" "):
                old.append(ln[1:])
                new.append(ln[1:])
            elif ln.startswith("\\"):
                continue  # "\ No newline at end of file"
            else:
                raise ApplyPatchError(
                    "parse", f"malformed diff line in {b['path']}: {ln[:40]!r}")
        if old or new:
            hunks.append({"old": old, "new": new})
        if not hunks:
            raise ApplyPatchError("parse",
                                  f"file block {b['path']} has no hunks")
        b["hunks"] = hunks
    return blocks


def apply_seek_patch_file(path, hunks, base_text=None):
    """Apply parsed hunks to ONE file via seek_sequence. All hunks must land
    or nothing is produced (Codex atomicity). Raises ApplyPatchError on the
    first failing hunk with expected/actual context.
    Returns the new content as string (does NOT write) — caller commits.
    `base_text` lets the caller chain several blocks that touch the same file
    (None = read the file from disk)."""
    safe_path = safe_repo_path(path)
    if base_text is None:
        if safe_path.exists():
            try:
                base_text = safe_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raise ApplyPatchError(
                    "io", f"binary file not supported by apply: {path}")
            except OSError as e:
                raise ApplyPatchError("io", f"cannot read {path}: {e}")
        else:
            base_text = ""
    lines = base_text.splitlines()
    # apply bottom-up so earlier indices stay valid after splices
    resolved = []
    for idx, h in enumerate(hunks, start=1):
        pos = _seek_sequence(lines, h["old"]) if h["old"] else len(lines)
        if pos is None:
            # structured error with expected-vs-actual rescue context
            probe = _locate_best_span(lines, h["old"] or [""])
            actual = lines[probe[1]:probe[2]] if probe else \
                lines[max(0, len(lines) - 6):]
            raise ApplyPatchError(
                "match", f"context not found in {path}", hunk=idx,
                expected=h["old"], actual=actual)
        resolved.append((pos, h))
    for pos, h in sorted(resolved, key=lambda t: -t[0]):
        if h["old"]:
            lines[pos:pos + len(h["old"])] = h["new"]
        else:
            lines[pos:pos] = h["new"]
    return "\n".join(lines) + ("\n" if lines else "")


def cmd_apply(args):
    """Codex-style tolerant patch application (apply-patch module port).
    Parse → seek_sequence 4-level match → transactional commit.
    On ANY failure: print the structured error (which hunk, expected vs
    actually-there) so the model can fix the patch and retry — exit 1.
    Phase 1 validates every block in memory (same-file blocks chain off the
    previous block's result, not the stale disk copy). Phase 2 commits every
    file and rolls back all of them if any write fails."""
    patch_text = Path(args.patch_file).read_text(encoding="utf-8") \
        if args.patch_file else sys.stdin.read()
    try:
        blocks = parse_patch(patch_text)
    except ApplyPatchError as e:
        print(f"[HCA-GATE-RED]\n{e.render()}")
        print("[HCA-GATE] Fix the patch format and re-submit.")
        sys.exit(1)

    # Phase 1 — validate in memory. `working` carries the evolving content so
    # a second block for the same file builds on the first block's result.
    working = {}
    for b in blocks:
        try:
            working[b["path"]] = apply_seek_patch_file(
                b["path"], b["hunks"], working.get(b["path"]))
        except ApplyPatchError as e:
            print(f"[HCA-GATE-RED]\n{e.render()}")
            print("[HCA-GATE] PATCH channel: feed this error back, adjust "
                  "the patch (run `locate <file>` for fuzzy rescue), "
                  "re-submit. No files were modified.")
            sys.exit(1)

    # Phase 2 — commit all files as one transaction. A failure at file N
    # restores files 1..N-1 from the in-memory originals (and removes files
    # that did not exist before), so the tree is never left half-applied.
    applied = []          # [(safe_path, original_bytes | None)]
    try:
        for path, content in working.items():
            safe_path = safe_repo_path(path)
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(safe_path.parent),
                prefix=safe_path.name + ".", suffix=".hca")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(content)
                    fh.flush()
                    os.fsync(fh.fileno())
                applied.append((safe_path,
                                safe_path.read_bytes()
                                if safe_path.exists() else None))
                os.replace(tmp_name, safe_path)
            except OSError:
                Path(tmp_name).unlink(missing_ok=True)
                raise
    except OSError as e:
        restores = []
        for p, original in applied:
            try:
                if original is None:
                    p.unlink(missing_ok=True)
                else:
                    p.write_bytes(original)
                restores.append(p.name)
            except OSError:
                pass
        print(f"[HCA-GATE-RED]\n[IO] commit failed: {e}")
        print(f"[HCA-GATE] ROLLED BACK {len(restores)} file(s) "
              f"({', '.join(restores)}) — the tree is unchanged. Cause is "
              "environmental (permissions / disk), not the patch.")
        sys.exit(1)

    for path in working:
        print(f"  ok  {path} ({len(working[path].splitlines())} line(s), "
              "seek_sequence)")
    ok(f"patch applied atomically to {len(working)} file(s)")


# ----------------------------------------------------------------- repo map

REPO_MAP_MAX_FILES = 400
REPO_MAP_TOP = 40          # files listed, ranked by symbol hits
REPO_MAP_SYMBOLS_PER_FILE = 8

PY_DEF = re.compile(
    r"^(?:\s*)(?:async\s+)?def\s+([A-Za-z_]\w*)"
    r"|^(?:class)\s+([A-Za-z_]\w*)")


def cmd_repomap(_args):
    """Aider-style lightweight repo map: rank source files by definition
    count (grep-based symbol sort), list top files with their defs.
    Pure stdlib walk — no tree-sitter, no networkx. Deterministic order."""
    import collections
    exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
            ".sh", ".rb", ".php", ".c", ".h", ".cpp", ".hpp"}
    skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__",
                 "dist", "build", ".pytest_cache", ".mypy_cache"}
    pat = re.compile(
        r"^\s*(?:(?:async\s+)?def|class|func|fn|function|export\s+function"
        r"|sub)\s+([A-Za-z_]\w*)")
    counts = {}
    defs = {}
    nfiles = 0
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if os.path.splitext(f)[1] not in exts:
                continue
            path = os.path.relpath(os.path.join(root, f))
            nfiles += 1
            if nfiles > REPO_MAP_MAX_FILES:
                continue
            syms = []
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        m = pat.match(line)
                        if m:
                            syms.append(m.group(1))
                            if len(syms) >= REPO_MAP_SYMBOLS_PER_FILE * 4:
                                break
            except OSError:
                continue
            if syms:
                counts[path] = len(syms)
                # deterministic: keep first-seen then sort alphabetically
                defs[path] = sorted(set(syms))[:REPO_MAP_SYMBOLS_PER_FILE]
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if not ranked:
        ok("repo map: no indexed source files")
        return
    print(f"[HCA-GATE] repo map — {len(ranked)} files with symbols "
          f"(scanned {nfiles}), top {min(REPO_MAP_TOP, len(ranked))}:")
    if nfiles > REPO_MAP_MAX_FILES:
        print(f"[HCA-GATE] WARNING: truncated at {REPO_MAP_MAX_FILES} files "
              f"({nfiles} source files present) — the map is NOT complete. "
              "List the relevant directory yourself if the target is missing.")
    for path, cnt in ranked[:REPO_MAP_TOP]:
        print(f"  {path} ({cnt})  {', '.join(defs[path])}")
    print("[HCA-GATE] use: read the most relevant file directly; "
          "do NOT dump the whole map into context")


def hard_stop(msg):
    """Exit-2 circuit breaker (budget/doom family). OpenCode MAX_STEPS
    close-out protocol: a hard stop is never silent — the agent must end
    with a structured wrap-up, not just die."""
    print(f"[HCA-GATE-BUDGET] {msg}")
    print("""[HCA-GATE] MAX LIMIT REACHED — close-out required. Tools are done for this approach.
STRICT REQUIREMENTS:
1. Do NOT make any further edits or tool calls on this task.
2. Respond with TEXT ONLY, structured as:
   - DONE: what was accomplished so far (with green checkpoints if any)
   - NOT DONE: remaining tasks that were not completed
   - NEXT: concrete recommendation (switch strategy / stronger model / revert)
Any attempt to keep editing past this line is a critical violation.""")
    sys.exit(2)


def ok(msg):
    print(f"[HCA-GATE-GREEN] {msg}")
    sys.exit(0)


def load_state():
    p = Path(STATE_FILE)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"steps": 0, "redfix": {}, "doom": [], "git_head": None,
            "snapshots": []}


def save_state(st):
    Path(STATE_FILE).write_text(
        json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def current_head():
    rc, out = run(["git", "rev-parse", "HEAD"], timeout=10)
    return out.strip() if rc == 0 else None


def state_stale(st):
    """State is stale if recorded HEAD no longer matches (rebase/branch switch)."""
    head = current_head()
    return st.get("git_head") is not None and head is not None \
        and st["git_head"] != head


# ------------------------------------------------------------------ detect

PY_TEST = [["python", "-m", "pytest", "-q"], ["python3", "-m", "pytest", "-q"]]
JS_TEST = [["npx", "vitest", "run"], ["npm", "test", "--silent"]]


def detect_commands():
    cmds = {"test": [], "lint": [], "format": [], "quickcheck": []}
    has = lambda f: Path(f).exists()

    # Python project?
    py = any(has(f) for f in ("pyproject.toml", "setup.py", "setup.cfg",
                              "requirements.txt"))
    tests_dir = Path("tests").is_dir() or list(Path().glob("test_*.py")) \
        or list(Path("tests").glob("test_*.py") if Path("tests").is_dir() else [])
    if py and tests_dir:
        # prefer project venv python first (avoids FileNotFoundError noise
        # when system python lacks the runner — found in v1.5.0 bench round)
        candidates = []
        for vpy in (".venv/bin/python", "venv/bin/python"):
            if has(vpy):
                candidates.append([vpy, "-m", "pytest", "-q"])
        candidates.extend(PY_TEST)
        for c in candidates:
            rc, _ = run(c + ["--co", "-q"], timeout=60)
            if rc == 0:  # only accept a runner that actually works
                cmds["test"].append(" ".join(c))
                break
        if has(".ruff.toml") or has("ruff.toml") or py:
            cmds["format"].append("ruff format .")
            cmds["quickcheck"].append(
                "python -m py_compile <file>")
    # JS/TS project?
    if has("package.json"):
        try:
            pkg = json.loads(Path("package.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pkg = {}
        scripts = pkg.get("scripts", {})
        if "test" in scripts and " ".join(JS_TEST[0]) not in cmds["test"]:
            cmds["test"].append("npm test")
        if "lint" in scripts:
            cmds["lint"].append("npm run lint")
        cmds["quickcheck"].append("npx tsc --noEmit <file>")
        cmds["format"].append("npx prettier --write <file>")
    # Go project?
    if has("go.mod"):
        cmds["test"].append("go test ./...")
        cmds["quickcheck"].append("go vet ./...")
        cmds["format"].append("gofmt -w .")
    # Rust project?
    if has("Cargo.toml"):
        cmds["test"].append("cargo test --quiet")
        cmds["quickcheck"].append("cargo clippy --quiet")
        cmds["format"].append("cargo fmt")
    return cmds


def cmd_detect(_args):
    cmds = detect_commands()
    if not any(cmds.values()):
        print("[HCA-GATE] No recognizable project markers "
              "(pyproject/package.json/go.mod/Cargo.toml). "
              "Ask the user how to verify.")
        print(f"[HCA-GATE] FIX (if you just need a runner): {runner_fix_hint()}")
        sys.exit(1)
    print("[HCA-GATE] detected commands (review before running — "
          "project scripts run with the agent's privileges):")
    for kind, items in cmds.items():
        for it in items:
            print(f"  {kind}: {it}")
    print("[HCA-GATE] TIP: project scripts come from the repo. For "
          "untrusted repos, read the script first or run in a sandbox.")
    ok("detection complete")


# ---------------------------------------------------------------- snapshot

def cmd_snapshot(args):
    if current_head() is None:
        rc, out = run(["git", "init"])
        if rc != 0:
            fail(f"not a git repo and git init failed: {out.strip()}")
        run(["git", "add", "-A"])
        run(["git", "-c", "user.email=hca@local",
             "-c", "user.name=hca", "commit", "-m", "hca snapshot base"])
    # Cline-style transactional checkpoint: stash commit + untracked files
    # written into a synthetic 2nd-parent tree, stored under a private ref so
    # the snapshot survives later resets AND can be rolled back atomically.
    rc, out = run(["git", "stash", "create"])
    snap = out.strip()
    if snap:
        # capture untracked files into a tree for the transaction parent
        rc_o, others = run(["git", "ls-files", "--others",
                            "--exclude-standard"])
        untracked_tree = None
        if others.strip():
            run(["git", "add", "-A"])
            rc_t, out_t = run(["git", "write-tree"])
            if rc_t == 0:
                untracked_tree = out_t.strip()
            run(["git", "reset"])  # undo index pollution, keep worktree
        if untracked_tree:
            rc_c, commit_out = run([
                "git", "commit-tree", untracked_tree,
                "-p", snap, "-m", "hca: untracked companion"])
            if rc_c == 0:
                snap = commit_out.strip()
    else:  # nothing dirty: use HEAD as the snapshot point
        snap = current_head()
    ref = f"refs/hca/snapshots/{snap[:12]}"
    run(["git", "update-ref", ref, snap])
    st = load_state()
    if state_stale(st):
        st = {"steps": 0, "redfix": {}, "doom": [],
              "git_head": current_head(), "snapshots": []}
    st.setdefault("snapshots", []).append({"id": snap, "ref": ref})
    st["git_head"] = current_head()
    save_state(st)
    ok(f"snapshot {snap[:12]} recorded (ref={ref}, "
       f"{len(st['snapshots'])} total)")


def cmd_restore(args):
    """Transactional restore with QA gate: verify clean status after."""
    st = load_state()
    snaps = st.get("snapshots") or []
    target = args.snapshot
    if not snaps:
        fail("no snapshots recorded — nothing to restore")
    entry = snaps[-1] if isinstance(snaps[-1], dict) else {"id": snaps[-1]}
    if target in ("last", ""):
        chosen = entry
    else:  # match by id prefix
        matches = [s for s in snaps
                   if isinstance(s, dict) and s["id"].startswith(target)]
        matches += [({"id": s, "ref": None}) for s in snaps
                    if isinstance(s, str) and s.startswith(target)]
        if not matches:
            fail(f"no snapshot matching '{target}'")
        chosen = matches[0]
    sid, ref = chosen["id"], chosen.get("ref")
    if ref:
        rc_r, resolved = run(["git", "rev-parse", "--verify", ref])
        if rc_r == 0:
            sid = resolved.strip()
    # restore worktree + index from the snapshot, keep current HEAD history
    rc, out = run(["git", "restore", "--source", sid,
                   "--worktree", "--staged", "."])
    if rc != 0:
        fail(f"restore failed: {out.strip()}")
    # remove files created after the snapshot (Cline semantics: restore
    # returns tree to the exact snapshot state, including untracked files)
    rc_ls, known = run(["git", "ls-tree", "-r", "--name-only", sid])
    known_set = set(known.splitlines())
    st_status, status_out = run(["git", "status", "--porcelain"])
    dirty = []
    for ln in status_out.splitlines():
        if not ln.strip():
            continue
        path = ln[3:].strip().strip('"')
        if ln.startswith("??") and path != ".hca_state.json" \
                and path not in known_set:
            Path(path).unlink(missing_ok=True)  # post-snapshot junk file
        else:
            dirty.append(ln)
    if dirty:
        print("[HCA-GATE] WARNING: worktree not fully clean after restore:")
        for ln in dirty[:10]:
            print(f"  {ln}")
    st["restored_from"] = sid
    save_state(st)
    ok(f"restored to {sid[:12]}"
       + (" (with warnings)" if dirty else " — clean"))


# --------------------------------------------------------------- quickcheck

QUICK_BY_EXT = {
    ".py": ["python", "-m", "py_compile"],
    ".ts": ["npx", "tsc", "--noEmit"],
    ".tsx": ["npx", "tsc", "--noEmit"],
}


def cmd_quickcheck(args):
    files = args.files or []
    if not files:
        exts = ("*.py", "*.ts")
        files = [str(p) for pat in exts for p in Path().rglob(pat)
                 if "node_modules" not in str(p) and ".venv" not in str(p)][:20]
    if not files:
        ok("no checkable files")
    bad = []
    for f in files:
        checker = QUICK_BY_EXT.get(Path(f).suffix)
        if not checker:
            continue
        rc, out = run(checker + [f], timeout=120)
        if rc != 0:
            bad.append((f, out.strip()[-500:]))
    if bad:
        for f, out in bad:
            print(f"[RED] {f}\n{out}\n")
        fail(f"{len(bad)} file(s) failed quick syntax gate — fix before VERIFY")
    ok(f"{len(files)} file(s) passed quick syntax gate")


# ------------------------------------------------------------- budget (Codex)

BUDGET_STEPS_SOFT = 4      # warn at step 4 of 5
BUDGET_TOKENS_TIERS = [    # Codex-style multi-tier soft reminders (deduped)
    # fixed templates, each fires ONCE per level; the 8k tier carries a
    # progress-saving directive ported from Codex's context_window_reminder
    (3000, "context is getting heavy — prefer targeted reads"),
    (8000, "heavy context: BEFORE continuing, write a short progress note "
           "(completed steps / current step / next action) into your working "
           "notes, then summarize completed steps and drop old tool output"),
]
BUDGET_TOKENS_HARD = 15000     # cumulative verify-digest tokens → hard stop
BUDGET_RED_CYCLES_HARD = 5     # red cycles before hard stop


def budget_hard_stop(st):
    """v1.7.0 overspend circuit breaker: cumulative verify digest tokens or
    red-cycle count past the cap → exit-2 stop with an escalate-to-stronger-
    model suggestion. Returns the reason string or None."""
    spent = sum(t for t in (st.get("tokens_verify") or [])
                if isinstance(t, int))
    n = (st.get("redfix") or {}).get("verify", 0)
    if spent >= BUDGET_TOKENS_HARD:
        return (f"verify digests have cost ~{spent} tok this task "
                f"(cap {BUDGET_TOKENS_HARD})")
    if n >= BUDGET_RED_CYCLES_HARD:
        return f"red cycle #{n} reached the cap ({BUDGET_RED_CYCLES_HARD})"
    return None


def budget_escalation_hint():
    """User-facing advice appended to any hard stop: this model has burned
    its budget without converging — suggest handing off. Two short lines
    (中文 + English), ANSI red so it stands out in the Hermes TUI."""
    R = "\033[1;31m"
    X = "\033[0m"
    return (
        f"{R}⛔ 此模型不胜任此编程任务，建议更换更强模型。{X}\n"
        f"{R}⛔ This model is unfit for this coding task — switch to a "
        f"stronger model.{X}")


def budget_reminder(st):
    """Codex rollout_budget port: tiered soft warnings, deduped per level."""
    fired = st.setdefault("budget_fired", [])
    msgs = []
    steps = st.get("steps", 0)
    if steps >= BUDGET_STEPS_SOFT and "steps" not in fired:
        fired.append("steps")
        msgs.append(f"step {steps}/5 — plan the finish, avoid new scope")
    spent = sum(st.get("tokens_verify") or [])
    for tier, msg in BUDGET_TOKENS_TIERS:
        if spent >= tier and f"tok{tier}" not in fired:
            fired.append(f"tok{tier}")
            msgs.append(msg)
    save_state(st)
    return (" — " + "; ".join(msgs)) if msgs else ""


# ------------------------------------------------------------------- verify

NOISE_PATTERNS = re.compile(
    r"^\.|^\s*$|^Warning: |^Deprecated", re.MULTILINE)


def failure_fingerprint(pytest_output):
    """Hash the SET of failing test ids from pytest output. Order- and
    count-insensitive; returns None when no test ids are parseable (e.g.
    collection errors), so non-test failures never trigger semantic doom."""
    ids = sorted({m.split()[0] for m in
                  re.findall(r"FAILED\s+(\S+)", pytest_output)})
    if not ids:
        return None
    return hashlib.sha1(" ".join(ids).encode()).hexdigest()[:12]


def trim_output(text, max_chars):
    """Pi-style double-limit digest: keep failure-relevant lines, cap by
    line count (200) AND bytes (max_chars). Never returns a half line."""
    MAX_LINES = 200
    lines = [ln for ln in text.splitlines()
             if re.search(r"(FAILED|ERROR|Error|error|assert|Exception|✗|×)",
                          ln)]
    out_lines, used = [], 0
    for ln in lines[:MAX_LINES]:
        if used + len(ln) + 1 > max_chars:
            out_lines.append("...[truncated %d more error lines]"
                             % (len(lines) - len(out_lines)))
            break
        out_lines.append(ln)
        used += len(ln) + 1
    trimmed = "\n".join(out_lines)
    if not trimmed and text.strip():
        # no failure-pattern lines: fall back to tail so red is never silent
        tail = text.strip().splitlines()[-10:]
        trimmed = "\n".join(tail)[-max_chars:]
        if len(trimmed) >= max_chars:
            trimmed = trimmed[:max_chars - len("[overflow compressed]")] \
                + "[overflow compressed]"
    # ⑦ overflow forced deterministic compression: even after filtering,
    # a pathological output (e.g. one 10k-char line) must never exceed the
    # hard cap. Deterministic middle-cut, no LLM, no randomness.
    if len(trimmed) > max_chars:
        marker = "...[overflow compressed]..."
        keep = max_chars - len(marker) - 2
        head = keep * 2 // 3
        tailn = max(keep - head, 0)
        trimmed = trimmed[:head] + "\n" + marker + "\n" + trimmed[-tailn:] \
            if tailn else trimmed[:head] + "\n" + marker
    return trimmed


def estimate_tokens(text):
    """Rough token proxy (~chars/3.5 for mixed CJK/ASCII). For cost telemetry."""
    return max(1, round(len(text) / 3.5))


def venv_python_hint():
    """Return a concrete fix command if a project-local venv has the runner."""
    for py in (".venv/bin/python", "venv/bin/python"):
        p = Path(py)
        if p.exists():
            return f"{py} -m pytest -q"
    return None


def runner_fix_hint():
    """One concrete install line for when no test runner is available.
    Reachable from the 'no test command detected' fail path too — that is the
    case that actually needs it."""
    hint = venv_python_hint()
    if hint:
        py = hint.split()[0]
        return (f"install the runner: `{py} -m ensurepip --upgrade && "
                f"{py} -m pip install pytest`")
    return "create a runner: `uv venv .venv && uv pip install pytest`"


def cmd_verify(args):
    cmds = detect_commands()["test"]
    if not cmds:
        st = load_state()
        reminder = budget_reminder(st)  # fire soft warnings even on early RED
        print("[HCA-GATE] no test command detected (no project markers + no "
              "working runner). Look for the tests yourself: tests/ dir, "
              "test_*.py, package.json scripts, Makefile targets.")
        print(f"[HCA-GATE] FIX: {runner_fix_hint()}")
        fail("do NOT fake green" + reminder)
    failures = []
    unavailable = []
    last_out = ""
    for c in cmds:
        print(f"$ {c}")
        rc, out = run(c.split(), timeout=180)
        last_out = out
        print(out[-1500:] if rc != 0 else
              ("PASS" if rc == 0 else out[-800:]))
        if rc == 127 or "No module named" in out:
            # tool itself missing: not a test failure — skip, don't count red
            unavailable.append(c)
            continue
        if rc != 0:
            failures.append((c, trim_output(out, args.max_chars)))
    if unavailable and not failures:
        print("[HCA-GATE] test runner(s) unavailable: "
              + ", ".join(unavailable))
        hint = venv_python_hint()
        if hint:
            rc2, out2 = run(hint.split(), timeout=600)
            if rc2 == 0:
                st = load_state()
                st["git_head"] = current_head()
                save_state(st)
                ok(f"full verify passed (via project venv: {hint})")
            if rc2 != 127 and "No module named" not in out2:
                print(f"[HCA-GATE] retried with `{hint}` → "
                      + ("FAILED, digest below" if rc2 != 0 else "PASS"))
                if rc2 != 0:
                    failures.append((hint, trim_output(out2, args.max_chars)))
            if not failures:
                print(f"[HCA-GATE] FIX: install the runner, e.g.\n"
                      f"  {hint.split()[0]} -m ensurepip --upgrade\n"
                      f"  or: uv pip install pytest   (then re-run verify)")
        else:
            print("[HCA-GATE] FIX: no .venv found. Create one and install "
                  "the runner:\n"
                  "  uv venv .venv && uv pip install pytest\n"
                  "  then re-run verify (it will auto-use .venv/bin/python)")
        if not failures:
            fail("cannot run verification — install the runner first; "
                 "do NOT fake green")
    if failures:
        digests = [(c, trimmed) for c, trimmed in failures]
        for c, trimmed in digests:
            print(f"\n[VERIFY-RED] `{c}` failed. Error digest "
                  f"(~{estimate_tokens(trimmed)} tok):\n{trimmed}")
        # record red cycle in state + cost telemetry
        st = load_state()
        if state_stale(st):
            st = load_state() | {"git_head": current_head()}
        key = "verify"
        rf = st.get("redfix") or {}
        rf[key] = rf.get(key, 0) + 1
        st["redfix"] = rf
        tv = [t for t in (st.get("tokens_verify") or []) if isinstance(t, int)]
        # record the digest actually shown to the agent (post-trim), so
        # telemetry matches what the model paid to read — not raw output.
        shown = "\n".join(d for _, d in digests)
        tv.append(estimate_tokens(shown))
        st["tokens_verify"] = tv[-20:]  # compaction: keep telemetry lean

        # --- semantic doom: same failure SET repeatedly → hard stop ---
        # (found in v1.5.1 bench: model patched the same commit-path bug
        #  5 rounds straight; action-tag doomcheck can't see this because
        #  each edit is a different tag. Fingerprint the failing tests.)
        fp = failure_fingerprint(last_out)
        if fp:
            hist = [f for f in (st.get("fail_fp") or [])
                    if isinstance(f, str)][-DOOM_THRESHOLD:]
            hist.append(fp)
            st["fail_fp"] = hist[-DOOM_THRESHOLD:]
            semantic_doom = (len(st["fail_fp"]) == DOOM_THRESHOLD
                             and len(set(st["fail_fp"])) == 1)
        else:
            semantic_doom = False
        st["git_head"] = current_head()
        save_state(st)
        if semantic_doom:
            print("[HCA-GATE-DOOM] Same failure set repeated "
                  f"{DOOM_THRESHOLD}x in a row — you are in a blind-patch "
                  "loop. The failing tests did not change across your last "
                  f"{DOOM_THRESHOLD} fixes.")
            print("Required: STOP patching. Either revert to the last "
                  "snapshot (hca_gate.py snapshot shows ids) and take a "
                  "DIFFERENT approach, or report this as a blocker with "
                  "your diagnosis of why the fix never lands.")
            sys.exit(2)
        n = st["redfix"][key]
        stop_reason = budget_hard_stop(st)
        if stop_reason:
            print(budget_escalation_hint())
            hard_stop(f"{stop_reason} — STOP, report the blocker "
                      "(see budget suggestion above)")
        extra = budget_reminder(st)
        fail(f"verify failed (red cycle #{n}{extra})")
    st = load_state()
    st["git_head"] = current_head()
    save_state(st)
    print("[HCA-GATE-GREEN] full verify passed")
    autocommit(st)
    sys.exit(0)


# ------------------------------------------------------- auto-commit (Aider)

def autocommit(st):
    """Aider-style auto-commit: after a green verify, land every working-tree
    change as a checkpoint commit so each green round is durable and
    revertible. Best-effort: no git repo / nothing to commit / git failure
    are all silent no-ops — never blocks the loop."""
    r = run(["git", "rev-parse", "--is-inside-work-tree"])
    if r[0] != 0 or r[1].strip() != "true":
        return
    dirty = (run(["git", "diff", "--quiet", "--",
                  ":(exclude).hca_state.json"])[0] != 0
             or run(["git", "ls-files", "--others", "--exclude-standard",
                     "--", ":(exclude).hca_state.json"])[1].strip() != "")
    if not dirty:
        return  # clean tree — nothing to land
    add = run(["git", "add", "-A"])
    if add[0] != 0:
        return
    run(["git", "reset", "-q", "--", ".hca_state.json"])
    # Never commit secrets (skill hard rule): unstage sensitive-looking paths
    # that `git add -A` swept in from a project without a matching .gitignore.
    staged = run(["git", "diff", "--cached", "--name-only"])[1].splitlines()
    secrets = [f for f in staged if SECRET_PATH_RE.search(f)]
    if secrets:
        run(["git", "reset", "-q", "--"] + secrets)
        print("[HCA-GATE] WARNING: refused to commit sensitive path(s): "
              + ", ".join(secrets[:5])
              + " — add them to .gitignore, or commit them yourself.")
    if run(["git", "diff", "--cached", "--quiet"])[0] == 0:
        return  # only the state file / secrets changed — nothing to land
    n_red = (st.get("redfix") or {}).get("verify", 0)
    msg = f"hca: green checkpoint (verify pass, red-cycles={n_red})"
    c = run(["git", "commit", "-qm", msg])
    if c[0] == 0:
        st["autocommits"] = (st.get("autocommits") or 0) + 1
        save_state(st)
        print(f"[HCA-GATE] auto-committed checkpoint "
              f"#{st['autocommits']}: {msg}")


# -------------------------------------------------------------------- state

def cmd_state(args):
    st = load_state()
    if args.state_cmd in (None, "show"):
        if state_stale(st):
            print("[HCA-GATE] state is STALE (git head moved) — run: "
                  "hca_gate.py state reset")
            sys.exit(1)
        print(json.dumps(st, ensure_ascii=False, indent=1))
        sys.exit(0)
    if args.state_cmd == "reset":
        save_state({"steps": 0, "redfix": {}, "doom": [],
                    "git_head": current_head(), "snapshots": []})
        ok("state reset")
    if args.state_cmd == "bump":
        st["steps"] = st.get("steps", 0) + 1
        st["git_head"] = current_head()
        save_state(st)
        ok(f"step -> {st['steps']}")
    fail(f"unknown state subcommand: {args.state_cmd}")


# ------------------------------------------------------------------- compact

COMPACT_KEEP = 10  # Gemini-style: preserve the recent tail, split old side


def cmd_compact(_args):
    """Deterministic context compaction (Gemini CLI port).

    Split-point discipline: only 'cut' at clean boundaries — completed steps
    collapse to one status line each; tool outputs are dropped entirely
    (they are reproducible), never half-kept. Failure fallback is pure
    truncation of the oldest entries (no LLM involved, never fails).
    """
    st = load_state()
    changed = []
    snaps = st.get("snapshots") or []
    if len(snaps) > COMPACT_KEEP:
        st["snapshots"] = ([f"compacted:{len(snaps) - COMPACT_KEEP} older"]
                           + snaps[-COMPACT_KEEP:])
        changed.append(f"snapshots {len(snaps)}→{len(st['snapshots'])}")
    tv = st.get("tokens_verify") or []
    if len(tv) > 20:
        st["tokens_verify"] = tv[-20:]
        changed.append("telemetry trimmed")
    rf = st.get("redfix") or {}
    for k in list(rf):
        if rf[k] > 99:
            rf[k] = 99  # sentinel cap; real budget logic lives elsewhere
            changed.append(f"redfix[{k}] capped")
    save_state(st)
    if changed:
        ok("compacted: " + ", ".join(changed))
    else:
        ok("nothing to compact")


# ---------------------------------------------------------------- plancheck

SOURCE_EXTS = {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".rb",
               ".c", ".cpp", ".h", ".sh"}

def cmd_plancheck(_args):
    rc, out = run(["git", "status", "--porcelain"])
    if rc != 0:
        fail("not a git repo — cannot verify plan/build separation")
    violations = [
        ln for ln in out.splitlines()
        if ln.strip() and Path(ln.split(maxsplit=1)[-1].strip()).suffix.lower() in SOURCE_EXTS
    ]
    if violations:
        print("[HCA-GATE-RED] PLAN step must not modify source files. "
              "Violations:")
        for v in violations[:10]:
            print(f"  {v}")
        print("Roll back these changes (git restore) before BUILD.")
        sys.exit(1)
    ok("plan/build separation clean")


# ------------------------------------------------------- locate (Aider port)

def _locate_best_span(source_lines, probe_lines):
    """Per-line fuzzy scoring (no hard threshold — report best candidate +
    its score; the model judges). For each probe line, find the source line
    with the highest char-level similarity (after whitespace-stripping so
    indentation drift never zeroes a match). Returns
    (avg_ratio, lo, hi, per_line) where per_line is a list of
    (probe_idx, src_idx, ratio) for reporting, or None if probe is empty."""
    import difflib
    norm_src = [ln.strip() for ln in source_lines]
    scores = []  # (best_ratio, probe_i, src_j)
    for pi, pline in enumerate(probe_lines):
        p = pline.strip()
        if not p:
            continue
        best, bj = 0.0, -1
        for sj, sline in enumerate(norm_src):
            if abs(len(sline) - len(p)) > max(len(sline), len(p)) * 0.7:
                continue  # cheap length gate before SequenceMatcher
            r = difflib.SequenceMatcher(None, sline, p).ratio()
            if r > best:
                best, bj = r, sj
        scores.append((best, pi, bj))
    if not scores:
        return None
    per_line = [(pi, bj, r) for r, pi, bj in scores]
    hits = [s for s in scores if s[0] > 0.3]
    if not hits:
        # nothing even remotely similar: report the least-bad anchor anyway
        hits = [max(scores)]
    lo = min(h[2] for h in hits if h[2] >= 0)
    hi = max(h[2] for h in hits if h[2] >= 0) + 1
    hi = min(max(hi, lo + len(probe_lines)), len(source_lines))
    avg = sum(h[0] for h in scores) / len(scores)
    return (avg, lo, hi, per_line)


def cmd_locate(args):
    """Aider did-you-mean rescue for failed patches. Give it the file and a
    snippet the patch expected to find; prints 'you looked for vs actually
    there' side-by-side with surrounding context. Read-only — never edits."""
    p = Path(args.file)
    if not p.exists():
        fail(f"file not found: {args.file}")
    text = p.read_text(encoding="utf-8", errors="replace")
    src_lines = text.splitlines()
    # probe: stdin or inline arg; strip diff markers so raw hunk bodies work
    raw = sys.stdin.read() if not args.snippet else args.snippet
    probe_lines = [ln[1:].rstrip() if ln[:1] in "+- " else ln.rstrip()
                   for ln in raw.splitlines()
                   if ln.strip() and not ln.startswith(("---", "+++"))]
    if not probe_lines:
        fail("empty probe — pass a snippet on stdin or as argument")
    hit = _locate_best_span(src_lines, probe_lines)
    if hit is None:
        print("[HCA-GATE] no fuzzy anchor found at all — the target code "
              "may not exist in this file. Re-read the file before patching.")
        sys.exit(1)
    ratio, lo, hi, per_line = hit
    print(f"[HCA-GATE-LOCATE] best region: lines {lo + 1}-{hi} "
          f"(avg similarity {ratio:.0%})")
    for pi, sj, r in per_line:
        where = f"line {sj + 1}" if sj >= 0 else "NO similar line found"
        print(f"  probe[{pi + 1}] {r:.0%} -> {where}")
    ctx_lo, ctx_hi = max(0, lo - 3), min(len(src_lines), hi + 3)
    print("--- context ---")
    for n in range(ctx_lo, ctx_hi):
        marker = ">>" if lo <= n < hi else "  "
        print(f"{marker} {n + 1:4d}| {src_lines[n]}")
    print("--- you looked for (first 8 lines) ---")
    for ln in probe_lines[:8]:
        print(f"   ?| {ln}")
    if ratio < 0.6:
        print("[HCA-GATE] low similarity — likely wrong file or the code "
              "moved. Locate by symbol search instead of blind re-patching.")
    sys.exit(0)  # always exit 0: evidence is delivered, the model judges


# ---------------------------------------------------------------- doomcheck

def cmd_doomcheck(args):
    """Call with a stable tag describing the action, e.g. 'edit:impl_a.py:42'.
    Same tag DOOM_THRESHOLD times in a row → exit 2 (hard stop signal)."""
    tag = hashlib.sha1(args.tag.encode()).hexdigest()[:12]
    st = load_state()
    doom = st.get("doom", [])
    doom.append(tag)
    if len(doom) > DOOM_THRESHOLD:
        doom = doom[-DOOM_THRESHOLD:]
    st["doom"] = doom
    st["git_head"] = current_head()
    save_state(st)
    repeated = len(doom) == DOOM_THRESHOLD and len(set(doom)) == 1
    if repeated:
        print("[HCA-GATE-DOOM] Same action repeated "
              f"{DOOM_THRESHOLD}x in a row. STOP this approach.")
        print("Required: revert to last snapshot "
              "(hca_gate.py snapshot shows ids) OR switch strategy. "
              "Do NOT keep patching the same spot.")
        sys.exit(2)
    ok(f"action logged ({len(doom)}/{DOOM_THRESHOLD})")


# ------------------------------------------------- check_cmd (Codex execpolicy
#                                                   × Gemini shell-utils port)

POLICY_FILE = Path(__file__).resolve().parent / "cmd_policy.yaml"

# Gemini detectBashSubstitution port: quote-aware scan for $(`, backtick,
# and <(/>( process substitution. Escapes respected; single quotes suppress.
def _detect_substitution(command):
    in_single = in_double = False
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            i += 1
            continue
        if in_single:
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            if in_double and command[i + 1] in "$`\"\\\n":
                i += 2
                continue
            if not in_double:
                i += 2
                continue
        if ch == "$" and i + 1 < n and command[i + 1] == "(":
            return "command substitution $()"
        if not in_double and ch in "<>" and i + 1 < n and command[i + 1] == "(":
            return f"process substitution {ch}()"
        if ch == "`":
            return "backtick substitution"
        i += 1
    return None


def _split_segments(command):
    """Split a compound shell command at && || ; | (top-level only — inside
    quotes is data). Each segment is checked independently (both upstreams)."""
    segments, cur = [], []
    in_single = in_double = False
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double and ch in "&;|":
            # consume && / ||
            if i + 1 < n and command[i + 1] == ch:
                i += 1
            segments.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    segments.append("".join(cur))
    return [s.strip() for s in segments if s.strip()]


def _shlex_tokens(segment):
    import shlex as _shlex
    try:
        return _shlex.split(segment)
    except ValueError:
        return segment.split()


def _load_policy():
    """Load the YAML rule table with a stdlib-only mini-parser (no PyYAML
    dependency): reads `default_decision` and flat `{pattern: [...],
    decision: ..., reason: ...}` list items."""
    default, rules = "confirm", []
    if POLICY_FILE.exists():
        for raw in POLICY_FILE.read_text(encoding="utf-8").splitlines():
            ln = raw.split("#", 1)[0].strip()
            if ln.startswith("default_decision:"):
                default = ln.split(":", 1)[1].strip() or default
                continue
            if "- {" not in ln or "pattern:" not in ln:
                continue
            body = ln[ln.index("{") + 1:ln.rindex("}")]
            m_pat = re.search(r"pattern:\s*\[(.*?)\]", body)
            if not m_pat:
                continue
            toks = [t.strip().strip("\"'") for t in m_pat.group(1).split(",")
                    if t.strip()]
            m_dec = re.search(r"decision:\s*(\w+)", body)
            m_rea = re.search(r"reason:\s*(.+)$", body[m_pat.end():]
                              if m_dec else body)
            rules.append({
                "pattern": toks,
                "decision": m_dec.group(1) if m_dec else "confirm",
                "reason": (m_rea.group(1).strip()
                           if m_rea else "matched policy rule"),
            })
    return default, rules


def _check_interpreter_escape(toks):
    """Detect interpreter-eval patterns that bypass the policy table by
    wrapping arbitrary code in an interpreter's `-c` / `--eval` / `-exec`
    arg. Returns the escape kind or None."""
    if len(toks) < 2:
        return None
    interp = toks[0]
    # python, python3, ruby, perl, node, php, lua, bash, sh, zsh
    if interp in {"python", "python3", "python2", "ipython"}:
        for t in toks[1:]:
            if t in {"-c", "-C"}:
                return f"python eval ({t})"
    elif interp in {"ruby", "rb"}:
        for t in toks[1:]:
            if t in {"-e", "--eval"}:
                return f"ruby eval ({t})"
    elif interp == "perl":
        for t in toks[1:]:
            if t in {"-e", "-E"}:
                return f"perl eval ({t})"
    elif interp == "node":
        for t in toks[1:]:
            if t in {"-e", "--eval", "-p", "-pe"}:
                return f"node eval ({t})"
    elif interp in {"php", "php7", "php8"}:
        for t in toks[1:]:
            if t in {"-r", "-R", "-B", "-F", "-E"}:
                return f"php eval ({t})"
    elif interp in {"bash", "sh", "zsh", "dash", "ash"}:
        for t in toks[1:]:
            if t in {"-c", "-i", "-l"} and len(toks) > 2:
                # plain `bash -c "..."` is a direct shell — always confirm
                return f"shell exec ({t})"
    elif interp == "find":
        for t in toks[1:]:
            if t == "-exec" or t.startswith("-exec"):
                return "find -exec"
    elif interp in {"xargs", "parallel"}:
        # xargs takes a command after --
        return f"{interp} command chain"
    elif interp == "env":
        # env VAR=val cmd ... — environment injection vector
        for t in toks[1:]:
            if "=" in t and not t.startswith("-"):
                continue  # var assignment, still flagging the wrapped cmd
        return "env command chain"
    return None


def cmd_check_cmd(args):
    """Three-state verdict on a shell command line (Codex Decision semantics:
    allow / deny / confirm), applied PER SEGMENT of compound commands, plus
    Gemini-style injection scanning. Exit codes: 0 allow · 1 deny · 3 confirm
    (non-zero so it can never be mistaken for green)."""
    default, rules = _load_policy()

    # injection scan first — any substitution anywhere → confirm w/ reason
    inj = _detect_substitution(args.command)
    verdicts = []
    for seg in _split_segments(args.command):
        toks = _shlex_tokens(seg)
        if not toks:
            continue
        best = None  # longest-prefix-wins (Codex matches_for_command)
        for r in rules:
            p = r["pattern"]
            if len(toks) >= len(p) and toks[:len(p)] == p:
                if best is None or len(p) > len(best["pattern"]):
                    best = r
        v = dict(best) if best else {"pattern": toks[:2], "reason": "not in "
                                     "policy table", "decision": default}
        if best is None and inj:
            v["reason"] = f"{inj} detected"
        elif inj and v["decision"] == "allow":
            # an allowed verb wrapped around substitution is NOT safe anymore
            v["decision"], v["reason"] = "confirm", f"{inj} inside command"
        # interpreter-escape interception: `python -c`, `bash -c`, `find -exec`
        # etc. bypass simple verb matching — always force confirm.
        escape = _check_interpreter_escape(toks)
        if escape:
            v["decision"] = "confirm"
            v["reason"] = f"interpreter escape: {escape}"
        verdicts.append((seg, v))

    final, worst = "allow", None
    for seg, v in verdicts:
        print(f"  [{v['decision'].upper():7s}] {seg}   ({v['reason']})")
        order = {"deny": 0, "confirm": 1, "allow": 2}
        if order[v["decision"]] < order[final]:
            final, worst = v["decision"], v

    if final == "deny":
        fail(f"DENY: {worst['reason']}. Do NOT run this; propose a safer "
             "alternative.")
    if final == "confirm":
        print("[HCA-GATE-CONFIRM] show the FULL original command to the user "
              "and get explicit approval (clarify) before running:")
        print(f"  >> {args.command}")
        sys.exit(3)
    ok("command cleared by policy")


# ------------------------------------------------------------------ update

# Self-update check (v2.1.1). The skill checks its own GitHub repo for a
# newer release. Two throttle pointers in skill_state.json (lives NEXT to
# SKILL.md, not inside a project):
#   last_check_ts  — last real network check; a successful check re-arms only
#                    after UPDATE_CHECK_HOURS (72h). --force bypasses.
#   next_prompt_ts — after the user chose "B. 不升级", prompts are suppressed
#                    until now + UPGRADE_PROMPT_DAYS (3 days).
# Network failure degrades silently: the coding task must never be blocked by
# an update check.

GITHUB_REPO = "bobvane/hermes-code-agent"
GITHUB_API_RELEASES = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_TARBALL = f"https://github.com/{GITHUB_REPO}/archive/refs/tags/v{{v}}.tar.gz"
UPDATE_CHECK_HOURS = 72          # 3 天检测节流
UPGRADE_PROMPT_DAYS = 3          # 选 B 后 3 天再提示
UPDATE_HTTP_TIMEOUT = 5          # curl-like --max-time 5
EXEMPT_FILES = {"skill_state.json"}


def skill_root():
    """Skill directory = hca_gate.py 的上级的上级 (scripts/ -> skill root)."""
    return Path(__file__).resolve().parent.parent


def skill_state_path():
    return skill_root() / "skill_state.json"


def read_skill_state():
    p = skill_state_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_check_ts": 0, "next_prompt_ts": 0, "pending": None}


def write_skill_state(st):
    skill_state_path().write_text(
        json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def local_skill_version():
    """Read `version:` from the SKILL.md next to this script."""
    p = skill_root() / "SKILL.md"
    if not p.exists():
        return "0.0.0"
    m = re.search(r"^version:\s*([0-9][0-9a-zA-Z.\-]*)", p.read_text(encoding="utf-8"),
                  re.MULTILINE)
    return m.group(1).strip() if m else "0.0.0"


def parse_version(v):
    """'v2.1.1' / '2.10.0' -> tuple for numeric comparison."""
    s = (v or "").strip().lstrip("v")
    parts = []
    for seg in s.split("."):
        digits = "".join(ch for ch in seg if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def fetch_latest_release():
    """Return the newest release tag (e.g. 'v2.1.1') or None on failure."""
    req = urllib.request.Request(GITHUB_API_RELEASES,
                                 headers={"User-Agent": "hermes-code-agent",
                                          "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=UPDATE_HTTP_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data.get("tag_name")
    except Exception:
        return None


def cmd_update_check(args):
    st = read_skill_state()
    now = time.time()
    if not args.force and st.get("last_check_ts", 0) and \
            now - st["last_check_ts"] < UPDATE_CHECK_HOURS * 3600:
        print("[HCA-GATE] update: skipped (throttled " +
              f"{UPDATE_CHECK_HOURS}h since last check)")
        sys.exit(0)

    local = local_skill_version()
    remote = fetch_latest_release()

    if remote is None:
        # network failure / rate limit -> silent degrade, never block
        print("[HCA-GATE] update: check failed (network), skipping")
        sys.exit(0)

    remote_clean = remote.lstrip("v")
    st["last_check_ts"] = now
    write_skill_state(st)

    if parse_version(remote_clean) > parse_version(local):
        st["pending"] = {"remote": remote_clean, "checked_at": now,
                         "local": local}
        write_skill_state(st)
        print(f"[HCA-GATE] UPDATE_AVAILABLE local={local} remote={remote_clean}")
    else:
        st["pending"] = None
        write_skill_state(st)
        print(f"[HCA-GATE] update: up-to-date ({local})")
    sys.exit(0)


def cmd_update_pending(_args):
    """Called after GATE: non-empty output means 'offer the upgrade now'."""
    st = read_skill_state()
    pending = st.get("pending")
    if pending:
        now = time.time()
        if now >= st.get("next_prompt_ts", 0):
            local_v = pending.get("local", "unknown")
            remote_v = pending.get("remote", "unknown")
            print(f"[HCA-GATE] PENDING local={local_v} remote={remote_v}")
            sys.exit(0)
    print("[HCA-GATE] update: none pending")
    sys.exit(0)


def cmd_update_status(_args):
    st = read_skill_state()
    print(f"version:        {local_skill_version()}")
    lct = st.get("last_check_ts", 0)
    print(f"last_check_ts:  {lct} ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(lct)) if lct else 'never'})")
    npt = st.get("next_prompt_ts", 0)
    print(f"next_prompt_ts: {npt} ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(npt)) if npt else 'no cooldown'})")
    print(f"pending:        {st.get('pending')}")
    print(f"check_interval: {UPDATE_CHECK_HOURS}h · prompt_cooldown: {UPGRADE_PROMPT_DAYS}d")
    print(f"skill_path:     {skill_root()}")
    sys.exit(0)


def cmd_update_apply(args):
    """Download the pending (or --version) release, back up, overwrite.
    skill_state.json is exempt: throttle pointers survive the upgrade.
    Security: SHA-256 of tarball is fetched from the release's `.sha256` file
    and verified before extraction. Mismatches abort the upgrade."""
    st = read_skill_state()
    if args.version:
        remote = args.version.lstrip("v")
    elif st.get("pending") and st["pending"].get("remote"):
        remote = st["pending"]["remote"]
    else:
        print("[HCA-GATE] update: nothing to apply (run update-check first)")
        sys.exit(1)

    root = skill_root()
    url = GITHUB_TARBALL.format(v=remote)
    print(f"[HCA-GATE] update: downloading v{remote} ...")
    data: bytes = b""
    try:
        with urllib.request.urlopen(url, timeout=UPDATE_HTTP_TIMEOUT) as r:
            data = r.read()
    except Exception as e:
        fail(f"update: download failed: {e}")
    if not data:
        fail("update: download returned no bytes")

    # SHA-256 verification: fetch the .sha256 sidecar and compare.
    # Format: "<hex>  <filename>" or just "<hex>". Mismatch => abort.
    sha256_url = f"https://github.com/{GITHUB_REPO}/archive/refs/tags/v{remote}.sha256"
    expected_sha256 = ""
    try:
        with urllib.request.urlopen(sha256_url, timeout=UPDATE_HTTP_TIMEOUT) as r:
            sha_text = r.read().decode("utf-8", errors="replace").strip()
        # Parse "hex  filename" or "hex" format
        expected_sha256 = sha_text.split()[0].lower() if sha_text else ""
    except Exception:
        pass  # No sidecar or network issue; warn but allow (--skip-verify override)
    if args.skip_verify:
        print("[HCA-GATE] update: SHA-256 verification SKIPPED (--skip-verify)")
    elif expected_sha256:
        actual_sha256 = hashlib.sha256(data).hexdigest()
        if actual_sha256 != expected_sha256:
            fail(f"update: SHA-256 mismatch! expected={expected_sha256} "
                 f"got={actual_sha256} — aborting for safety")
        print(f"[HCA-GATE] update: SHA-256 verified ({actual_sha256[:16]}...)")
    else:
        print(f"[HCA-GATE] update: WARNING no .sha256 sidecar found, "
              f"proceeding without integrity check")

    with tempfile.TemporaryDirectory() as tmp:
        tarball = Path(tmp) / "release.tar.gz"
        tarball.write_bytes(data)
        extract_dir = Path(tmp) / "x"
        extract_dir.mkdir()
        import tarfile
        with tarfile.open(tarball, "r:gz") as tf:
            tf.extractall(extract_dir)
        # archive contains a single top dir: hermes-code-agent-<version>/
        src_root = next(extract_dir.iterdir())

        # validate: SKILL.md version must equal the target
        src_skill = src_root / "SKILL.md"
        m = re.search(r"^version:\s*([0-9][0-9a-zA-Z.\-]*)",
                      src_skill.read_text(encoding="utf-8"), re.MULTILINE)
        got = m.group(1).strip() if m else ""
        if got.lstrip("v") != remote.lstrip("v"):
            fail(f"update: tarball version mismatch (wanted {remote}, got {got})")

        # backup SKILL.md (rollback rail) then copy tree, exempting state
        backups = root / "backups"
        backups.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        if (root / "SKILL.md").exists():
            shutil.copy2(root / "SKILL.md", backups / f"SKILL.md.bak-{stamp}")

        for item in src_root.iterdir():
            if item.name in EXEMPT_FILES:
                continue
            dst = root / item.name
            if dst.exists():
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
            shutil.move(str(item), str(dst))

        # refresh state: bump version, clear pending, no prompt cooldown reset
        st["local"] = remote
        st["pending"] = None
        st["last_check_ts"] = time.time()
        write_skill_state(st)

    print(f"[HCA-GATE] UPDATED to v{remote} — restart the Hermes gateway "
          "(/model or restart) to load the new skill.")
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(prog="hca_gate.py",
                                 description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("detect", help="detect test/lint/build commands")

    sub.add_parser("snapshot", help="record a reversible git snapshot")

    r = sub.add_parser("restore", help="transactional restore to a snapshot")
    r.add_argument("snapshot", nargs="?", default="last",
                   help="snapshot id prefix or 'last'")

    c = sub.add_parser("compact", help="deterministic state compaction")

    q = sub.add_parser("quickcheck", help="fast per-file syntax gate")
    sub.add_parser("repomap", help="lightweight symbol-ranked repo map")
    q.add_argument("files", nargs="*", help="files to check (default: scan)")

    v = sub.add_parser("verify", help="run full test suite")
    v.add_argument("--max-chars", type=int, default=MAX_VERIFY_CHARS_DEFAULT)

    s = sub.add_parser("state", help="loop state: show|reset|bump")
    s.add_argument("state_cmd", nargs="?", choices=["show", "reset", "bump"])

    sub.add_parser("plancheck", help="verify PLAN did not touch sources")

    d = sub.add_parser("doomcheck", help="doom-loop detection by action tag")
    d.add_argument("tag")

    lc = sub.add_parser("locate", help="Aider did-you-mean: fuzzy-locate a "
                        "snippet in a file after a patch miss (read-only)")
    lc.add_argument("file", help="source file to search in")
    lc.add_argument("snippet", nargs="?", default=None,
                    help="expected snippet (default: stdin, diff markers ok)")

    cc = sub.add_parser("check_cmd", help="three-state command policy check "
                        "(Codex execpolicy x Gemini substitution scan)")
    cc.add_argument("command", help="full shell command line to evaluate")

    ap_ = sub.add_parser("apply", help="Codex apply-patch port: tolerant "
                         "patch application (seek_sequence 4-level match, "
                         "atomic, structured errors)")
    ap_.add_argument("patch_file", nargs="?", default=None,
                     help="patch file (default: stdin)")

    # --- self-update subcommands (v2.1.1)
    u = sub.add_parser("update-check",
                       help="check GitHub for newer release (throttled)")
    u.add_argument("--force", action="store_true",
                   help="bypass 72h throttle and force a network check")

    sub.add_parser("update-pending",
                   help="non-empty output = there is a pending upgrade to offer")

    sub.add_parser("update-status",
                   help="show version, throttle pointers, pending info")

    ua = sub.add_parser("update-apply",
                        help="download & overwrite skill from pending or --version")
    ua.add_argument("--version",
                    help="override pending; apply this tag (strip v prefix)")
    ua.add_argument("--skip-verify", action="store_true",
                    help="skip SHA-256 verification (NOT RECOMMENDED)")

    args = ap.parse_args()
    table = {"detect": cmd_detect, "snapshot": cmd_snapshot,
             "restore": cmd_restore, "compact": cmd_compact,
             "quickcheck": cmd_quickcheck, "verify": cmd_verify,
             "state": cmd_state, "plancheck": cmd_plancheck,
             "doomcheck": cmd_doomcheck,
             "locate": cmd_locate, "check_cmd": cmd_check_cmd,
             "repomap": cmd_repomap, "apply": cmd_apply,
             "update-check": cmd_update_check,
             "update-pending": cmd_update_pending,
             "update-status": cmd_update_status,
             "update-apply": cmd_update_apply}
    table[args.cmd](args)


if __name__ == "__main__":
    main()
