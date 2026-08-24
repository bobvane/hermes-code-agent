# Hermes Code Agent

Make Hermes a self-correcting coding agent. A packaging of the verify-before-done loop that powers tools like OpenCode / Claude Code / Codex — as a plain Hermes skill, model-agnostic and planner-agnostic.

## Why

Coding agents feel "strong" not because of the model alone, but because they wrap the model in a **narrow tool loop with real feedback**: edit → run → see error → fix → re-run. A mid/weak model inside that loop performs far above its bare-chat level. This skill gives Hermes the same loop.

It does **not** replace Hermes's existing dev skills (`test-driven-development`, `systematic-debugging`, `requesting-code-review`, `simplify-code`). It **orchestrates** them as stage workers, so the discipline is structural, not advisory.

## Install

```bash
git clone https://github.com/bobvane/hermes-code-agent.git
mkdir -p ~/.hermes/skills
cp -r hermes-code-agent ~/.hermes/skills/
```

Optional: copy the project-rules template into your repo:
```bash
cp ~/.hermes/skills/hermes-code-agent/templates/AGENTS.md ./AGENTS.md
```

## Use

In any Hermes chat, just describe the work:
- "build a FastAPI auth service"
- "fix the bug in src/parser.py"
- "refactor the auth module"

The agent will run the hard loop automatically: clarify → plan → implement → verify → loop on red → green gate.

## How it compares to the big names

| Tool | Open | Model | Role here |
|---|---|---|---|
| OpenCode | MIT | 75+ (agnostic) | **Primary reference** — harness architecture |
| OpenAI Codex CLI | Apache-2.0 | OpenAI-first | Secondary — `exec`/approval/subagent patterns |
| Claude Code | proprietary | Claude | Loop shape only (not a code reference) |
| **Hermes Code Agent** | MIT | **any (Hermes default)** | the skill you're installing |

## Design red lines (generality)

1. Self-sufficient hard loop — works with no external dependency.
2. Plan input optional — runs from a raw instruction by default.
3. No private-workflow commands hardcoded (omh etc. are optional upstreams).
4. No fixed model — uses Hermes's default.

## Links

- Repo: https://github.com/bobvane/hermes-code-agent
- Roadmap: see `ROADMAP.md`

## License

MIT — see `LICENSE`.
