---
name: hermes-code-agent
description: "Use when the user wants to build, fix, refactor, or verify software in a repo. Wraps Hermes's coding tools in a verify-loop (implement → test/lint → fix → only green is done) and orchestrates the existing general dev skills as stage workers. Distilled from 6 open coding agents (OpenCode primary, Codex + Aider + Cline + Gemini CLI + Pi), model-agnostic, plan-source-agnostic."
version: 1.8.2
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

**Plan/Build separation (from Codex ModeKind):** planning and editing are distinct modes with distinct discipline. Plan = look and decide; Build = touch as little as possible and verify. Never plan and edit in the same breath.

**Budget ceiling (from Codex Token/RolloutBudget):** cap the whole task at a budget — e.g. max 5 steps, max 5 red→fix cycles per step, and a soft tool-call cap (~40). On exceed, STOP and report a blocker. This is the guard against a weak model looping forever and burning tokens.

**Verify rule (Aider-style retry discipline):** "not green = not done" is a prompt-level discipline (same as Aider's auto-retry). Run the project's tests via `python scripts/hca_gate.py verify` — if red, feed the exact error back, fix, re-run, up to 3 retries. If the script is unavailable in this environment, run the project's tests manually and say so explicitly.

## Deterministic gate: scripts/hca_gate.py / 确定性门禁脚本（v1.2.1 核心）

The punch-clock of the hard loop. Rules a model might forget become commands that always run. Stdlib-only Python; self-tested in `tests/test_hca_gate.py`. Call it at each stage instead of remembering prose rules:

```bash
python scripts/hca_gate.py detect          # CLARIFY: print detected test/lint/format commands
python scripts/hca_gate.py snapshot        # before BUILD: record reversible git snapshot id
python scripts/hca_gate.py plancheck       # after PLAN: exit!=0 if sources changed during planning → roll back
python scripts/hca_gate.py quickcheck f.py # after each edit: seconds-level syntax gate
python scripts/hca_gate.py doomcheck "edit:file:line"  # same tag 3x in a row → exit 2 = STOP this approach
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

## Zero-config by default（零配置，无需 AGENTS.md）

> Install once, zero-config. No per-project file copying required.

**Universal safety rules（内置硬性安全规则，无需外部文件）** — always enforced, with or without an AGENTS.md:
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

**AGENTS.md is now fully optional（AGENTS.md 仅为可选覆盖）** — `templates/AGENTS.md` is NOT required. The skill already enforces the above by itself. Use AGENTS.md ONLY to *override* auto-detected defaults or add project-specific conventions (naming, layout, out-of-scope). If present at repo root, the skill consumes it as an override; if absent, it runs identically.

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
2. **Per-step model hint (where setup allows).** If the user's Hermes config has more than one model, prefer a stronger model for PLAN/architecture steps and a cheaper one for BUILD/execute steps. OpenCode does this via a per-agent `model` field; we approximate via profile/provider swap at step boundaries.
3. **Command-segment approval + low-risk self-review.** Split shell commands at operators (`|`, `&&`, `||`, `;`, subshells) and evaluate EACH segment. Destructive segments (`rm`, `git reset --hard`, `drop`, force flags) ALWAYS need explicit user confirm — never auto-approve. For *non-destructive, repeated* approvals in `auto-edit` mode, apply a quick self-review (re-state the action + risk; deny if ambiguous) instead of pinging the user every time — borrowed from Codex's Guardian (fail-closed) pattern; destructive ops never go to self-review.
4. **Bound the loop + budget (Codex soft reminders).** Step cap (5), red→fix cap (5/step), soft tool-call cap (~40). Multi-tier soft reminders fire before hard limits: step 4/5 → "plan the finish"; token tiers (3k/8k) → targeted-read / summarize advice; each tier fires once (deduped in `budget_fired`). On hard exceed → stop, report blocker.
5. **Repo map before edits (Aider).** Lightweight structural index (symbol defs + import edges) ranked by step relevance; feed top-N symbols only. Biggest context-efficiency win surveyed. Approximate `aider/repomap.py` PageRank.
6. **Checkpoint before each BUILD step (Cline, transactional).** `snapshot` records stash commit + untracked companion tree under a private ref `refs/hca/snapshots/<id>`; `restore <id|last>` returns the tree to the exact snapshot state (removes post-snapshot junk files), verifies cleanliness, records `restored_from`. First-class rollback rail.
7. **Model-aware context strategy + deterministic compaction.** Big-window models: load broadly; small-window: repo map. `compact` subcommand trims state deterministically (keep last 10 snapshots + 20 telemetry entries, tail-preserved split, no LLM involved — Gemini-style failure-safe fallback).
8. **Formatter / compaction / plan-separation live in the script.** `quickcheck` formatters, `verify --max-chars` double-limit digest (line cap 200 + byte cap, tail fallback so red is never silent), `plancheck` enforces plan/build separation. Verify also records token≈ telemetry (`tokens_verify` in state, capped at 20 entries) for cost tracking — the "cache miss" observability ported from Pi's cache-stats.
9. **Progressive disclosure (Pi).** Reference docs and skills are indexed by name+path in this file; read them on demand, never preload. Long-form evidence lives in `references/`, not inline.

## Parallel execution (fan-out, from OpenCode Task tool) / 并行子代理

OpenCode's Task tool makes concurrent subagent launch the default ("launch multiple agents concurrently whenever possible"). We encode it into the hard loop via Hermes's `delegate_task`.

1. **Trigger**: use fan-out when there are ≥2 independent file-level changes, OR a wide read-only exploration is needed. Never parallelize edits to the same file or files with shared imports under active change.
2. **Self-contained prompts**: each subagent gets its own full brief — subagents see nothing of the main conversation. Every prompt must state: goal, exact files, expected output artifact, and the verify command to run.
3. **Say write vs research**: tell each agent explicitly whether it writes code or only explores (OpenCode task.txt rule). Exploration agents are read-only.
4. **Orchestration shape**: N builders (isolated contexts, parallel) + 1 reviewer (converges). The orchestrator reconciles results and never re-implements a builder's work itself.
5. **Concurrency cap ≤3**: more than 3 parallel agents risks provider rate-limits and makes reconcile harder. Queue the rest.
6. **Merge gate**: after all builders return, run the FULL project verify (not per-agent checks) before GATE. A step is done only when the merged tree is green.

## Approval modes (borrowed from Codex CLI)

Pick by task risk.
- **suggest** — propose changes, ask before editing. Use for unfamiliar/prod repos.
- **auto-edit** — edit + run read-only checks freely; stop only on destructive ops (push, force, delete). Low-risk repeated approvals may use self-review (Advanced pattern 3).
- **full-auto** — unattended; only for sandboxed/throwaway work. Never default to this.
- Default is `auto-edit` for local repos you trust.

Destructive commands (git push, rm -rf, drop db, force flag) ALWAYS require an explicit user confirm, regardless of mode.

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
3. (Optional) If you want project-specific overrides (e.g. a non-standard test command or extra conventions), copy `templates/AGENTS.md` into that repo and edit it. **This step is NOT required** — the skill auto-detects commands and enforces safety on its own.

See `ROADMAP.md` for the project's intent and the `references/` folder for source analysis.
