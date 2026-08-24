# Inspiration extraction — OpenCode & Codex CLI

Reverse-engineering-by-reading (both are open source: OpenCode MIT, Codex Apache-2.0).
Goal: pull the *mechanisms* that make these agents strong into `hermes-code-agent`.

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

## 2. OpenAI Codex CLI (secondary) — `codex-rs/core/src/`

### 2.1 Execution limiter / capacity guard
`control/execution.rs` — `AgentExecutionLimiter` caps concurrent subagent turns (`max_threads`, `AgentExecutionGuard` RAII). Prevents fork bombs.

**Takeaway:** when we fan out via `delegate_task`, respect a concurrency cap (Hermes already caps children; document the cap we rely on).

### 2.2 Approval as a state machine
`prompts/templates/permissions/approval_policy/` has `never / on_request / unless_trusted / on_request_rule_request_permission`.
- Commands are split at shell operators (`|`, `&&`, `;`, subshells) and **each segment** evaluated independently for sandbox + approval.
- Escalation uses `sandbox_permissions: "require_escalated"` + `justification` — the *agent* must self-request, never message user first.
- `prefix_rule` lets user persist approvals categorically (e.g. `["npm","run","dev"]`), but bans broad prefixes like `["python3"]` and **never** for destructive (`rm`).

**Takeaway:** our approval modes map cleanly:
- `suggest` ≈ `never` + ask
- `auto-edit` ≈ `unless_trusted`
- `full-auto` ≈ `on_request` (trusted)
We should add the "split command at shell operators, evaluate each segment" rule to our destructive-op guard.

### 2.3 Multi-agent v2 = isolated contexts
`tools/handlers/multi_agents_v2/` — `spawn / send_message / wait / list_agents / interrupt_agent / followup_task`. Subagents get isolated sessions, explicit message passing, and can be interrupted. This is the same pattern as Claude Code's fan-out.

**Takeaway:** our `delegate_task` children are already isolated. Document the spawn→message→wait→interrupt lifecycle as the canonical parallel pattern.

## 3. What we already have in Hermes (no code needed)
| Mechanism | OpenCode/Codex | Hermes equivalent |
|---|---|---|
| Tool loop w/ feedback | core loop | terminal/execute_code + patch |
| Subagent fan-out | Task tool / multi_agents_v2 | `delegate_task` |
| Per-agent model | `model` field | Hermes profile / provider swap |
| Approval gate | approval_policy | our approval modes |
| Capacity limit | AgentExecutionLimiter | Hermes child cap |
| Context compaction | `compaction.txt` | Hermes compression |

## 4. Gaps to close in hermes-code-agent
1. **Make delegation default**, not optional, for non-trivial tasks.
2. **Per-step model hint**: planner strong / executor cheap (where setup allows).
3. **Command-segment approval**: evaluate each shell segment; ban broad persisted approvals for destructive cmds.
4. **Bounded steps**: encourage a step cap to prevent runaway.

These become v0.2.0 changes to SKILL.md.
