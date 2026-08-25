# 砍除计划：移除三个"原创"功能，回退为纯对标学习形态

> 背景：Bob 决策（2026-08-25）——项目现阶段不需要创新，先模拟学习六家
> （OpenCode / Codex CLI / Aider / Cline / Gemini CLI / Pi）。
> 需砍掉三个非对标来源的原创功能：防假完成谎报、防篡改测试凑绿、断了恢复进度。

## 0. 冲突声明（必须先看）

**「防假完成谎报」= exit-code 硬门禁 = 本 skill 的核心卖点**，
且与 2026-08-25 四方评审战略共识（必留四件之首：verify 硬门禁）直接冲突。
本计划按 Bob 指示列出彻底砍除方案，但标注了每一步的战略代价，最终取舍由 Bob 定。

---

## 1. 防假完成谎报 → 砍 exit-code 硬门禁

**现状**：
- SKILL.md "Gate rule (exit-code semantics, v1.2.0)" 一节
- `hca_gate.py verify` 子命令的 exit-code 裁决语义（0=绿可报done / ≠0=禁止报done）
- SKILL.md 开头 "verify-before-done" 核心表述

**砍法**：
1. SKILL.md：删除 Gate rule 一节；"not green = not done" 从硬规则降级为
   Aider 式软纪律提示词（"测试失败时继续修复，最多3次"——对标 Aider 的 retry≤3）。
2. `hca_gate.py`：`verify` 保留测试执行与摘要输出功能（这是六家都有的
   "跑测试喂回反馈"，属于对标件），但删除其作为完成判定的裁决地位——
   输出不再声称"exit 0 才许报告 done"。
3. 测试：`tests/test_hca_gate.py` 中 gate 语义相关断言同步调整。

**代价（评论家备注）**：v180 数据中 DeepSeek lockmgr run3 的 11/12 假完成
正是被它拦下的；砍后该场景回归。弱模型实验性支持将失去唯一担保。

## 2. 防篡改测试凑绿 → 删 guard 子命令

**现状**：
- `hca_gate.py` 的 `guard record|check` 子命令 + judge 文件 sha256 封存逻辑
- `verify` 内部对 guard check 的自动调用（exit 3 分支）
- SKILL.md exit 表格中的 exit=3 JUDGE TAMPERED 行、guard 相关描述

**砍法**：
1. 删除 `cmd_guard`、`_guarded_files` 及 hash 计算存储代码。
2. `verify` 移除 guard check 调用与 exit 3 语义。
3. SKILL.md：删 guard 全部提及；exit 表格缩为 0/1/2 三行。
4. 测试：删除 tamper 相关用例。
5. 版本号 bump 小版本，push 后 CI 自动 tag+Release（按项目发布规矩）。

**代价**：ImpossibleBench 已证明测试篡改是真实行业现象；砍后无拦截。
但六家确实均无此机制，符合"先模拟学习"定位。

## 3. 断了恢复进度 → 砍 state 的恢复用途，保留内部计数

**关键依赖**：state 文件同时服务 budget 封顶（redfix 计数）、doomcheck
（doom 日志）、snapshot id——后两者是 Codex/Cline 对标件，必须存活。

**砍法（只砍"断点恢复"用途，不动计数器）**：
1. 删除 SKILL.md 中"After any context loss/compaction, run state show to
   restore discipline"及 .hca_state.json 作为 resume point 的全部表述。
2. `state show` 保留为调试输出，不再宣传为恢复入口；
   `state stale` 提示降为普通警告。
3. 不删 state 文件本身（否则连带杀死 doomcheck/budget 两个对标件）。

**代价**：上下文压缩后模型需靠 prompt 自述恢复进度，长任务可靠性下降。
若要更彻底（连 state 文件都删），需先把 redfix/doom 迁到内存或临时文件，
会改动 doomcheck 与 budget 实现——不建议在本轮做。

---

## 4. 执行顺序建议

1. 先砍 §2 guard（最干净、无争议）
2. 再砍 §3 state 恢复用途（低风险）
3. 最后砍 §1 exit-code 门禁（最高风险，建议单独一个 commit + 基准复跑确认退化幅度）
4. 每步独立 commit；全部完成后 bump 版本、push、CI 自动 Release
5. 复跑 skill-ab-benchmark 对照 v180 基线，把退化数字写进 benchmarks/

## 5. 待 Bob 拍板的两个点

- [ ] §1 是否真砍？（与 8/25 战略共识冲突，砍后弱模型场景失去担保）
- [ ] §3 砍到哪一层？（只砍宣传口径【推荐】 vs 连 state 文件一起删【大手术】）
