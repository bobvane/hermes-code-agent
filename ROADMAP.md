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
- **v1.3.0 — 基准协议 v1 固化 (2026-08-25)**:
  - `benchmarks/protocol.md`: 固定题（嵌套事务+TTL+并发 KVStore, 11 用例裁判）+ guard 封存 + N≥3 + A/B 组定义与判读规则; 工作目录 hca-bench-<date> 测完删除.
  - `benchmarks/baseline-v1.2.1.md` 双轨基线: OxAlpha 轨 B 首过 10.0/11 收敛 3/3, A 首过 10.67 但 1/3 概率隐藏缺陷出货; DeepSeek v4 Flash 轨 B 10.0/11 (n=2), A 均值 9.33 且 a3 仅 6/11. 结论: 强模型价值=完成性保证, 中档模型=首过率+拦截裸交付缺陷.
- **v1.4.0 — Pi 可移植项落地 (2026-08-25)**:
  - verify 输出双限摘要（200 行 + max_chars 字节双 cap, 只保留失败相关行）; tokens≈ 遥测写入 .hca_state.json; 渐进披露精简.
  - 实测 B 组首过 10.75/11 (n=4), 发现遥测记录原始输出而非展示 digest 的 bug → v1.4.1 修复（telemetry = 模型实际付费阅读的内容）.
- **v1.5.0 — 四仓共识第一批落地 (2026-08-25)**:
  - **事务性 snapshot/restore**: git refs/hca/snapshots 快照点, restore 带 cleanliness 校验（快照后新文件删除、快照前改动保留——真事务点语义）; compact 状态压缩 split point; budget_fired 分层软提醒(3000/8000 tok, 同层严格去重).
  - 验证: OxAlpha 轨 B×3 全部首过 11/11 收敛, 三特性实战验证通过.
- **v1.5.1 — detect 优先探测项目 venv python (2026-08-25)**:
  - 验证轮反馈: detect_commands 先探测 `.venv/bin/python`, 消除每轮 verify 的 FileNotFoundError 噪声 (~550 tok/轮).
  - 补测: DeepSeek v4 Flash 中档轨 B×3 — 首过 9.0/11 (11,5,11), b2 撞 5 轮上限未收敛(commit 路径 doom-loop) → 记录为能力天花板并反哺: doomcheck 对"同测试集语义级重复红"缺检测, 列入 v1.6 候选.
- **v1.6.0 — doomcheck 语义级检测 (2026-08-25)**:
  - **实证驱动**: v1.5.1 补测 b2 的 doom-loop——模型对同一 commit 缺陷连续 5 轮盲修, 现有 action-tag doomcheck 检测不到(每轮编辑 tag 都不同).
  - **failure fingerprint**: 每次 verify RED 提取失败测试 id 集合的 sha1 指纹写入 state(`fail_fp`, cap=阈值); **同一失败集连续 3 轮 → exit 2 熔断**, 明示"你在盲修循环, 停止 patch, 回滚快照或换策略".
  - **语义安全**: 集合序无关/计数无关; 失败集一旦变化(有测试被修好)立即重置——真修复不会误触; collection error 等无 FAILED 行场景返回 None 不参与判定.
  - **自测**: tests/test_hca_gate.py 33 用例全绿(新增语义熔断触发+恢复重置用例); bench 目录实战验证: 同坏实现 3 轮 → exit 2 触发, 改动失败集后回到普通 RED.
- **v1.7.0 — 预算超支硬熔断 + 换模型建议 (2026-08-25)**:
  - **实证驱动**: v1.5.1 补测 b2 盲修 5 轮烧掉 ~23.6k token——旧机制只有软提醒, 烧穿预算也不会强制停.
  - **双阈值硬停**: verify digest 累计 ≥15000 tok 或红轮 ≥5 → exit 2 (与 doom 同级), 输出超支原因.
  - **升级建议**: 硬停时向用户明示"当前模型反复无法收敛, 建议换更强模型从最近快照重新开始"——护栏不止于拦截, 还给出路.
- **v1.7.1 — 熔断提示精简 (2026-08-25)**: 换模型建议压缩为中英双行红色(ANSI 1;31)输出: "此模型不胜任此编程任务，建议更换更强模型。" / "This model is unfit for this coding task — switch to a stronger model."
- **v1.8.0 — 四仓共识第二批落地 (2026-08-25)**:
  - **⑥ auto-commit (Aider 式)**: verify 绿后自动落盘 checkpoint commit (`hca: green checkpoint`), 排除 .hca_state.json, 干树/非 git 目录静默跳过——每轮成果可回溯可 revert.
  - **⑤ patch 三级降级 (Codex 式)**: 新 `patch` 子命令按块应用 unified diff: tier1 `git apply` 精确 → tier2 `--ignore-whitespace --unidiff-zero` 容忍空白漂移 → tier3 锚点替换(去空白匹配且全文唯一才动手); 任一块三级全败 → exit 1 RED, 不静默半应用.
  - **④ repomap 轻量仓库图 (Aider 思路, stdlib 实现)**: 新 `repomap` 子命令 grep 式符号统计(def/class/func/fn...), 按符号数排序取 top40, 跳过 node_modules/.venv 等; 不引 tree-sitter/networkx.
  - **⑦ overflow 强制确定性压缩**: trim_output 兜底再压一道——即使单行 50k 字符的病态输出也保证 ≤ max_chars, 中间截断带 `[overflow compressed]` 标记, 无 LLM 无随机.
  - **自测**: tests/test_hca_gate.py 52 用例全绿(四特性各 3-5 用例).

## 當前版本 / Current version

**v2.1.1** (2026-08-28): **自检升级 (self-update check)** — Skill 每次进入编程前静默探一次 GitHub 版本，任务完成后若发现新版本弹 A/B 升级选项（A=立即升级后提示重启网关生效；B=3 天后再提示）。两个节流指针写在 `skill_state.json`（不在项目 `.hca_state.json`）：`last_check_ts` 72h 检测节流 + `next_prompt_ts` 3 天提示节流。网络失败/版本相同均静默，不阻塞主流程。加 4 个子命令：`update-check`（强制/节流）、`update-pending`（任务完成后调用）、`update-status`（调试）、`update-apply`（真正下载覆盖，`skill_state.json` 豁免）。升级过程先备份旧 SKILL.md 到 `backups/`，失败可回滚。

**v2.1.0** (2026-08-27): feature-complete 里程碑 — 六家对标 11/11 功能全部落地（计划/执行分离、测试反馈重试循环、子代理并行、每角色不同模型、步数/花费封顶、并发限制、权限审批分级、危险命令拦截、项目规则文件、仓库结构图、补丁容错应用）。收尾：README 完整重写（安装+机制+对照表+边界）、LICENSE 版权名规范化、清理基准冗余文件；测试套件暂不维护，按需响应问题。

**v2.0.1** (2026-08-26): locate 模糊救援重写——从 difflib 整行序列匹配（探针行与源码行需逐字一致，差一个参数即报"找不到"）改为逐行字符级相似度评分：每条探针行独立找最像的源码行（去缩进后比对+长度门槛加速），无硬阈值——永远报告最佳候选区域+平均相似度+逐行分数明细，判断权交给模型；相似度低时附提示但不阻断。10+2 场景实测全过：子串探针、差参数、缩进漂移、tab/space、多行混合、改名变量、不存在代码、中文行、空探针、文件缺失、apply→locate 真实救援链路。

**v2.0.0** (2026-08-26): 第二批功能落地（三项实施 + 八项砍除）。实施：①项目规则文件两层设计——全局层 `CONVENTIONS.md` 随 Skill 分发（templates/CONVENTIONS.md 六节骨架）+ 项目层 `<项目名>.md` 放项目目录内随项目走，入口检测协议（缺目录/缺规则文件才提问，齐全静默加载），项目层覆盖全局层，首次生成按技术栈代填；②仓库结构图两张索引卡——目录卡（Cline 式列目录树）+ 符号卡（Aider 式 ripgrep 抽 class/def/function 定义行），任务开始出目录卡、挑完相关文件再出符号卡；③补丁容错应用——Codex apply-patch 全量移植：`apply` 子命令实现 seek_sequence 四级匹配引擎（精确→rstrip→trim→Unicode 归一化，逐级降级不跳级）、防御性补丁解析器、ApplyPatchError 结构化错误（PARSE/MATCH/IO + hunk 定位 + expected/actual 对照）、单文件原子写入（任一 hunk 失败整补丁不落盘）、EOF 追加特判。实测通过：四级匹配逐级验证、原子性拒绝、结构化错误回喂、畸形补丁解析报错。砍除（Bob 拍板）：快照回滚、编辑后自动 commit、编辑格式自适应、LSP 实时诊断、上下文压缩、会话持久恢复、内核沙箱、技能/扩展体系——宿主已有或形态做不到或单家冷门，项目材料中不再提及。测试套件暂不维护（按需响应问题）。

**v1.8.2** (2026-08-25): 对标收敛 — 移除三个六家参照均无的原创机制：①guard 反作弊子系统（judge sha256 封存 + exit 3）②exit-code 硬门禁降级为 Aider 式提示词重试纪律（≤3 次）③state 断点恢复口径（state 保留为 doomcheck/budget 内部计数器）。政策依据：Bob 定"六家没有的不做、有的尽量加"。自测 47/47。
**v1.8.1** (2026-08-25): 总体测试驱动修复 — `run()` 加 per-command 超时 + 进程组 kill（start_new_session + killpg），防死锁 impl 把 pytest runner 挂死时 verify 无法返回；超时降 600s→180s，rc=124 进入红轮/语义 doom 流程。自测 52/52。
**v1.8.0 总体测试**: 四模型 A/B 对比基准 32 轮，详见 benchmarks/v180-benchmark-report.md。
**v1.8.0** (2026-08-25): 四仓共识第二批(auto-commit + patch 三级降级 + repomap + overflow 压缩). 自测 52/52.

## 後續升級目標 / Post-v1.5.1 goals (updated 2026-08-25)

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
3. v1.6 候选（按补测反哺排序）: ①doomcheck 语义级检测（同测试集连续 N 轮同失败集 → 熔断提示换策略, 源自 v4 Flash b2 doom-loop 实证）②中档模型轨常态化（每版本同协议补测, 强模型轨已饱和 11/11 失去区分度）③Hermes plugin 程序级硬门禁.
