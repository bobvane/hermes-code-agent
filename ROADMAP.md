# Hermes Code Agent — Roadmap

> **Hermes 代码助手 — 开发路线图**
> 项目说明以中文为主体，英文为辅助参考。

## What it is / 这是什么

A packaging of a **self-correcting coding workflow** as a Hermes skill. The insight: coding agents (Claude Code, OpenCode, Codex, Cline) feel "strong" not because of the model alone, but because they wrap the model in a **narrow tool loop with real feedback** (run → see error → fix → re-run). This skill gives Hermes that same loop, so a mid/weak model performs far above its bare-chat level.

## Why not just use the existing dev skills?

Hermes already ships `test-driven-development`, `systematic-debugging`, `requesting-code-review`, `simplify-code`. Those are **soft constraints** — the model must remember to obey them each turn. Weak models drift. This skill is the **hard shell** that forces the loop every time and routes to those skills as stage workers, so the discipline is structural, not advisory.

## Reference targets (decided 2026-08-24)

- **Primary: OpenCode** (MIT, ~172K★). Model-agnostic harness — same genes as Hermes. We study its architecture: LSP diagnostics fed back to the model, git snapshots (undo/redo), subagent fan-out, multi-surface (TUI/desktop/IDE).
- **Secondary: OpenAI Codex CLI** (Apache-2.0). Borrow three patterns only: headless `exec` (CI-style gate), approval modes (suggest/auto-edit/full-auto), isolated subagents. Do NOT copy its OpenAI-first architecture — that would poison Hermes's model-agnosticism.
- Claude Code is the overall best but **proprietary** — out of scope as a code reference; we only mirror its loop shape at the prompt level.

## Architecture (single source of truth rule)

```
upstream plan (optional: omh / AGENTS.md / raw instruction)
        │
        ▼
hermes-code-agent  ── orchestrates ──►  existing dev skills (stage workers)
 (hard verify loop)                      TDD / debug / review / simplify / delegate
        │
        ▼
 green gate  ──►  done
```

The skill **never rewrites** what the stage-worker skills already define. It calls them. This keeps one source of truth and avoids drift.

## Generality red lines (must hold for every release)

1. Self-sufficient hard loop — no external dependency to function.
2. Plan input is optional — runs from a raw instruction by default.
3. No private/workflow-specific commands hardcoded (omh etc. are optional upstreams, not requirements).
4. No fixed model — uses Hermes's default model (matches repo owner's standing rule).

## Scope & non-goals

- In scope: a deployable skill (`SKILL.md` + templates + docs) that lifts Hermes's coding reliability to parity with popular agents on similar models.
- Out of scope (future, separate projects): a real program-enforced gate (Hermes plugin / ACP server with hard locks), deeper IDE integration (live diagnostics, goto-def). Tracked below.

## Future directions

- **v0.2**: `references/workflow.md` with language-specific verify commands (node/py/go/rust).
- **v0.3**: delegate_task templates for parallel implement+review baked in.
- **v1.0+**: consider a Hermes plugin / ACP-server variant for true program-level gates.

## Status

- v0.1.0 — initial skill skeleton: hard loop, stage-worker routing, approval modes, context mgmt, optional-plan handling.
- v0.2.0 — distilled OpenCode/Codex mechanisms into SKILL.md: delegate-by-default, per-step model hint, command-segment approval, bounded loop. Added `references/inspiration.md` (source analysis).
- v0.3.0 — prior session: added `references/agent-mechanism-extraction.md` (mechanism notes) + `scripts/make_bugbench.py` (benchmark harness). *(Published without a report to user; recorded here for continuity.)*
- v0.4.0 — added `references/benchmark.md` (weak-model loop validation, honest limits) and `references/parallel-implement-review.md` (reusable builder+reviewer delegate_task prompts); SKILL.md links both; version bumped to 0.4.0.
- v0.5.0 — **Codex read at equal depth and cross-validated with OpenCode**. Rewrote `inspiration.md` (symmetric analysis + comparison table). SKILL.md gains: explicit Plan/Build mode split (Codex ModeKind), budget ceiling (Codex Token/RolloutBudget), low-risk self-review (Codex Guardian), all reinforced.
- v0.6.0 — distilled **4 more agents** (Aider, Cline, Gemini CLI, Pi) into `references/extra-distillation.md`. OpenCode remains primary. SKILL.md adds: repo map before edits (Aider PageRank), per-step checkpoint (Cline), model-aware context (Gemini); Pi = architectural confirmation. Version 0.5.0 → 0.6.0.

## 状态更新（中文主体 / Status updates）

- **v0.7.0** — 固化 benchmark 测试框架：`benchmarks/README.md`（测试约定 + 复现命令 + 对比维度）与 `benchmarks/test_cache_param.py`（7 个边界 pytest 裁判，参数化 impl_a/impl_b）。记录 hy3-free 弱模型对比结论，供后续中/强模型对照。
- **v0.8.0** — 强模型实测：切 claude-sonnet-4.5 跑新题（LRU+TTL 线程安全缓存）。A 组裸写 7/7 一次全对，B 组硬循环 7/7 首轮全绿零修复。删除旧题（并发 KV 缓存）固化，只留新题。结论：强模型下 Skill 边际价值趋零。
- **v0.9.0** — 补测 hy3-free 同题（LRU+TTL）数据，修正跨题对比方法论。新增「严格同题对比」：hy3-free 与 claude-sonnet-4.5 同跑 LRU+TTL 均 7/7 / 红修=0。结论修正为：Skill 价值由「模型档次 × 题目难度」交互决定，非单纯模型档次。

## 当前版本 / Current version

**v0.9.0**（SKILL.md frontmatter 已同步）。项目说明文件（README / ROADMAP / SKILL.md / benchmarks/README.md）均以中文为主体，英文为辅助参考。

## 下一步（建议 / Next steps, optional）

- 将 Skill 实际安装进 `~/.hermes/skills/` 让用户在真实编码中验证（之前为做 A/B 对比暂未安装）。
- v1.0+：评估 Hermes 插件 / ACP-server 变体，实现程序级硬门禁（而非仅 prompt 层约束）。
