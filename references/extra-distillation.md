# Extra distillation — Aider, Cline, Gemini CLI, Pi

OpenCode remains the **primary reference** (model-agnostic harness, subagent fan-out,
per-agent model, LSP feedback). Codex is the equal-depth secondary (ModeKind, Guardian,
Token/RolloutBudget). This file captures the *distinctive* mechanisms of four more
high-star open agents that the primary/secondary do NOT cover — the gaps worth absorbing.

All read at source level (cloned under `/opt/data/upstream-analysis/`). Each entry:
what they do uniquely → the mechanism → whether Hermes should absorb it.

## 1. Aider — PageRank repo map (automatic codebase structure awareness)

**Unique:** Aider ships a **repo map** — a graph where each source file is a node, edges
link files by dependency (imports/references). Before *every* LLM call it runs
**personalized PageRank** to rank files by relevance to the current conversation, then
renders the top-ranked symbol definitions (elided to fit a token budget) into the prompt.

**Why it matters:** OpenCode/Codex rely on the model to `search_files`/`read_file` and
*guess* what matters. Aider instead gives the model automatic structural awareness of the
whole repo every turn, without dumping the tree. This is the single biggest context
efficiency win among all agents surveyed.

**Source:** `aider/repomap.py` (`RepoMap.get_ranked_tags_map`), `aider/coders/*.py`.

**Absorb?** YES — but adapt. Hermes has no built-in repo map. We can approximate in the
skill: a **pre-step that builds a lightweight symbol/dependency index** (e.g. `grep` for
`def `/`class `/`import ` + a cheap rank) and feeds the top-N relevant symbols as context
before the model edits. This directly attacks the "weak model gets lost in large repo"
failure noted in benchmark.md. Add to SKILL.md as the CONTEXT step (upgrade of the current
"prefer search_files" advisory into a structured map).

## 2. Cline — Plan/Act + shadow-Git checkpoint + .clinerules

**Unique A — Plan/Act:** explicit mode toggle (explore + lay out strategy in Plan; execute
in Act). Same shape as Codex ModeKind but Cline's is a **user-toggleable UX contract** with
checkpoints.
**Unique B — Checkpoint / undo:** Cline maintains per-step snapshots of file state
(after each tool use) with one-click restore to any earlier step, including untracked
files. (Source: `cline/apps/vscode/src/core/controller/checkpoints/` — restore/picker/
proto components confirm a real snapshot-and-rollback system; exact storage backend not
verified here but the revert UX is first-class.)
**Unique C — `.clinerules`:** ship repo rules as a file (same role as our AGENTS.md /
Codex AGENTS.md — convergent, confirms the pattern).

**Source:** `cline/` extension (`checkpoints/`, `core/`, `.clinerules` handling).

**Absorb?** PARTIAL.
- Plan/Act → already covered by our Plan/Build split (Codex). No change.
- `.clinerules` → same as AGENTS.md. No change (already have template).
- **Shadow-Git checkpoint → YES, worth adopting.** Before any edit in the loop, the skill
  can suggest `git stash`/worktree or a lightweight snapshot so a bad step is reversible.
  Add a "checkpoint before each BUILD step" note. Cheap, high safety, especially for weak
  models that may make a destructive edit.

## 3. Gemini CLI — 1M-token context strategy + GEMINI.md + ReAct loop

**Unique A — Huge context as a strategy:** Gemini CLI leans on a 1M-token window to load
entire repos, trading careful pruning for breadth. Opposite philosophy to OpenCode's
compact-and-trim. For Hermes (model-agnostic, may run small-context models), the *lesson*
is: when the configured model has a large window, prefer broad load + periodic compress
over aggressive pruning; when small, use the Aider-style map. Context strategy should be
**model-aware**.
**Unique B — GEMINI.md:** persistent project context file (again, convergent with
AGENTS.md — industry standard, confirmed 3rd time).
**Unique C — ReAct loop:** reasoning-act-observe iterative loop (same skeleton we use; no
new mechanism, just explicit naming).

**Source:** `gemini-cli/` (`GEMINI.md` loading, context management, tools).

**Absorb?** ONE thing: make the **context strategy model-aware** — if the active model has
a large window, load broadly; if small, use the repo map. Add a note to SKILL.md context
section. GEMINI.md → already covered by AGENTS.md.

## 4. Pi — minimal 4-primitive kernel + extension/skill/prompt-template growth

**Unique:** Pi gives the LLM exactly four tools — `read`, `write`, `edit`, `bash` — and
nothing else baked in. Everything else (skills, prompt templates, themes, slash commands)
is layered via **Extensions** (TypeScript modules sharing the same tool API) and **Skills**.
Philosophy: "adapt Pi to your workflow, not the other way around." Minimal kernel, maximal
extensibility without forking.

**Why it matters for us:** Hermes's `hermes-code-agent` is itself a "skill layered on a
kernel" — Pi validates that approach as first-class. It also suggests our skill should
stay **minimal and composable**, delegating specifics to other skills (which we already do
via stage workers) rather than bloating.

**Source:** `pi/packages/coding-agent/` (tools: read/write/edit/bash; extension loading).

**Absorb?** ARCHITECTURAL CONFIRMATION, not a new feature. Reinforces our existing design
(decision already made): skill = thin orchestrator, not a monolith. No SKILL.md change
needed beyond a one-line acknowledgment. Good to record so we don't drift toward a
fat skill later.

## Cross-agent convergence (now 6 agents)

| Mechanism | OpenCode | Codex | Aider | Cline | Gemini | Pi |
|---|---|---|---|---|---|---|
| Loop + verify | ✓ | ✓ | ✓ | ✓(Act) | ✓(ReAct) | ✓(bash) |
| Plan/exec split | implicit | ModeKind | — | Plan/Act | — | — |
| Subagent fan-out | ✓ | ✓ | — | — | sub-agents | ext |
| Per-role model | ✓ | per-turn | — | — | — | — |
| Budget cap | steps | Token/Rollout | — | — | — | — |
| **Auto repo map** | — | — | **✓ PageRank** | — | — | — |
| **Shadow checkpoint** | /undo | — | — | **✓ shadow git** | — | — |
| **Model-aware ctx** | compact | compact | map | — | **1M load** | — |
| Project rules file | AGENTS.md | AGENTS.md | — | .clinerules | GEMINI.md | — |
| Minimal kernel+ext | — | — | — | — | — | **✓ 4 prims** |

**What we adopt from this round (new, on top of v0.5.0):**
1. **Repo map pre-step** (Aider) — automatic structural context before edits. Biggest win.
2. **Checkpoint before each BUILD step** (Cline shadow-git idea) — reversible edits.
3. **Model-aware context strategy** (Gemini) — broad-load if large window, map if small.
4. **Stay minimal/composable** (Pi) — architectural confirmation, no change.

OpenCode still leads on harness architecture; these four fill specific gaps.
