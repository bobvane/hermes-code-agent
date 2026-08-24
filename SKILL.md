---
name: hermes-code-agent
description: "Use when the user wants to build, fix, refactor, or verify software in a repo. Wraps Hermes's coding tools in a hard verify-loop (implement → test/lint → fix → only green is done) and orchestrates the existing general dev skills as stage workers. Model-agnostic, plan-source-agnostic, works with or without an upstream planner (omh/AGENTS.md/raw instruction)."
version: 0.2.0
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

Inspired by OpenCode (primary reference: model-agnostic harness + LSP-style feedback loop + subagent fan-out) and OpenAI Codex CLI (secondary: headless `exec`, approval modes, isolated subagents).

## What this skill is NOT

- NOT a rewrite of TDD / debugging / code-review skills. It **orchestrates** them as stage workers. Single source of truth stays with those skills.
- NOT bound to any planner (omh / AGENTS.md / company flow). Those are **optional upstreams**. A raw instruction works fine.
- NOT bound to any framework it shouldn't be. Runs on plain Hermes, any model, any repo.

## The hard loop (the only non-negotiable)

Every implementation task goes through this. The agent must NOT report "done" until the gate is green.

```
1. CLARIFY SCOPE   — what file(s)/behavior change? what does "done" mean (test? lint? run)?
2. PLAN (small)    — if no upstream plan present, write a 3-5 step mini-plan. One change per step.
3. IMPLEMENT       — edit the smallest set of files. Use patch where possible.
4. VERIFY          — run the project's test/lint/build. Capture real output.
5. LOOP ON RED     — if red, feed the EXACT error back, fix, re-run. Max 5 red→fix cycles per step.
6. GATE            — only when ALL checks green AND scope met → mark step done.
7. REPEAT for next step. Then report: what changed, what's green, what's untested.
```

**Gate rule (must be explicit in your reasoning):** "not green = not done." Never summarize past a red check. If a check is unavailable, say so and downgrade confidence — do not fake green.

## Stage workers (call these, don't duplicate them)

When the step needs it, load the matching skill instead of re-inventing instructions:

| Need | Load |
|---|---|
| Writing tests before code | `test-driven-development` |
| Root-causing a bug | `systematic-debugging` |
| Pre-commit quality / security | `requesting-code-review` |
| Cleaning recent diffs | `simplify-code` |
| Parallel implement + review | `delegate_task` (one builder + one reviewer, isolated contexts) |

If the skill is not installed, fall back to the behavior described inline — do not block.

## Advanced patterns (distilled from OpenCode & Codex CLI)

These came from reading the open-source agents (see `references/inspiration.md`). They are defaults, not options.

1. **Delegate by default for non-trivial tasks.** Do not implement + review in the same head. Use `delegate_task`: one builder agent (isolated context) + one reviewer agent, run in parallel, then reconcile. Matches OpenCode's Task-tool fan-out and Codex's `multi_agents_v2` (spawn → send_message → wait → interrupt).
2. **Per-step model hint (where setup allows).** If the user's Hermes config has more than one model, prefer a stronger model for planning/architecture steps and a cheaper one for mechanical edit/execute steps. OpenCode does this via a per-agent `model` field; we approximate via profile/provider swap at step boundaries.
3. **Command-segment approval.** When about to run a shell command, split it at shell operators (`|`, `&&`, `||`, `;`, subshells) and evaluate EACH segment for danger. Destructive segments (`rm`, `git reset --hard`, `drop`, force flags) ALWAYS require explicit user confirm — never auto-approve, never persist a broad approval rule for them. Borrowed from Codex's `approval_policy` state machine.
4. **Bound the loop.** Set a step cap per task (e.g. 3-5 steps) and a red→fix cap (5 cycles). Prevents runaway. OpenCode encodes this via a `steps` field; we enforce it in the loop above.

## Approval modes (borrowed from Codex CLI)

Pick by task risk. Default to `auto-edit` for local repos you trust.

- **suggest** — propose changes, ask before editing. Use for unfamiliar/prod repos.
- **auto-edit** — edit + run read-only checks freely; stop only on destructive ops (push, force, delete).
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
