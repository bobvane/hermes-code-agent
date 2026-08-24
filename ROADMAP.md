# Hermes Code Agent — 開發路線圖

> **Hermes 代码助手 — 开发路线图**
> 项目说明以中文为主体，英文为辅助参考。

## 这是什么 / What it is

A packaging of a **self-correcting coding workflow** as a Hermes skill. The insight: coding agents (Claude Code, OpenCode, Codex, Cline) feel "strong" not because of the model alone, but because they wrap the model in a **narrow tool loop with real feedback** (run → see error → fix → re-run). This skill gives Hermes that same loop, so a mid/weak model performs far above its bare-chat level.

## 为什么不用现有 dev skills / Why not just use the existing dev skills?

Hermes already ships `test-driven-development`, `systematic-debugging`, `requesting-code-review`, `simplify-code`. Those are **soft constraints** — the model must remember to obey them each turn. Weak models drift. This skill is the **hard shell** that forces the loop every time and routes to those skills as stage workers, so the discipline is structural, not advisory.

## 參考對象 / Reference targets (decided 2026-08-24)

- **Primary: OpenCode** (MIT, ~172K★). Model-agnostic harness — same genes as Hermes. We study its architecture: LSP diagnostics fed back to the model, git snapshots (undo/redo), subagent fan-out, multi-surface (TUI/desktop/IDE).
- **Secondary: OpenAI Codex CLI** (Apache-2.0). Borrow three patterns only: headless `exec` (CI-style gate), approval modes (suggest/auto-edit/full-auto), isolated subagents. Do NOT copy its OpenAI-first architecture — that would poison Hermes's model-agnosticism.
- Claude Code is the overall best but **proprietary** — out of scope as a code reference; we only mirror its loop shape at the prompt level.

## 架構 / Architecture (single source of truth rule)

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

## 通用性原則 / Generality red lines (must hold for every release)

1. Self-sufficient hard loop — no external dependency to function.
2. Plan input is optional — runs from a raw instruction by default.
3. No private/workflow-specific commands hardcoded (omh etc. are optional upstreams, not requirements).
4. No fixed model — uses Hermes's default model (matches repo owner's standing rule).

## 範圍與非目標 / Scope & non-goals

- In scope: a deployable skill (`SKILL.md` + templates + docs) that lifts Hermes's coding reliability to parity with popular agents on similar models.
- Out of scope (future, separate projects): a real program-enforced gate (Hermes plugin / ACP server with hard locks), deeper IDE integration (live diagnostics, goto-def). Tracked below.

## 版本歷史 / Status

- **v0.1.0** — initial skill skeleton: hard loop, stage-worker routing, approval modes, context mgmt, optional-plan handling.
- **v0.2.0** — distilled OpenCode/Codex mechanisms into SKILL.md: delegate-by-default, per-step model hint, command-segment approval, bounded loop. Added `references/inspiration.md` (source analysis).
- **v0.3.0** — prior session: added `references/agent-mechanism-extraction.md` (mechanism notes) + `scripts/make_bugbench.py` (benchmark harness). *(Published without a report to user; recorded here for continuity.)*
- **v0.4.0** — added `references/benchmark.md` (weak-model loop validation, honest limits) and `references/parallel-implement-review.md` (reusable builder+reviewer delegate_task prompts); SKILL.md links both; version bumped to 0.4.0.
- **v0.5.0** — **Codex read at equal depth and cross-validated with OpenCode**. Rewrote `inspiration.md` (symmetric analysis + comparison table). SKILL.md gains: explicit Plan/Build mode split (Codex ModeKind), budget ceiling (Codex Token/RolloutBudget), low-risk self-review (Codex Guardian), all reinforced.
- **v0.6.0** — distilled **4 more agents** (Aider, Cline, Gemini CLI, Pi) into `references/extra-distillation.md`. OpenCode remains primary. SKILL.md adds: repo map before edits (Aider PageRank), per-step checkpoint (Cline), model-aware context (Gemini); Pi = architectural confirmation. Version 0.5.0 → 0.6.0.
- **v0.7.0** — 固化 benchmark 测试框架：`benchmarks/README.md`（测试约定 + 复现命令 + 对比维度）与 `benchmarks/test_ttlcache.py`（7 个边界 pytest 裁判，参数化 impl_a/impl_b）。记录 hy3-free 弱模型对比结论，供后续中/强模型对照。
- **v0.8.0** — 强模型实测：切 claude-sonnet-4.5 跑新题（LRU+TTL 线程安全缓存）。A 组裸写 7/7 一次全对，B 组硬循环 7/7 首轮全绿零修复。删除旧题（并发 KV 缓存）固化，只留新题。结论：强模型下 Skill 边际价值趋零。
- **v0.9.0** — 补测 hy3-free 同题（LRU+TTL）数据，修正跨题对比方法论。新增「严格同题对比」：hy3-free 与 claude-sonnet-4.5 同跑 LRU+TTL 均 7/7 / 红修=0。结论修正为：Skill 价值由「模型档次 × 题目难度」交互决定，非单纯模型档次。
- **v0.10.0** — 文档收尾：README 改为中文主体 + 英文补充；ROADMAP/SKILL.md 补中文副标题与 v0.7~v0.9 状态；SKILL.md version 对齐到 0.9.0。
- **v0.11.0** — **产品设计修正（零配置）**：根据用户反馈，AGENTS.md 不应是"每个项目复制一次"的必需文件。Skill 现已**内置安全规则 + 自动探测测试/lint/构建命令**，安装一次即可无感使用；AGENTS.md 降级为纯可选覆盖（仅用于覆盖自动探测默认值或加项目专属约定）。templates/AGENTS.md 保留作可选模板，但 Quick start 不再要求复制。CLARIFY 步骤加入"先探测命令再问"。
- **v0.11.1** — **文档口径同步修正**：补改 README 安装段（删除"必须复制 AGENTS.md"引导，改为"零配置、可选覆盖"），使所有文档与零配置设计一致。
- **v1.0.0 — 正式发布 (2026-08-25)**:
  - **文档重写**: SKILL.md/README/ROADMAP/benchmarks/README 重構为中文主体+英文補充, 结构整齐; 3題對比(A KV 缓存 7/7, B TTLCache 6/6, C Async 调度器 5/5) 固化進 benchmarks/README.
  - **结论固化**: Skill 价值由「模型档次 × 题目难度」交互决定; 题 C 驗證 Skill 非流式(stream:false)抗 OmniRoute 波动優勢, OpenCode/Aider 流式失敗.
  - **工程陷阱总结**: 在非交互模式下 coding agent 長输出不穩 (Aider 0 字节 / OpenCode 500), 必須 `stream:false` 才通過; 固化為 Advanced pattern pitfall.
  - **生产就绪**: 安装一次零配置, 硬安全规则+自动探测内置, AGENTS.md 可选.
- **v1.1.0 — 深度源码研究落地 (2026-08-25)**:
  - **研究**: 克隆 sst/opencode 逐文件深读 + 6 篇技术文章交叉验证 → `references/opencode-deep-research.md`.
  - **SKILL.md 新增 4 条硬规则**: Doom-loop 熔断（同参同工具×3→STOP）; 快速语法门（py_compile/tsc 单文件秒级反馈）; API 韧性（指数退避+retry-after+非流式防波动）; **Parallel execution fan-out 章节**（delegate_task 编入硬循环: ≥2 独立文件改动触发、自包含 prompt、N builder+1 reviewer、并发≤3、合并后全量 VERIFY 才 GATE）.
  - **补齐能力**: 子 Agent fan-out（OpenCode Task tool 对标）正式入编.
- **v1.2.0 — 确定性门禁脚本 (2026-08-25)**:
  - **三方评审驱动**: 产品经理（能力差距清单）+ 架构师（scripts=harness 近似）+ 评论家（融合路线+反对清单）共识方案落地.
  - **核心**: `scripts/hca_gate.py` 单入口 CLI — detect/snapshot/plancheck/quickcheck/doomcheck/verify/state 七个子命令; **exit-code 硬阻塞语义**（0=绿/1=红/2=死循环熔断）; `.hca_state.json` 状态外置（对抗会话压缩失忆，含 git HEAD stale 检测）.
  - **散文规则退役入代码**: formatter/compaction 修剪/plan-build 分离从提示词规则编译为脚本必然执行.
  - **自测**: `tests/test_hca_gate.py` 15 用例全绿（含"无测试命令时禁止假绿"、doom 阈值、redfix 计数、stale 检测）.
  - **原则**: 凡能编译成 exit code 的规则绝不留在提示词里；凡需要判断力的规则绝不假装脚本能做.
- **v1.2.1 — guard 反作弊门禁 + 模型门槛声明 (2026-08-25)**:
  - **实证驱动**: 4 组 A/B 实验（laguna-s-2.1 / ministral-8b / qwen3-8b）暴露三类失败模式: 强模型无 harness 假报完成、弱模型上下文崩溃、弱模型篡改裁判凑绿.
  - **guard record|check**: judge/test 文件 sha256 封存, 篡改/删除 → exit 3 + TAMPER 提示; verify 自动执行完整性检查.
  - **verify venv 自举**: runner 缺失时自动尝试 `.venv/bin/python` 重跑, 并输出具体 FIX 命令, 不再让模型盲试.
  - **叙事重构 (四方评审共识)**: 主卖点改为「对一切模型的完成性验证」; 弱模型降级为实验性, 明示支持门槛(编码≥8B激活/通用≥24B).
  - **自测**: 21 用例全绿.

## 當前版本 / Current version

**v1.2.1** (2026-08-25): guard 反作弊门禁(exit 3) + verify venv 自举 + 模型支持门槛声明. 自测 21/21.

## 後續升級目標 / Post-v1.2.1 goals (decided 2026-08-25)

**战略定位**: 只正式支持中强模型（编码特化 ≥8B 激活参数 / 通用 ≥24B），弱模型实验性不担保。目标：让中强模型编程**更准确、成本效率更高**。

**目标体系（四方评审收敛）**:

| 目标 | 定义（可测） | 度量方式 |
|---|---|---|
| 北极星: 难题首过率 | N 道难题上 harness 开启后的首次全绿率 | 固定基准协议 A/B |
| 约束: 成本效率 | tokens/题 + wall-clock/题 + 红→修轮次不劣化 | 同一次基准跑产出 |

- **简洁性降级为约束项**: 只在全绿前提下优化（diff 最小化、simplify-code 集成），不得为简洁牺牲正确性。
- **泛化鲁棒性为观察项**: 跨语言/跨框架稳定性，暂不定指标。
- **方法论红线**: 先基线后改动——用 skill-ab-benchmark 固定协议（固定题集+裁判+N次均值）跑出 v1.2.1 基线数字；之后每版只追一个目标做 A/B，四线并进不可接受。

## 下一步 / Next steps (optional)

1. **基线工程**: 把 skill-ab-benchmark 固化为可重复协议（固定 seed/题集/N 次），跑出 v1.2.1 的首过率与 tokens/题基线，写入 benchmarks/.
2. v1.3+: 以基线为参照逐版验证单目标边际收益；评估 Hermes plugin / ACP-server 程序级硬门禁.
