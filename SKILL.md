---
name: hermes-code-agent
description: "Use when the user wants to build, fix, refactor, or verify software in a repo. Wraps Hermes's coding tools in a hard verify-loop (implement → test/lint → fix → only green is done) and orchestrates the existing general dev skills as stage workers. Model-agnostic, plan-source-agnostic, works with or without an upstream planner (omh/AGENTS.md/raw instruction)."
version: 0.5.0
author: bobvane
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [coding, agent, tdd, workflow, dev, automation]
    homepage: https://github.com/bobvane/hermes-code-agent
---

# Hermes Code Agent

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

## Advanced patterns (distilled from OpenCode & Codex CLI, cross-validated)

These came from reading both open-source agents at equal depth (see `references/inspiration.md`). They are defaults, not options.

1. **Delegate by default for non-trivial tasks.** Do not implement + review in the same head. Use `delegate_task`: one builder agent (isolated context) + one reviewer agent, run in parallel, then reconcile. Use the reusable prompts in `references/parallel-implement-review.md`. Both OpenCode (Task tool) and Codex (multi_agents_v2) converge on this.
2. **Per-step model hint (where setup allows).** If the user's Hermes config has more than one model, prefer a stronger model for PLAN/architecture steps and a cheaper one for BUILD/execute steps. OpenCode does this via a per-agent `model` field; we approximate via profile/provider swap at step boundaries.
3. **Command-segment approval + low-risk self-review.** Split shell commands at operators (`|`, `&&`, `||`, `;`, subshells) and evaluate EACH segment. Destructive segments (`rm`, `git reset --hard`, `drop`, force flags) ALWAYS need explicit user confirm — never auto-approve. For *non-destructive, repeated* approvals in `auto-edit` mode, apply a quick self-review (re-state the action + risk; deny if ambiguous) instead of pinging the user every time — borrowed from Codex's Guardian (fail-closed) pattern; destructive ops never go to self-review.
4. **Bound the loop + budget.** Step cap (3-5), red→fix cap (5/step), and a soft tool-call cap (~40). On exceed → stop, report blocker. OpenCode encodes this via a `steps` field; Codex via Token/RolloutBudget. We enforce both.

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

1. Drop `hermes-code-agent/` into `~/.hermes/skills/`.
2. (Optional) copy `templates/AGENTS.md` into your repo to set project rules.
3. In chat: "build X", "fix bug in Y", "refactor Z" — the loop runs automatically.

See `ROADMAP.md` for the project's intent and the `references/` folder for command templates.
