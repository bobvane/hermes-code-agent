# 四仓库横向对比报告（Codex / Aider / Cline / Gemini CLI，2026-08）

## ① 各仓库独立摘要

**Codex (codex-rs)**
- 沙箱：`sandboxing/src/landlock.rs` + seccomp（denial.rs 用 exit 128+SIGSYS 识别沙箱拒绝），策略化、跨平台（seatbelt/bwrap/windows）。
- rollout 持久化：`codex-rs/rollout/` 独立 crate——JSONL 追加 + sqlite 索引 + reverse_jsonl_scanner，会话可恢复可搜索。
- apply_patch：`apply-patch/src/seek_sequence.rs` 三级降级匹配（精确→rstrip→trim 双侧）+ eof 特判；patch 安全分级 `assess_patch_safety` → AutoApprove/AskUser/Reject。
- 预算：rollout_budget 加权计量+多阈值软提醒（已有蒸馏）；token_budget 双轨。

**Aider**
- repo map：`repomap.py:525` personalized PageRank（chat 文件做 personalization+dangling），map_tokens=1024、map_mul_no_files=8 动态扩到上下文比例。
- edit format 按 model 元数据选 whole/diff/u-diff（models.py:439-484）；失败后 `search_replace.py:flexible_search_and_replace` 多级容错策略 + num_reflections 反射上限。
- auto_commit（base_coder.py:2375）：每轮编辑后自动 commit，commit message 由弱模型从 diff 生成，失败仅告警不中断。

**Cline**
- checkpoint：shadow git（docs/core-workflows/checkpoints.mdx），每次工具使用后 commit 快照；restore 前用 `stash push --include-untracked` + 私有 ref `refs/cline/restore-transactions/<uuid>` 做恢复事务，可回滚（sdk/packages/core/src/session/checkpoint-restore.ts）。三种 restore 粒度（文件/任务/两者）。
- compaction：`extensions/context/compaction.ts` 触发比 0.9×窗口、目标压缩到 0.7；overflowRecovery 时强制用确定性 basic 策略（不依赖 LLM 再成功）。
- auto-approve：按工具类别细粒度配置。

**Gemini CLI**
- checkpoint：`services/gitService.ts` shadow repo（GIT_DIR 独立、GIT_WORK_TREE=项目根），`git add . + commit`；clean 无变更直接返回 HEAD hash。轻量但无事务保护。
- chat compression：阈值 0.5×token limit 触发，保留最近 30%（COMPRESSION_PRESERVE_THRESHOLD），function response 有 50k 独立预算；findCompressSplitPoint 只在 user 非 tool 边界切分；摘要失败后降级为纯截断不再重试 LLM。
- GEMINI.md 分层记忆：memoryDiscovery.ts 从 cwd 向上找 `.git` 边界内的各级 context 文件，树形 import 合并，20 并发读。

## ② 五角色辩论

**产品经理**：目标对齐"首过率+完成性保证"。优先级：Aider 容错解析（直接影响补丁成功率）> Cline 三粒度回滚（用户信任）> Codex 软预算提醒（省钱）。反对移植 landlock（用户是单机个人环境，收益低）。
**架构师**：hca_gate 已有 git 快照，应升级而非叠加。最优实现评 judge：repo map=Aider 无争议；checkpoint=Cline（事务性 restore 是唯一正确的写法，Gemini 版太裸）；compaction=Gemini（split point 边界约束 + 失败降级路径完整）。Codex rollout 的 JSONL+索引外置状态与我们方向一致，确认现状即可。
**开发工程师**（独立表态）：不同意 PM 把容错排第一——我们 patch 工具走 Hermes 原生 fuzzy patch，已有降级；真正的空白是 **checkpoint 事务**和 **PageRank map**。移植成本现实评估：PageRank 若引 networkx 是重依赖，可用简化度排序替代（中成本）；shadow-git 事务纯 git 命令脚本化，低成本低风险，应最先落地。Gemini 的"tool-response 不切断"split point 是十几行逻辑，白捡。
**测试/QA 代表**：关心可验证性。Cline/Gemini 的 checkpoint 都有明确失败分支（快照失败→报错不阻塞 vs 事务回滚）；我们移植必须加 doomcheck 断言：restore 后 `git status` 必须干净，否则标记状态污染。compaction 移植需测 overflowRecovery 路径（估算错时强制确定性压缩）——这是最容易漏的边界。auto_commit 在 dirty repo 上行为要定义清楚。
**评论家**：泼两盆冷水。(1) Cline checkpoint 每次 commit 全量 add，大 repo 会慢——文档自己承认；我们的场景（单任务小改动）够用但要跳过 node_modules/.venv。(2) Aider PageRank 的收益依赖 tree-sitter tag 提取质量，Python 生态外的语言衰减大；不要神化。(3) 五家在"loop+verify+budget"上完全收敛，说明骨架已定，v1.5 应做深不做宽。
**分歧与收敛**：PM vs 工程师对优先级分歧 → 以"成本低且填补空白优先"收敛；QA 补充验证条款全部采纳；评论家的两条限制写入注意事项。共识见下。

## ③ v1.5 共识可移植清单

| # | 机制 | 来源 | 关键源码 | 成本 | 价值 |
|---|------|------|---------|------|------|
| 1 | shadow-git 快照 + **事务性 restore**（stash include-untracked → 私有 ref → 可回滚），BUILD 步骤前打点 | Cline | sdk/packages/core/src/session/checkpoint-restore.ts | 低 | 高 |
| 2 | 压缩 split point 只取 user 非 tool 边界 + 摘要失败降级纯截断 | Gemini | context/chatCompressionService.ts findCompressSplitPoint | 低 | 高 |
| 3 | 预算多阈值软提醒注入（去重防重发） | Codex | core/src/context/rollout_budget.rs | 低 | 中高 |
| 4 | 轻量 repo map（grep 符号+引用计数排序，top-N 注入；不强引 networkx） | Aider | aider/repomap.py:525 | 中 | 中高 |
| 5 | 补丁三级降级匹配（精确→rstrip→trim）作为 hca patch 兜底层 | Codex | apply-patch/src/seek_sequence.rs | 中 | 中 |
| 6 | auto-commit 每轮落盘（弱模型生成 message，失败不阻塞） | Aider | coders/base_coder.py auto_commit | 低 | 中 |
| 7 | overflow 强制确定性压缩路径（估算失误时不依赖 LLM 自救） | Cline | extensions/context/compaction.ts | 低 | 中 |

**不可移植**：landlock/seccomp 内核沙箱（Rust+内核特性，Hermes 无执行环境对应层）；Cline VSCode 三粒度 restore UX（无 IDE 层，保留文件/任务双态即可）；Gemini 1M 宽窗策略（模型绑定）；Codex JSONL+sqlite rollout 索引（Hermes 会话存储已覆盖）。

**QA 附带条件**：#1 必须 restore 后校验 `git status --porcelain` 为空；#2/#7 需覆盖"估算错误"回归用例；#4/#6 跳过 .venv/node_modules 且 dirty repo 行为显式定义。
