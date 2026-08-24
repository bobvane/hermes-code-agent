# Inspiration extraction — OpenCode & Codex CLI

Reverse-engineering-by-reading (both are open source: OpenCode MIT, Codex Apache-2.0).
Goal: pull the *mechanisms* that make these agents strong into `hermes-code-agent`.
Both are read at equal depth and cross-validated below.

## 1. OpenCode (primary reference) — `packages/opencode/src/agent/`

### 1.1 Agent as structured config, not a prompt blob
`agent.ts` defines `Info` schema:
- `mode: "subagent" | "primary" | "all"` — lets one config declare a primary agent + subagents.
- `permission` ruleset per agent — fine-grained tool allow/ask/deny.
- `model` per agent (providerID + modelID) — **per-agent model selection** (cheap model to execute, strong model to plan).
- `steps` — bounded step count (prevents runaway loops).

**Takeaway for us:** our `delegate_task` already does multi-agent. We should explicitly model "planner = strong model, executor = cheap model" when the user's setup allows. Add a note in SKILL.md.

### 1.2 Permission defaults are deny-by-escalation
`agent.ts` builds `readonlyExternalDirectory` = `*` → "ask", with whitelisted dirs (tmp, skill dirs, reference dirs) → "allow". Default posture is **ask, not allow**.

**Takeaway:** our approval modes already cover this. Reinforce: default `auto-edit` still stops on destructive ops; align with OpenCode's "ask outside whitelist".

### 1.3 Subagent fan-out via Task tool
`generate.txt` shows the model is *instructed with examples* to launch subagents (e.g. `greeting-responder`) instead of answering directly. The harness makes delegation the default pattern, not an afterthought.

**Takeaway:** make `delegate_task` (implement + review in parallel) the *default* for non-trivial tasks in our skill, not optional.

## 2. OpenAI Codex CLI (equal-depth reference) — `codex-rs/core/src/`

### 2.1 ModeKind: plan vs execute separation
`context/world_state/collaboration_mode.rs` selects a different system-prompt bundle per `ModeKind::Default` vs `ModeKind::Plan`. Planning and executing are distinct cognitive modes with distinct instructions.

**Takeaway:** our skill should make the PLAN step explicit and separate from the BUILD step, using a different instruction tone for each (plan = explore + decide; build = minimal edit + verify). Already partially in the loop; now intentional.

### 2.2 Guardian: autonomous approval review (fail-closed)
`guardian/mod.rs` — when a command needs `on-request` approval, Codex spins up a **separate guardian review session** that reconstructs a compact transcript, assesses the exact planned action, and returns strict allow/deny JSON. **It fails closed** on timeout/failure/malformed output.

**Takeaway:** for `auto-edit` mode, we can route repeated/low-risk approvals through a quick self-review (re-state the action + risk, deny if ambiguous) instead of always pinging the user. Destructive ops never go to guardian — they stay human. This is smarter than our current "always ask".

### 2.3 TokenBudget + RolloutBudget: hard cost ceiling
`session/token_budget.rs` + `session/rollout_budget.rs` — a per-session token/rollout budget. When exceeded, `record_rollout_budget_usage` returns `SessionBudgetExceeded` and the turn terminates. Prevents runaway spend on a stuck weak model.

**Takeaway:** add an explicit budget cap to our loop (e.g. max tokens or max tool-calls per task). On exceed → stop, report blocker. This is the Codex-level guard against the "weak model loops forever" failure we noted in benchmark.md.

### 2.4 Skills system + AGENTS.md
`core/src/skills.rs` + `agents_md.rs` — Codex has its own skill loader (explicit @mention + implicit detection) and reads nearest `AGENTS.md` as project rules. Same shape as our skill + AGENTS.md template.

**Takeaway:** confirms our AGENTS.md approach is industry-standard; keep it.

### 2.5 Remote compaction
`compact_remote_v2.rs` — offloads context compaction to a separate model call (keeps main context small). OpenCode only has local `compaction.txt`.

**Takeaway (future):** if Hermes context gets large mid-task, a delegated compaction pass is cleaner than inline. Not urgent; note for v1.0+.

## 3. Cross-validation: what each does better

| Mechanism | OpenCode | Codex | What we adopt |
|---|---|---|---|
| Multi-agent | Task tool fan-out | multi_agents_v2 isolated | delegate_task (both agree) |
| Plan/exec split | implicit in prompts | explicit ModeKind | explicit plan step (Codex clearer) |
| Approval | ask-outside-whitelist | Guardian fail-closed | ask + optional self-review (Codex) |
| Cost guard | `steps` field | Token/RolloutBudget | step cap + token/tool cap (both) |
| Model per role | per-agent `model` | per-turn model | per-step hint (OpenCode) |
| Compaction | local | remote v2 | local for now |
| Project rules | AGENTS.md | AGENTS.md | AGENTS.md (both) |

**Conclusion:** the two agents independently converge on the same skeleton (loop + feedback + delegation + budget + rules). That convergence *is* the proof the skeleton is correct. Differences are tuning: Codex is stronger on safety (Guardian) and cost-control (budget); OpenCode is cleaner on model-per-role. We take the union.

## 4. Gaps to close in hermes-code-agent
1. Make delegation default (OpenCode + Codex agree).
2. Per-step model hint (OpenCode).
3. Command-segment approval + optional self-review for low-risk (Codex Guardian).
4. Bounded steps + token/tool budget cap (both).
5. Explicit plan step vs build step separation (Codex ModeKind).
6. AGENTS.md as project rules (both).

Implemented incrementally: v0.2.0 (1-4 distilled), v0.3.0 (parallel template), v0.5.0 (5 + 2/3/4 reinforced).
