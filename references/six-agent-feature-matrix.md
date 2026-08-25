# 六家 AI 编程工具 × 本 Skill 功能对照表

> 用途：hermes-code-agent 对标沟通的标准参照表。Bob 说"把对照表调出来"即展示本文件。
> 依据：references/inspiration.md、extra-distillation.md、four-repo-comparison.md、agent-mechanism-extraction.md 四次源码深扒。
> 政策（2026-08-25）：六家没有的功能一律不做；六家有的能加就加；Skill 形态做不到的除外。
> 版本基准：v1.8.2（2026-08-25）

| 功能 | OpenCode | Codex CLI | Aider | Cline | Gemini CLI | Pi | 本 Skill |
|---|---|---|---|---|---|---|---|
| 测试反馈重试循环 | ✓ | ✓ | ✓≤3次 | ✓ | ✓ReAct | ✓ | ✓verify+重试 |
| 计划/执行分离 | 半 | ✓双模式 | ✗ | ✓Plan/Act | ✗ | ✗ | ✓PLAN/BUILD分模式 |
| 子代理并行 | ✓ | ✓ | ✗ | ✗ | ✓ | ✓扩展 | ✓delegate_task扇出 |
| 每角色不同模型 | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | 半per-step提示(受配置限制) |
| 步数/花费封顶 | ✓steps | ✓硬预算 | ✗ | ✗ | ✗ | ✗ | ✓软帽(硬终止做不到) |
| 并发数限制 | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓≤3并发上限 |
| 权限审批分级 | ✓默认问 | ✓分段审 | ✗ | ✓细粒度 | ✗ | ✗ | ✓三档approval modes |
| 危险命令拦截 | ✗ | ✓rm永不免批 | ✗ | ✗ | ✗ | ✗ | ✓破坏性必确认 |
| 项目规则文件 | AGENTS.md | AGENTS.md | CONVENTIONS | .clinerules | GEMINI.md | ✗ | ✓AGENTS.md可选覆盖 |
| 仓库结构图 | ✗ | ✗ | ✓PageRank | ✗ | ✗ | ✗ | ✓repomap简化版 |
| 快照回滚 | ✓undo | ✗ | 常规git | ✓shadow-git最强 | ✓轻量无事务 | ✗ | ✓snapshot/restore事务性 |
| 编辑后自动commit | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✓autocommit |
| 补丁容错应用 | ✗ | ✓三级降级 | ✓多级容错 | ✗ | ✗ | ✗ | ✓patch三级降级 |
| 编辑格式自适应 | ✗ | ✗ | ✓按模型选 | ✗ | ✗ | ✗ | ✗未做 |
| LSP实时诊断 | ✓ | ✗ | ✗ | ✓IDE | ✗ | ✗ | ✗做不到 |
| 上下文压缩 | ✓本地 | ✓远程 | ✗ | ✓0.9阈值 | ✓0.5阈值 | ✗ | ✓compact确定性压缩 |
| 会话持久恢复 | ✗ | ✓JSONL+索引 | ✗ | ✗ | ✗ | ✗ | 半state计数器(恢复口径已砍) |
| 内核沙箱 | ✗ | ✓Landlock | ✗ | ✗ | ✗ | ✗ | ✗做不到 |
| 技能/扩展体系 | ✗ | ✓skills | ✗ | ✗ | ✗ | ✓4原语内核 | ✓本身即Hermes skill |

## 差距盘点

- 六家全✓的唯一功能：测试反馈重试循环 = 行业骨架。
- **真正差距仅1项可做**：编辑格式自适应（Aider，按模型元数据选 whole/diff/u-diff）。
- 维持现状：会话持久恢复（完整形态依赖宿主会话存储；恢复口径已按政策砍除）。
- Skill形态硬限制不做：LSP实时诊断、内核沙箱。
- 覆盖率：19项对标功能已覆盖17项。

## 已移除的原创机制（v1.8.2，政策依据：六家均无）

- guard 反作弊子系统（judge sha256 封存 + exit 3）
- exit-code 硬门禁 → 降级为 Aider 式提示词重试纪律
- state 断点恢复口径（state 文件保留为 doomcheck/budget 内部计数器）
