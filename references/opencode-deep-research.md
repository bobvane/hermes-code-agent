# OpenCode 深度源码研究 — 验证循环之外的隐藏优势 (v1.1.0 候选)

> 2026-08-25 深度研究：克隆 `sst/opencode` 源码逐文件阅读 + 6 篇技术文章交叉验证。
> 目的：找出「硬验证循环」之外，OpenCode 编程厉害的**其他原因**，作为本 Skill 后续迭代方向。

---

## 一、源码实证的隐藏机制（我们 Skill 还没有的）

### 1. Doom Loop 检测（死循环熔断）— `session/processor.ts`
**机制**：`DOOM_LOOP_THRESHOLD = 3`。如果模型**连续 3 次**用**完全相同的输入**调用同一个工具（JSON.stringify(input) 全等），权限层自动弹出 `doom_loop: "ask"` 确认——打断死循环，交给用户裁决。

**为什么重要**：弱模型最常见的失败不是"写错代码"，而是"同一个错法反复重试"。我们的 Skill 只有"5 轮 red→fix 上限"，但没检测**同一步内**的重复无效操作。OpenCode 的检测粒度是"单工具 × 相同参数 × 连续 N 次"，比轮次上限更精准。

**吸收方案**：Skill 硬循环加一条规则——"若连续 3 次对同一文件做相同编辑且结果相同，STOP，换方法或报告阻塞"。

### 2. 编辑即反馈：LSP 诊断直接回灌 — `tool/edit.ts`
**机制**：每次 Edit/Write 工具执行后，**同步**做三件事：
```
写入 → format.file() 自动格式化 → lsp.diagnostics() 拉取诊断
     → 有错误则把 "LSP errors detected in this file, please fix:\n..." 追加到工具输出
```
模型在**同一轮**就看到类型错误/未定义变量，立刻自修。技术文章证实（agenticloopsai.substack.com 实测记录）：模型因 LSP 反馈在会话中途中改了实现策略。

**为什么重要**：这是比 pytest 更快的反馈环。pytest 要等整个模块写完，LSP 是**每次编辑后毫秒级**反馈。反馈越快，红→修循环成本越低。

**吸收方案**：Hermes 无内置 LSP，但可以近似：Python 用 `python -m py_compile <file>`、TS 用 `npx tsc --noEmit` 单文件检查，作为 BUILD 步骤后的**即时轻量校验**（在完整 VERIFY 之前）。零 LSP 也能拿到语法级反馈。

### 3. 编辑后自动格式化 — `format.file()`
**机制**：Edit 工具写完立即调 formatter（prettier/gofmt 等），保证落盘代码始终符合项目风格。

**价值**：消除一类低级红——格式错误导致的 lint 失败。模型的红→修预算留给真正的逻辑 bug。

**吸收方案**：BUILD 步骤规则加一条："编辑 Python 后跑 `ruff format --check` 或项目 formatter；有 formatter 的项目先格式化再验证"。成本低，减少无谓红轮。

### 4. Snapshot 影子 Git（每步可回滚）— `snapshot/index.ts`
**机制**：独立的 snapshot 服务，用真实 git 实现：`track()` 在每次工具调用前打快照 hash，`restore(hash)` / `revert(patches)` 可精确回到任意步骤。快照保留 7 天，单仓上限 2MB patch。

**价值**：不只是"撤销"，是**让模型敢做大改动**——知道任何一步都能回退。Cline 的 shadow-git 同理（已在 SKILL.md pattern 6），但 OpenCode 的实现证明这应该是**harness 层强制**而非提示词建议。

**吸收方案**：现有 pattern 6 已覆盖思路，升级为硬规则："BUILD 第一个编辑前必须 `git stash create` 或确认工作区干净可 revert；不可 revert 的仓库先建 git init"。

### 5. LLM 调用层重试（指数退避 + retry-after 尊重）— `session/retry.ts`
**机制**：`RETRY_MAX_RETRIES=5`，初始延迟 2s，退避因子 2，抖动 25%；识别 ~15 种可重试错误模式（429/5xx/网络/超时）；**优先读响应头的 retry-after-ms/retry-after**。

**价值**：这正是本次题 C 实测中 OmniRoute 流式波动的解药！我们实测时 OpenCode/Aider 因 500 波动直接失败——但 OpenCode 自己有重试层（可能因非流式长输出超了它的重试预算）。我们 Skill 调 API 时也应内建这个策略。

**吸收方案**：gen.py 式的直接 API 调用加：识别 429/5xx/network 错误 → 最多 5 次指数退避（2s→4s→8s→16s→32s）→ 尊重 retry-after 头。固化到 SKILL.md VERIFY 基础设施节。

### 6. 自动压缩（Compaction）— `session/compaction.ts`
**机制**：三层防护：
- `overflow.ts`: token 总量 ≥ context - reserved(20k buffer) 时触发 auto compaction
- 压缩策略：保留最近 turn（2k-15k tokens 自适应），更早的内容由模型生成摘要替换
- **工具输出修剪**：`TOOL_OUTPUT_MAX_CHARS = 2000`——旧工具输出超过 2000 字符就截断（skill 类工具豁免）

**价值**：长任务不崩。弱模型上下文小，这条尤其关键——我们实测题 C 失败部分原因就是长输出+长上下文。

**吸收方案**：SKILL.md Context management 升级为量化规则："VERIFY 输出超过 2000 字符只保留错误摘要行；每个 step 结束把已完成内容压成一行状态"。（已有 advisory，需加数字阈值）

### 7. Plan 模式是权限隔离而非仅提示词 — `agent/agent.ts`
**机制**：plan agent 通过 permission 规则集**禁止所有编辑工具**（`edit: {"*": "deny"}`），只能写 `.opencode/plans/*.md`。"不能改代码"是 harness 强制的，不靠模型自觉。

**吸收方案**：我们 PLAN 步骤目前靠提示词纪律（"Do NOT edit code in this step"）。Hermes 层面无法禁工具，但可以在 SKILL.md 把它升格为**验证规则**："PLAN 结束后 diff 工作区，若有变更说明违反了 plan/build 分离，回滚并重新规划"。

### 8. 子 Agent fan-out（Task tool）— `tool/task.ts` + `task.txt`
**机制**（我们要补的核心能力）：
- 内置 subagent 类型：`general`（通用多步任务，**明确写了"execute multiple units of work in parallel"**）、`explore`（只读探索）
- 提示词工程精髓（task.txt）：
  - "**Launch multiple agents concurrently whenever possible**, use a single message with multiple tool uses"
  - "do not duplicate that work yourself"——委派后主 agent 不重复劳动
  - task_id 支持**恢复同一子 agent 会话**（延续上下文）
  - "Clearly tell the agent whether you expect it to write code or just to do research"
- 后台模式：background=true 异步启动立即返回，完成后通知

**与 Hermes 的对接**：Hermes 的 `delegate_task` 就是现成的 fan-out 原语（支持 tasks[] 批量并行、steer 中途纠偏、isolated context）。我们缺的是 **SKILL.md 里把它编入硬循环**：
- BUILD 阶段多文件任务 → 按文件拆给多个 builder 并行
- VERIFY 前的探索 → explore 型 delegate（只读）
- review → 已有 pattern 1

**落地草案（v1.1.0）**：新增 SKILL.md 章节 "Parallel execution (fan-out)"：
1. 触发条件：≥2 个互不依赖的文件级修改，或需要大范围探索
2. 拆分原则：每个子任务的 prompt 必须自包含（子代理看不到主对话）+ 明确产出物 + 明确验证命令
3. 编排：builder×N 并行 + reviewer×1 收敛；冲突文件绝不并行
4. 结果合并：主 agent 只做 reconcile，不重复实现
5. 上限：并行度 ≤3（防 OmniRoute 并发限流，呼应 ≤2 经验值）

---

## 二、技术文章交叉验证的结论

| 来源 | 佐证 |
|---|---|
| cefboud.com 深度解析 | Plan/Build 双 agent + LSP 反馈环是核心；subagent 即 planning 的载体 |
| agenticloopsai 实测 | "Rich tool results turn tool calls into feedback loops"——LSP 错误导致模型中途换实现策略 |
| foojay.io | OpenCode 内置 30+ LSP server；LSP = 结构性反馈，规格 = 意图清晰，两者夹击缩小偏差 |
| arxiv 2603.05344 | 学术佐证：harness 负责 dispatch tools/compact context/enforce safety/persist state 四件事；LSP 只取 Error 级别、上限 20 条防噪音 |
| Oracle blog 三层 loop | Level 3 = 显式 feedback instrumentation——我们的 verify-loop 在 L2，LSP/doom-loop/fan-out 是 L3 特征 |

**综合判断**：OpenCode 的强 = 硬验证循环（我们已有）+ **高频结构化反馈**（LSP/格式化，我们没有）+ **死循环熔断**（没有）+ **真并行 fan-out**（有原语没编排）+ **基础设施韧性**（重试/压缩/快照，部分有）。前三者是 v1.1.0 最值得补的。

## 三、v1.1.0 迭代清单（按性价比排序）

| # | 项 | 成本 | 收益 |
|---|---|---|---|
| 1 | Doom-loop 规则（同参同工具×3 → STOP） | 低（纯提示词） | 高（直击弱模型最常见失败） |
| 2 | 轻量语法校验进 BUILD（py_compile/tsc --noEmit） | 低 | 高（反馈周期从"整模块"缩到"单文件"） |
| 3 | API 重试策略固化（指数退避+retry-after） | 低 | 高（题 C 已证明痛点） |
| 4 | Fan-out 编排章节（delegate_task 编入硬循环） | 中 | 高（多文件任务提速+质量） |
| 5 | 编辑后 formatter 规则 | 低 | 中 |
| 6 | Compaction 数字阈值 | 低 | 中 |
| 7 | PLAN 后 diff 验证分离纪律 | 低 | 中 |

## 附：信息来源
- 源码：github.com/sst/opencode（packages/opencode/src/{agent,session,tool,snapshot}，浅克隆已删）
- 文章：cefboud.com/posts/coding-agents-internals-opencode-deepdive；agenticloopsai.substack.com "Disassembling AI Agents Part 3"；foojay.io LSP best practices；arxiv.org/html/2603.05344v1；codexpedite.com 两篇；medium @gaharwar.milind
