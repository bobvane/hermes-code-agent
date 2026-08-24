---
name: hermes-code-agent
description: "Use when the user wants to build, fix, refactor, or verify software in a repo. Wraps Hermes's coding tools in a hard verify-loop (implement → test/lint → fix → only green is done) and orchestrates the existing general dev skills as stage workers. Distilled from 6 open coding agents (OpenCode primary, Codex + Aider + Cline + Gemini CLI + Pi), model-agnostic, plan-source-agnostic."
version: 0.11.1
author: bobvane
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [coding, agent, tdd, workflow, dev, automation]
    homepage: https://github.com/bobvane/hermes-code-agent
    title_zh: Hermes 代码助手（自纠错编程工作流）
---

# Hermes Code Agent

> **Hermes 代码助手（自纠错编程工作流）**
> 把 Hermes 变成一个会自己纠错的编程智能体：用「先验证、后完成」的硬循环（实现→测试/校验→修复→全绿才算完成）包裹模型，让弱到中档模型也能稳定产出可靠代码。

Turn Hermes into a self-correcting coding agent. The model alone is a "weak coder"; this skill is the harness that makes weak-to-mid models punch above their weight by forcing a **verify-before-done** loop instead of one-shot code dumping.

Cross-validated against two open-source agents read at equal depth: **OpenCode** (model-agnostic harness, LSP feedback, subagent fan-out, per-agent model) and **OpenAI Codex CLI** (ModeKind plan/exec split, Guardian fail-closed approval, Token/RolloutBudget cost ceiling). See `references/inspiration.md`.

## What this skill is NOT

- NOT a rewrite of TDD / debugging / code-review skills. It **orchestrates** them as stage workers. Single source of truth stays with those skills.
- NOT bound to any planner (omh / AGENTS.md / company flow). Those are **optional upstreams**. A raw instruction works fine.
- NOT bound to any framework it shouldn't be. Runs on plain Hermes, any model, any repo.

## The hard loop (the only non-negotiable)

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

**Gate rule (must be explicit in your reasoning):** "not green = not done." Never summarize past a red check. If a check is unavailable, say so and downgrade confidence — do not fake green.

## Zero-config by default（零配置，无需 AGENTS.md）

> 本 Skill 安装一次即可使用，不需要为任何项目复制文件。
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

## Stage workers (call these, don't duplicate them)

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

OpenCode leads (harness architecture). Codex secondary (ModeKind/Guardian/Budget). This
round adds Aider, Cline, Gemini CLI, Pi — see `references/extra-distillation.md`. Defaults, not options.

1. **Delegate by default for non-trivial tasks.** Do not implement + review in the same head. Use `delegate_task`: one builder agent (isolated context) + one reviewer agent, run in parallel, then reconcile. Use the reusable prompts in `references/parallel-implement-review.md`. Both OpenCode (Task tool) and Codex (multi_agents_v2) converge on this.
2. **Per-step model hint (where setup allows).** If the user's Hermes config has more than one model, prefer a stronger model for PLAN/architecture steps and a cheaper one for BUILD/execute steps. OpenCode does this via a per-agent `model` field; we approximate via profile/provider swap at step boundaries.
3. **Command-segment approval + low-risk self-review.** Split shell commands at operators (`|`, `&&`, `||`, `;`, subshells) and evaluate EACH segment. Destructive segments (`rm`, `git reset --hard`, `drop`, force flags) ALWAYS need explicit user confirm — never auto-approve. For *non-destructive, repeated* approvals in `auto-edit` mode, apply a quick self-review (re-state the action + risk; deny if ambiguous) instead of pinging the user every time — borrowed from Codex's Guardian (fail-closed) pattern; destructive ops never go to self-review.
4. **Bound the loop + budget.** Step cap (3-5), red→fix cap (5/step), and a soft tool-call cap (~40). On exceed → stop, report blocker. OpenCode encodes this via a `steps` field; Codex via Token/RolloutBudget. We enforce both.
5. **Repo map before edits (Aider).** Before BUILD, build a lightweight structural index of the repo (symbol defs + import edges), rank by relevance to the current step, and feed the top-N symbols as context. Do NOT dump the whole tree. This gives automatic codebase awareness — the biggest context-efficiency win among all agents surveyed, and the direct antidote to "weak model gets lost in a large repo". Approximate Aider's PageRank repo map (`aider/repomap.py`, `nx.pagerank`).
6. **Checkpoint before each BUILD step (Cline).** Before editing, take a reversible snapshot (e.g. `git stash` / worktree / copy) so a bad step can be undone. Cline proves per-step rollback (snapshot after every tool use, one-click restore) is a first-class safety rail — especially valuable for weak models that may make a destructive edit.
7. **Model-aware context strategy (Gemini CLI).** If the active model has a large context window, prefer loading broadly (+ periodic compress) over aggressive pruning. If small-window, rely on the repo map (pattern 5). Gemini's 1M-token strategy is the opposite pole from OpenCode's compact-and-trim; pick per model. (Pi confirms the minimal-kernel + extension design — our skill stays thin orchestrator, not a monolith; no separate rule needed.)

## Approval modes (borrowed from Codex CLI)

Pick by task risk. Default to `auto-edit` for local repos you trust.

- **suggest** — propose changes, ask before editing. Use for unfamiliar/prod repos.
- **auto-edit** — edit + run read-only checks freely; stop only on destructive ops (push, force, delete). Low-risk repeated approvals may use self-review (Advanced pattern 3).
- **full-auto** — unattended; only for sandboxed/throwaway work. Never default to this.

Destructive commands (git push, rm -rf, drop db, force flag) ALWAYS require an explicit user confirm, regardless of mode.

## Optional upstream plan (omh / AGENTS.md / other)

If the conversation already contains a structured plan (from omh, a written AGENTS.md, or any planner), **consume it as step 2's input** — do not re-plan. If none exists, the mini-plan above suffices. The skill never requires a planner to function.

## Context management (keeps weak models on track)

- Prefer `search_files` / `read_file` (paged) over dumping whole trees.
- Before editing, read only the files the change touches + their direct callers.
- If context is large, summarize completed steps into a short status line and drop old tool output.
- Respect `.gitignore` and project rule files (AGENTS.md / .hermes.md / CLAUDE.md) when present.

## Quick start for the user

1. Drop `hermes-code-agent/` into `~/.hermes/skills/` (or your Hermes skills dir). **That's it — zero config.**
2. In chat: "build X", "fix bug in Y", "refactor Z" — the loop runs automatically. Safety rules and test/lint commands are built-in.
3. (Optional) If you want project-specific overrides (e.g. a non-standard test command or extra conventions), copy `templates/AGENTS.md` into that repo and edit it. **This step is NOT required** — the skill auto-detects commands and enforces safety on its own.

See `ROADMAP.md` for the project's intent and the `references/` folder for command templates.
