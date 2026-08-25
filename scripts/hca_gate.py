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

Exit codes: 0 green · 1 red/blocked · 2 doom stop

Stdlib only. No third-party dependencies. Python 3.8+.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

STATE_FILE = ".hca_state.json"
DOOM_THRESHOLD = 3
MAX_VERIFY_CHARS_DEFAULT = 2000


# ---------------------------------------------------------------- utilities

def run(cmd, timeout=300):
    """Run a command in its own process group; return (returncode, output).
    On timeout the whole group is killed (start_new_session=True + killpg)
    so a hang in a child (e.g. impl self-deadlock freezing pytest) can never
    block the gate — v1.8.1 hardening."""
    import signal
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            start_new_session=True
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired as te:
        # the subprocess.run call already killed the leader; also reap
        # any surviving process-group members (defensive — impl may fork)
        pid = getattr(te, "pid", None)
        if pid is not None:
            try:
                import signal
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except Exception:
                pass
        return 124, f"timeout after {timeout}s: {' '.join(cmd)}"


def fail(msg):
    print(f"[HCA-GATE-RED] {msg}")
    sys.exit(1)


# ------------------------------------------- patch apply w/ 3-tier fallback

def _unified_diff_blocks(diff_text):
    """Split a multi-file unified diff into (path, hunks) blocks."""
    import re as _re
    blocks, cur = [], None
    for line in diff_text.splitlines():
        m = _re.match(r"\+\+\+ (?:b/)?(\S+)", line)
        if m and not line.startswith("---"):
            cur = {"path": m.group(1), "lines": []}
            blocks.append(cur)
            continue
        if cur is not None:
            if line.startswith(("--- ", "diff --git")) \
                    and not line.startswith("--- \t"):
                cur = None
                continue
            cur["lines"].append(line)
    return [b for b in blocks if b["lines"]]


def cmd_patch(args):
    """Codex-style patch application with three-tier matching fallback:
    tier 1: `git apply` (exact context);
    tier 2: per-hunk apply with reduced context (`--unidiff-zero` + ignore
            whitespace) — survives small drift around the edit;
    tier 3: anchor replace — find the removed lines' core content with all
            whitespace stripped; if unique, splice the replacement.
    Never partially applies a file silently: reports per-block outcome."""
    diff_text = Path(args.patch_file).read_text(encoding="utf-8") \
        if args.patch_file else sys.stdin.read()
    blocks = _unified_diff_blocks(diff_text)
    if not blocks:
        fail("no parseable diff blocks")
    results = []
    for b in blocks:
        block_diff = ("--- a/" + b["path"] + "\n+++ b/" + b["path"]
                      + "\n" + "\n".join(b["lines"]) + "\n")
        p = Path(b["path"])
        # tier 1: exact git apply of this block
        proc = subprocess.run(["git", "apply", "--whitespace=nowarn", "-"],
                              input=block_diff, capture_output=True,
                              text=True, timeout=60)
        if proc.returncode == 0:
            results.append((b["path"], "exact"))
            continue
        # tier 2: relaxed — ignore whitespace changes, allow zero context
        proc = subprocess.run(
            ["git", "apply", "--ignore-whitespace", "--unidiff-zero",
             "--whitespace=nowarn", "-"],
            input=block_diff, capture_output=True, text=True, timeout=60)
        if proc.returncode == 0:
            results.append((b["path"], "fuzzy(ws)"))
            continue
        # tier 3: anchor — strip ws from removed lines, require uniqueness
        old_lines = [ln[1:] for ln in b["lines"]
                     if ln.startswith("-") and not ln.startswith("---")]
        new_lines = [ln[1:] for ln in b["lines"]
                     if ln.startswith("+") and not ln.startswith("+++")]
        key = "".join(old_lines).strip()
        if not p.exists() or not key:
            results.append((b["path"], "FAILED(all tiers)"))
            continue
        text = p.read_text(encoding="utf-8")
        knorm = "".join(key.split())
        if _wsfree_count(text, key) != 1:
            results.append((b["path"], "FAILED(anchor not unique/found)"))
            continue
        span = _wsfree_span(text, key)   # (first_char_idx, last_char_idx)
        if span is None:
            results.append((b["path"], "FAILED(anchor walk)"))
            continue
        first, last = span
        new_text = text[:first] + "\n".join(new_lines) + text[last + 1:]
        p.write_text(new_text, encoding="utf-8")
        results.append((b["path"], "anchor"))
    for path, how in results:
        print(f"  ok  {path} [{how}]")
    bad = [r for r in results if r[1].startswith("FAILED")]
    if bad:
        fail(f"{len(bad)}/{len(results)} patch block(s) failed: "
             + "; ".join(f"{p}: {h}" for p, h in bad))
    ok(f"patch applied ({len(results)} block(s))")


def _wsfree_count(text, key):
    """Occurrences of `key` in `text` ignoring all whitespace on both sides."""
    knorm = "".join(key.split())
    if not knorm:
        return 0
    return sum(1 for _ in _wsfree_iter(text, knorm))


def _wsfree_iter(text, knorm):
    """Yield (start, end) spans where knorm matches ignoring whitespace."""
    i, j, n, m = 0, 0, len(text), len(knorm)
    start = None
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if j == 0:
            start = i
        if ch == knorm[j]:
            j += 1
            i += 1
            if j == m:
                yield (start, i - 1)
                j, start = 0, None
        else:
            # mismatch: restart scan just after the candidate start char
            i = start + 1
            j, start = 0, None


def _wsfree_span(text, key):
    knorm = "".join(key.split())
    for span in _wsfree_iter(text, knorm):
        return span
    return None


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
        m = re.match(r"\+\+\+ (?:b/)?(\S+)", raw)
        if m and not raw.startswith("---"):
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


def apply_seek_patch_file(path, hunks):
    """Apply parsed hunks to ONE file atomically via seek_sequence. All hunks
    must land or nothing is written (Codex atomicity). Raises
    ApplyPatchError on the first failing hunk with expected/actual context."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8") if p.exists() else ""
    except OSError as e:
        raise ApplyPatchError("io", f"cannot read {path}: {e}")
    lines = text.splitlines()
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
    try:
        p.write_text("\n".join(lines) + ("\n" if lines else ""),
                     encoding="utf-8")
    except OSError as e:
        raise ApplyPatchError("io", f"cannot write {path}: {e}")


def cmd_apply(args):
    """Codex-style tolerant patch application (apply-patch module port).
    Parse → seek_sequence 4-level match → atomic write per file.
    On ANY failure: print the structured error (which hunk, expected vs
    actually-there) so the model can fix the patch and retry — exit 1."""
    patch_text = Path(args.patch_file).read_text(encoding="utf-8") \
        if args.patch_file else sys.stdin.read()
    try:
        blocks = parse_patch(patch_text)
    except ApplyPatchError as e:
        print(f"[HCA-GATE-RED]\n{e.render()}")
        print("[HCA-GATE] Fix the patch format and re-submit.")
        sys.exit(1)
    results = []
    for b in blocks:
        try:
            apply_seek_patch_file(b["path"], b["hunks"])
            results.append((b["path"], len(b["hunks"])))
        except ApplyPatchError as e:
            print(f"[HCA-GATE-RED]\n{e.render()}")
            print("[HCA-GATE] PATCH channel: feed this error back, adjust "
                  "the patch (run `locate <file>` for fuzzy rescue), "
                  "re-submit. The file was NOT modified.")
            sys.exit(1)
    for path, nh in results:
        print(f"  ok  {path} ({nh} hunk(s), seek_sequence)")
    ok(f"patch applied atomically to {len(results)} file(s)")


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
        sys.exit(1)
    for kind, items in cmds.items():
        for it in items:
            print(f"{kind}: {it}")
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


def cmd_verify(args):
    cmds = detect_commands()["test"]
    if not cmds:
        st = load_state()
        reminder = budget_reminder(st)  # fire soft warnings even on early RED
        fail("no test command detected — ask the user; do NOT fake green"
             + reminder)
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
    if run(["git", "diff", "--cached", "--quiet"])[0] == 0:
        return  # only the state file changed — nothing to land
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
    pp = sub.add_parser("patch", help="apply unified diff (3-tier fallback)")
    pp.add_argument("patch_file", nargs="?", default=None,
                    help="diff file (default: stdin)")
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

    args = ap.parse_args()
    table = {"detect": cmd_detect, "snapshot": cmd_snapshot,
             "restore": cmd_restore, "compact": cmd_compact,
             "quickcheck": cmd_quickcheck, "verify": cmd_verify,
             "state": cmd_state, "plancheck": cmd_plancheck,
             "doomcheck": cmd_doomcheck,
             "locate": cmd_locate, "check_cmd": cmd_check_cmd,
             "patch": cmd_patch, "repomap": cmd_repomap, "apply": cmd_apply}
    table[args.cmd](args)


if __name__ == "__main__":
    main()
