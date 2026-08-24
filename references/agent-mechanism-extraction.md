# Agent mechanism extraction — worked example (OpenCode + Codex CLI)

Condensed findings from reading the open-source agents (Aug 2026). Goal: pull the
*mechanisms* that make weak models strong into Hermes, not copy code.

## OpenCode (MIT) — `packages/opencode/src/agent/`
- `agent.ts` `Info` schema: `mode: "subagent"|"primary"|"all"`, per-agent `permission`,
  per-agent `model` (providerID+modelID), `steps` (bounded loop). → per-agent model
  selection + bounded steps are first-class, not afterthoughts.
- Default permission posture is deny-by-escalation: `*` → "ask", whitelisted dirs → "allow".
- `generate.txt` instructs the model with EXAMPLES to launch subagents (Task tool) instead
  of answering directly. Delegation is the default pattern.

## OpenAI Codex CLI (Apache-2.0) — `codex-rs/core/src/`
- `agent/control/execution.rs`: `AgentExecutionLimiter` caps concurrent subagent turns
  (RAII guard). Prevents fork bombs. → bounded concurrency.
- `prompts/templates/permissions/approval_policy/`: `never / on_request / unless_trusted /
  on_request_rule_request_permission`. Commands split at shell operators (`| && || ;`
  subshells); EACH segment evaluated independently for sandbox + approval. Escalation via
  `sandbox_permissions:"require_escalated"` + `justification`; `prefix_rule` lets user
  persist categorical approvals but bans broad prefixes (`python3`) and NEVER for `rm`.
- `tools/handlers/multi_agents_v2/`: spawn / send_message / wait / list_agents /
  interrupt_agent / followup_task — isolated subagent sessions with explicit messaging.

## What Hermes already has (no code needed)
| Mechanism | Peer agent | Hermes equivalent |
|---|---|---|
| Tool loop w/ feedback | core loop | terminal/execute_code + patch |
| Subagent fan-out | Task / multi_agents_v2 | `delegate_task` (isolated) |
| Per-agent model | `model` field | profile/provider swap |
| Approval gate | approval_policy | approval modes |
| Capacity limit | AgentExecutionLimiter | Hermes child cap |
| Context compaction | compaction.txt | Hermes compression |

## Bugbench validation (how we proved the gain)
1. Make a throwaway repo with 2 intentional bugs + a test suite (see scripts/make_bugbench.py).
2. Confirm baseline: tests RED.
3. Run the coding-workflow skill's HARD LOOP (implement → pytest → red→fix → green gate).
4. Verify: 3 passed, exit 0. The loop forces the weak model to converge instead of
   declaring done on a guess.
Key result: skill gives real lift on small tasks even on a free/weak model; complex
cross-file bugs still need a stronger model — the skill is an amplifier, not a ceiling-raiser.
