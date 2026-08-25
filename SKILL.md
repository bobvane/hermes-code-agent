---
name: hermes-code-agent
description: "Use when the user wants to build, fix, refactor, or verify software in a repo. Wraps Hermes's coding tools in a verify-loop (implement → test/lint → fix → only green is done) and orchestrates the existing general dev skills as stage workers. Distilled from 6 open coding agents (OpenCode primary, Codex + Aider + Cline + Gemini CLI + Pi), model-agnostic, plan-source-agnostic."
version: 2.0.0
author: bobvane
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [coding, agent, tdd, workflow, dev, automation]
    homepage: https://github.com/bobvane/hermes-code-agent
    title_zh: Hermes 代码助手（自纠错编程工作流）
---

# Hermes Code Agent — 验证循环

> **Hermes 代码助手（自纠错编程工作流）**
> 把 Hermes 变成一个会自己纠错的编程智能体：用「先验证、后完成」的循环（实现→测试/校验→修复→全绿才算完成）包裹模型。机制对齐六家开源 coding agent（OpenCode / Codex CLI / Aider / Cline / Gemini CLI / Pi），不引入它们之外的原创机制。

Turn Hermes into a self-correcting coding agent with a verify-before-done loop (implement → test → fix → green), the same skeleton every major open coding agent converges on.

**Model support policy（模型支持门槛）**: designed for coding-specialized models ≥8B active params or general models ≥24B. Smaller models may run it experimentally, but convergence is NOT guaranteed.

Cross-validated against two open-source agents read at equal depth: **OpenCode** (model-agnostic harness, LSP feedback, subagent fan-out, per-agent model) and **OpenAI Codex CLI** (ModeKind plan/exec split, Guardian fail-closed approval, Token/RolloutBudget cost ceiling). See `references/inspiration.md`.

## What this skill is NOT / 本技能不是什么

- NOT a rewrite of TDD / debugging / code-review skills. It **orchestrates** them as stage workers. Single source of truth stays with those skills.
- NOT bound to any planner (omh / AGENTS.md / company flow). Those are **optional upstreams**. A raw instruction works fine.
- NOT bound to any framework it shouldn't be. Runs on plain Hermes, any model, any repo.

## The hard loop (the only non-negotiable) / 唯一强制循环

Every implementation task goes through this. The agent must NOT report "done" until the gate is green.

```text
1. CLARIFY SCOPE   — what file(s)/behavior change? what does "done" mean (test? lint? run)?
                      Detect the test/lint/build command from repo signals (see Zero-config section) before asking; only ask if undetectable.
2. PLAN (separate mode) — switch to PLAN cognition: explore, read relevant files, decide approach.
                      Output a 3-5 step mini-plan. Do NOT edit code in this step.
                      (If an upstream plan exists, consume it and skip to step 3.)
3. BUILD (separate mode) — switch to BUILD cognition: minimal edits, one change per step.
4. VERIFY          — run the project's test/lint/build. Capture real output.
5. LOOP ON RED     — if red, feed the EXACT error back, fix, re-run. Max 5 red→fix cycles per step.
6. GATE            — only when ALL checks green AND scope met → mark step done.
7. REPEAT for next step. Then report: what changed, what's green, what's untested.
```

**Plan/Build separation v2 (Codex ModeKind × Cline Plan/Act, goal-plan-exec-split-v2):**
planning and editing are distinct modes with distinct discipline — never plan and edit in the same breath.

**Two mode scripts (Codex-style prompt-level split).** When you enter a mode, your behavior contract is EXACTLY that mode's text:

- **PLAN mode discipline**: read, search, explore, decide. Output a 3–5 step mini-plan (files to touch, approach, done-criteria). FORBIDDEN in PLAN: `patch` / `write_file` / any source edit; running mutating commands. If an upstream plan exists, consume it and skip to the BUILD gate.
- **BUILD mode discipline**: touch as little as possible, one change per step, verify each step. No re-planning mid-build; if the plan proves wrong, exit back through the stage gate (below), never silently switch cognition.

**Stage gate at every PLAN↔BUILD boundary (Cline-style user switch).** Do not cross a mode boundary on your own authority — ask:

```text
clarify("切换模式？", choices=["进入 BUILD（按方案执行）", "留在 PLAN（继续规划）"])   # PLAN → BUILD
clarify("回到规划？", choices=["回 PLAN 重新规划", "留在 BUILD 继续修"])             # BUILD → PLAN
```

The user's confirmation is the switch. This mirrors Cline's Plan/Act button: the human sees and authorizes every transition.

**plancheck is mandatory (not optional) at each boundary:** after PLAN output, before any edit, run `python scripts/hca_gate.py plancheck`. Exit !=0 → roll back the violating edits (`git restore`) before entering BUILD. Enforcement reality (honest label): Codex makes violations physically impossible at the host layer — we cannot. Ours = user-witnessed gates (clarify) + post-hoc audit (plancheck). A violation surfaces immediately because the user just watched the transition.

**Budget ceiling v2 (Codex TokenBudget × OpenCode MAX_STEPS, goal-step-budget-cap-v2):**
explicit step cap: **max 5 steps per task**, max 5 red→fix cycles in the TEST channel (3 for PATCH/STATIC), soft tool-call cap ~40. Multi-tier soft reminders fire ONCE each (deduped): step 4/5 → "plan the finish"; 3k tok → targeted reads; 8k tok → write a progress note first. Source-verified reality (both agents' "hard stop" is message-injection, not a kill): on hard exceed the gate prints a **MAX_STEPS close-out protocol** — no more edits, respond with text only structured as DONE / NOT DONE / NEXT. Follow it; do not attempt further tool calls after an exit-2 budget/doom stop.

**Verify rule v2 — three-channel triage (Aider × OpenCode, goal-verify-loop-v2):**
after an edit, do NOT run tests blindly. Triage by failure type into three independent channels — cheapest check first. Each channel has its OWN retry budget (they never eat each other's):

| Channel | Trigger | Action first | Budget |
|---|---|---|---|
| ① PATCH channel | `apply`/`patch` failed to land | structured error self-heal: the gate prints which hunk failed + expected-vs-actually-there → fix the patch and re-`apply`; for deep misses run `python scripts/hca_gate.py locate <file>` with the snippet | 3 tries |
| ② STATIC channel | patch landed but syntax/lint errors | fix directly from the quickcheck/lint output (seconds-level fail-fast) | 3 tries |
| ③ TEST channel | static clean, tests run and red | feed the exact verify digest back, fix, re-run | 5 red→fix cycles |

**Preferred edit path (Codex parity):** emit unified-diff patches and land them with `python scripts/hca_gate.py apply <patch-or-stdin>`. The engine is the Codex apply-patch port: seek_sequence four-level matching (exact → rstrip → trim → Unicode-normalized, never skipping levels), atomic per-file writes (any hunk fails → nothing is written), and structured errors ([PARSE]/[MATCH]/[IO] + hunk index + expected/actual context) designed to be fed back for model self-healing. `patch` (git-apply 3-tier) remains as fallback; plain `write_file` only for new files or full rewrites.

Rules: never jump to the test suite while ① or ② is failing; never re-patch while a test digest is the actual signal. Global ceiling still applies (see budget). Run the project's tests via `python scripts/hca_gate.py verify` — if red, feed the exact error back, fix, re-run. If the script is unavailable in this environment, run the project's tests manually and say so explicitly.

Forced-loop discipline (OpenCode): the error output IS your next input — processed, not paraphrased. You have no authority to declare done on red; only the gate exit code speaks.

## Deterministic gate: scripts/hca_gate.py / 确定性门禁脚本（v1.2.1 核心）

The punch-clock of the hard loop. Rules a model might forget become commands that always run. Stdlib-only Python; self-tested in `tests/test_hca_gate.py`. Call it at each stage instead of remembering prose rules:

```bash
python scripts/hca_gate.py detect          # CLARIFY: print detected test/lint/format commands
python scripts/hca_gate.py snapshot        # before BUILD: record reversible git snapshot id
python scripts/hca_gate.py plancheck       # after PLAN: exit!=0 if sources changed during planning → roll back
python scripts/hca_gate.py quickcheck f.py # after each edit: seconds-level syntax gate
python scripts/hca_gate.py doomcheck "edit:file:line"  # same tag 3x in a row → exit 2 = STOP this approach
python scripts/hca_gate.py locate f.py <<< "expected snippet"  # did-you-mean: fuzzy-locate after a patch miss (read-only)
python scripts/hca_gate.py apply < patch.diff  # land a unified diff (Codex seek_sequence engine, atomic)
python scripts/hca_gate.py verify          # GATE: run full test suite; exit code is the verdict
python scripts/hca_gate.py state show      # inspect loop counters: steps/redfix/doom/snapshots (.hca_state.json)
```

Exit-code contract (memorize ONE rule instead of twenty):

| exit | meaning | your required action |
|---|---|---|
| 0 | GREEN | step may proceed |
| 1 | RED | fix exactly what the digest shows; run tests again before claiming progress |
| 2 | DOOM-LOOP | revert to last snapshot or switch strategy; patching again is forbidden |

`verify` runs the full test suite and reports pass/fail via exit code. If pytest is missing, verify retries via a project-local `.venv/bin/python` automatically and prints concrete FIX commands on failure — follow them instead of re-running blindly.

State lives in `.hca_state.json` (steps, red→fix counts, doom log, snapshot ids). If state is stale (git HEAD moved), the script says so — run `state reset`.

Doom-loop + revert protocol: when `doomcheck` exits 2, prefer `snapshot`-based rollback to the step's start point over stacking another patch on a broken diff.

**API resilience (from OpenCode retry.ts):** when calling model APIs directly (curl/scripts), build in: max 5 retries, exponential backoff starting at 2s (×2), respect `retry-after` headers, and treat 429/5xx/network errors as retryable. Prefer non-streaming (`stream:false`) for long code generations through proxy gateways — streaming is prone to mid-stream drops.

## Project rules: two-layer conventions（两层规则文件，goal-project-rules-v2）

**Layer 1 — global**: `skills/hermes-code-agent/CONVENTIONS.md` ships with the skill (template in `templates/CONVENTIONS.md`, six-section skeleton: 通用纪律/工具链/编码规范/提交纪律/测试验证/禁区). The user may edit it; Hermes's bundled-skill user-modified mechanism preserves edits across upgrades. Read it at task start if present.

**Layer 2 — per project**: `<项目目录>/<项目名>.md`. Lives INSIDE the project directory so `mv` carries it with the repo. Name source: user-stated name > directory name > name fixed inside the file once generated.

**Entry check protocol (every coding task, before CLARIFY):**
1. Detect the project directory → none? clarify: "项目需要专属目录，建议 <workspace>/<项目名>/，确认？"
2. Detect `<项目名>.md` → present? load silently. Missing? generate it from `templates/project-rules.md`, auto-filled from detected stack (vitest → vitest commands, not blanks for the user to fill).
Both present → silent pass, zero interruption; only missing pieces trigger questions.

**Conflict rule**: project layer overrides global layer per-item (near wins); Section 1 通用纪律 is non-overridable.

**Universal safety rules（内置硬性安全规则，无需外部文件）** — always enforced, with or without any rules file:
- Run the project's test/lint/build and reach green before reporting "done" (the GATE rule above).
- Never commit secrets or `.env` files.
- Never `force` push to `main`/`master` (or the repo's protected branch).
- Destructive ops (push, rm -rf, drop, force flags) always need explicit user confirm (see Approval modes).

**Auto-detect project commands（自动探测命令，不依赖手写配置）** — in CLARIFY/VERIFY, detect the test/lint/build command from repo signals before asking:
- Python: `pytest` / `python -m pytest` (look for `pyproject.toml`, `pytest.ini`, `tests/`); lint `ruff`/`flake8` if present.
- Node: `npm test` / `npm run lint` / `npm run build` (read `package.json` scripts).
- Go: `go test ./...` / `go vet ./...`.
- Rust: `cargo test` / `cargo clippy`.
- Has a `Makefile`? prefer `make test` / `make lint` / `make build`.
- If detection is ambiguous or the user stated a command, use that. Only ask in CLARIFY if truly undetectable.

**Rules file is optional override** — the two-layer conventions above (global CONVENTIONS.md + per-project `<项目名>.md`) add project-specific overrides on top of the built-in defaults. If neither exists, the skill runs identically (auto-detect + built-in safety).

## Stage workers (call these, don't duplicate them) / 阶段性协作工具

When the step needs it, load the matching skill instead of re-inventing instructions:

| Need | Load |
|---|---|
| Writing tests before code | `test-driven-development` |
| Root-causing a bug | `systematic-debugging` |
| Pre-commit quality / security | `requesting-code-review` |
| Cleaning recent diffs | `simplify-code` |
| Parallel implement + review | `delegate_task` (one builder + one reviewer, isolated contexts) + `references/parallel-implement-review.md` |

If the skill is not installed, fall back to the behavior described inline — do not block.

## Advanced patterns (distilled from 6 open agents, OpenCode primary)

OpenCode leads (harness architecture). Codex secondary (ModeKind/Guardian/Budget). This round adds Aider, Cline, Gemini CLI, Pi — see `references/extra-distillation.md`. Defaults, not options.

1. **Delegate by default for non-trivial tasks.** Do not implement + review in the same head. Use `delegate_task`: one builder agent (isolated context) + one reviewer agent, run in parallel, then reconcile. Use the reusable prompts in `references/parallel-implement-review.md`. Both OpenCode (Task tool) and Codex (multi_agents_v2) converge on this.

**Pitfall (stream vs non-stream in non-interactive mode):** one-shot invocations (`aider -m`, `opencode run`) are unstable with default streaming — 0-byte files (Aider) or mid-stream crashes (OpenCode). Force `stream=false` / `--no-stream` on headless paths; interactive TUI keeps streaming. Reproduction: `references/non-interactive-streaming-pitfall.md`.
2. **Per-role model tiers (OpenCode declarative mapping × Codex elasticity, goal-per-role-model-v2).**
   Role→tier mapping (declarative, like OpenCode's per-agent `model` field):

   | Step/role | Tier | Why |
   |---|---|---|
   | PLAN / architecture / root-cause diagnosis | strong tier (largest reasoning model configured) | planning errors cascade into every later step |
   | BUILD / mechanical edits / test-fix loops | economy tier (cheapest model that passes verify) | high volume, low decision density |
   | REVIEW / code-review / security scan | mid or strong tier | judgment-heavy but cheaper than planning |

   **Boundary check (non-blocking reminder):** at every step boundary, check whether the current model matches this step's tier from the table. Mismatch → tell the user once: "本步骤建议切换到<档次>模型（/model），不切换则继续" — then CONTINUE with whatever model is active. The Skill cannot route requests (host-layer, form-factor limit); the user switching gains the benefit, not switching costs nothing — the loop never waits for a model change.
3. **Command-segment approval + low-risk self-review.** Split shell commands at operators (`|`, `&&`, `||`, `;`, subshells) and evaluate EACH segment. Destructive segments (`rm`, `git reset --hard`, `drop`, force flags) ALWAYS need explicit user confirm — never auto-approve. For *non-destructive, repeated* approvals in `auto-edit` mode, apply a quick self-review (re-state the action + risk; deny if ambiguous) instead of pinging the user every time — borrowed from Codex's Guardian (fail-closed) pattern; destructive ops never go to self-review.
4. **Bound the loop + budget (Codex soft reminders).** Step cap (5), red→fix cap (5/step), soft tool-call cap (~40). Multi-tier soft reminders fire before hard limits: step 4/5 → "plan the finish"; token tiers (3k/8k) → targeted-read / summarize advice; each tier fires once (deduped in `budget_fired`). On hard exceed → stop, report blocker.
5. **Repo map: two index cards (Aider × Cline, goal-repo-map-v2).** Build the map in two passes — coarse first, expand on demand:
   - **Card 1 目录卡 (directory card, Cline-style)** — at every task start: list the project tree (file names only) via `search_files(target='files')` or `ls -R`, excluding junk dirs (`node_modules/ .git/ __pycache__/ venv/ .venv/ dist/ build/`). Answers "项目长什么样、东西在哪".
   - **Card 2 符号卡 (symbol card, Aider-style)** — on demand, AFTER picking task-relevant files from Card 1: extract definition lines from those files with `search_files(pattern='^\\s*(class |def |function |fn |func )', target='content')` (ripgrep ships with Hermes). Answers "这个文件里有什么功能、该去哪改".
   Flow: 任务开始 → 目录卡(全景) → 按需求挑相关文件 → 符号卡(细节) → 动手. Never build the symbol card for the whole repo — relevance judgment is yours, informed by the task (an advantage Aider's blind indexer lacks; its tree-sitter+PageRank precision is traded for zero-dependency ripgrep, ~90% of the value).
6. **Checkpoint before each BUILD step (Cline, transactional).** `snapshot` records stash commit + untracked companion tree under a private ref `refs/hca/snapshots/<id>`; `restore <id|last>` returns the tree to the exact snapshot state (removes post-snapshot junk files), verifies cleanliness, records `restored_from`. First-class rollback rail.
7. **Model-aware context strategy + deterministic compaction.** Big-window models: load broadly; small-window: repo map. `compact` subcommand trims state deterministically (keep last 10 snapshots + 20 telemetry entries, tail-preserved split, no LLM involved — Gemini-style failure-safe fallback).
8. **Formatter / compaction / plan-separation live in the script.** `quickcheck` formatters, `verify --max-chars` double-limit digest (line cap 200 + byte cap, tail fallback so red is never silent), `plancheck` enforces plan/build separation. Verify also records token≈ telemetry (`tokens_verify` in state, capped at 20 entries) for cost tracking — the "cache miss" observability ported from Pi's cache-stats.
9. **Progressive disclosure (Pi).** Reference docs and skills are indexed by name+path in this file; read them on demand, never preload. Long-form evidence lives in `references/`, not inline.

## Parallel execution v2 (OpenCode delegation culture × Codex lifecycle, goal-subagent-parallel-v2)

**Delegation is the default (OpenCode hard rule), not an option.** For any non-trivial task, your first instinct must be: split and fan out via `delegate_task`. Trigger checklist — delegate when ANY of:
- ≥2 independent file-level changes (different files, no shared imports under active change)
- a wide read-only exploration (repo survey, multi-file impact analysis)
- implement + review can be separated into different heads
Do NOT parallelize edits to the same file or files with shared imports under active change. Only skip delegation for single-file trivial fixes.

1. **Self-contained prompts**: each subagent gets its own full brief — subagents see nothing of the main conversation. Every prompt must state: goal, exact files, expected output artifact, and the verify command to run.
2. **Say write vs research**: tell each agent explicitly whether it writes code or only explores (read-only).
3. **Orchestration shape**: N builders (isolated contexts, parallel) + 1 reviewer (converges). The orchestrator reconciles results and never re-implements a builder's work itself.
4. **Concurrency cap ≤3**: more than 3 parallel agents risks provider rate-limits. Queue the rest. (Codex enforces this with a runtime limiter — a host-layer capability we lack; the cap here is prompt discipline + Hermes' own child cap as backstop.)
5. **Lifecycle protocol (Codex six-action port)** — manage every agent through its full life:
   - **spawn**: dispatch with the self-contained brief (batch mode for parallel starts)
   - **message**: course-correct a running agent mid-flight (`steer`) instead of killing it
   - **wait**: batch results re-enter the conversation on completion; do not poll in a loop — continue other work or wait for delivery
   - **list**: know who is running before spawning duplicates (`delegate_task` action=list)
   - **interrupt**: stop a drifting agent early (`stop`); its partial result still returns
   - **follow-up**: a new small task building on a finished agent = a fresh spawn whose brief includes that agent's returned artifact (there is no true followup handle; re-brief explicitly)
6. **Merge gate**: after all builders return, run the FULL project verify (not per-agent checks) before GATE. A step is done only when the merged tree is green.

## Approval tiers (Codex approval policy × Cline auto-approve, goal-permission-tiers-v2)

One table, four tiers — check it BEFORE any action. L2/L3 use `clarify` as the approval action (the Cline confirm-dialog experience: the user sees and approves before the act).

| Tier | Operations | Action |
|---|---|---|
| **L0 免审** (Cline auto-approve) | read_file / search_files / repomap; git status/diff/log; running tests/lint/build (read-only side effects) | do it, no ask |
| **L1 常规** (Codex on-failure) | project-file edits via patch/write_file; quickcheck; snapshot/restore within repo; hca_gate commands | do it; report failures honestly |
| **L2 审批** (Codex untrusted + Cline per-op confirm) | installing dependencies; writing outside the project dir; git commit/push/tag; network downloads (curl/wget/pip/npm install); creating cron jobs | `clarify` first, act only on approval |
| **L3 红线** (both agents' never-auto set) | deleting data (`rm -rf`, drop, reset --hard); modifying system config; sending messages / publishing / releasing; touching secrets, keys, or restricted paths (~/.ssh/, ~/.aws/, *key*, *secret*); disabling safety rules | `clarify` with a recommended-reject default |

Enforcement reality (honest label): the table is prompt-level knowledge — nothing forces the model to consult it before every act. Post-hoc audit and the user watching L2/L3 clarify prompts are the backstops. Destructive ops need explicit user confirm in EVERY mode, including full-auto.

## Dangerous-command interception (Codex execpolicy × Gemini substitution scan, goal-dangerous-cmd-intercept-v2)

Before running ANY terminal command (L1 and above), run the deterministic engine:

```bash
python scripts/hca_gate.py check_cmd "<full command line>"
```

Exit codes: `0` ALLOW → run it · `1` DENY → do NOT run, propose a safer alternative · `3` CONFIRM → show the FULL original command to the user via clarify and act only on approval.

What the engine does (ported verbatim from upstream source):
- **Three-state prefix table** (`scripts/cmd_policy.yaml`, Codex Decision semantics) — longest-prefix-wins; unmatched commands fail CLOSED to confirm
- **Per-segment checks** — compound commands (`&&`/`;`/`|`) are split and EACH segment judged independently (both engines); one bad segment denies the whole line
- **Quote-aware injection scan** (Gemini `detectCommandSubstitution`) — `$()`, backticks, `<()`/`>()` process substitution anywhere → at best CONFIRM, even inside an allowlisted verb; quoted `$()` inside single quotes is correctly ignored

The engine is deterministic Python — same verdict as the upstream engines for any input. The only soft link is that the model must invoke it first; post-hoc audit catches skips.

## Optional upstream plan (omh / AGENTS.md / other)

If the conversation already contains a structured plan (from omh, a written AGENTS.md, or any planner), **consume it as step 2's input** — do not re-plan. If none exists, the mini-plan above suffices. The skill never requires a planner to function.

## Context management (keeps weak models on track)
## Benchmark results
Full A/B benchmark data and the 5-role design review are in `benchmarks/v180-benchmark-report.md` + raw results in `benchmarks/v180_raw_results.json`. Quick takeaway: every green delivered is verified (`exit 0`); weak models still hit a hard ceiling.

- Prefer `search_files` / `read_file` (paged) over dumping whole trees.
- Before editing, read only the files the change touches + their direct callers.
- If context is large, summarize completed steps into a short status line and drop old tool output.
- Respect `.gitignore` and project rule files (AGENTS.md / .hermes.md / CLAUDE.md) when present.

## Quick start for the user / 快速开始

1. Drop `hermes-code-agent/` into `~/.hermes/skills/` (or your Hermes skills dir). **That's it — zero config.**
2. In chat: "build X", "fix bug in Y", "refactor Z" — the loop runs automatically. Safety rules and test/lint commands are built-in.
3. (Optional) Project-specific conventions: the skill generates `<项目名>.md` in your project on first contact (auto-filled from detected stack), or you can edit the global `CONVENTIONS.md` inside the skill directory. **Neither is required** — auto-detect + built-in safety work alone.

See `ROADMAP.md` for the project's intent and the `references/` folder for source analysis.
