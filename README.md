# Hermes Code Agent

> **Hermes 代码助手** — 把 Hermes 变成一个会自己纠错的编程智能体：实现→测试→修复→全绿才算完成。对标六家开源 coding agent（OpenCode / Codex CLI / Aider / Cline / Gemini CLI / Pi）提炼机制，不引入它们之外的原创设计。

## 安装方法

```bash
# 1. 克隆本仓库（或下载）
git clone https://github.com/bobvane/hermes-code-agent.git
cd hermes-code-agent

# 2. 安装到 Hermes skills 目录（一次即可，零配置）
mkdir -p ~/.hermes/skills
cp -r . ~/.hermes/skills/hermes-code-agent/

# 3. 在聊天中直接使用
#    "fix the divide-by-zero bug in calc.py"
#    "refactor the cache module and run pytest"
```

不需要复制任何文件到项目里，Skill 自动探测 `pytest` / `npm test` / `go test` 等命令并执行。

## 功能对照表（六家开源 agent × 本 Skill）

依据四次源码深扒（详见 `references/`）。✓=已实现，半=部分实现/近似形态，✗=未做。

| 功能 | OpenCode | Codex CLI | Aider | Cline | Gemini CLI | Pi | 本 Skill |
|---|---|---|---|---|---|---|---|
| 测试反馈重试循环 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ 三通道分流+did-you-mean定位救援 |
| 计划/执行分离 | 半 | ✓ 双模式 | ✗ | ✓ Plan/Act | ✗ | ✗ | ✓ 双段模式指令+clarify阶段门 |
| 子代理并行 | ✓ | ✓ | ✗ | ✗ | ✓ | ✓扩展 | ✓ 委派默认化+生命周期编排 |
| 每角色不同模型 | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ 角色-档次映射表(提醒制) |
| 步数/花费封顶 | ✓ steps | ✓ 硬预算 | ✗ | ✗ | ✗ | ✗ | ✓ 分级提醒+收尾协议 |
| 并发数限制 | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ ≤3并发上限 |
| 权限审批分级 | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✓ 四档操作分级表 |
| 危险命令拦截 | ✗ | ✓ execpolicy | ✗ | ✗ | ✓ 注入检测 | ✗ | ✓ check_cmd双引擎移植 |
| 项目规则文件 | AGENTS.md | AGENTS.md | CONVENTIONS | .clinerules | GEMINI.md | ✗ | ✓ AGENTS.md可选覆盖 |
| 仓库结构图 | ✗ | ✗ | ✓ PageRank | ✗ | ✗ | ✗ | ✓ repomap简化版 |
| 快照回滚 | ✓ undo | ✗ | 常规git | ✓ shadow-git | ✓ 轻量 | ✗ | ✓ snapshot/restore事务性 |
| 编辑后自动commit | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ autocommit |
| 补丁容错应用 | ✗ | ✓ 三级降级 | ✓ 多级容错 | ✗ | ✗ | ✗ | ✓ patch三级降级 |
| 编辑格式自适应 | ✗ | ✗ | ✓ 按模型选 | ✗ | ✗ | ✗ | ✗ 未做 |
| LSP实时诊断 | ✓ | ✗ | ✗ | ✓ IDE | ✗ | ✗ | ✗ 形态限制 |
| 上下文压缩 | ✓ 本地 | ✓ 远程 | ✗ | ✓ | ✓ | ✗ | ✓ compact确定性压缩 |
| 会话持久恢复 | ✗ | ✓ JSONL | ✗ | ✗ | ✗ | ✗ | 半 内部计数器 |
| 内核沙箱 | ✗ | ✓ Landlock | ✗ | ✗ | ✗ | ✗ | ✗ 形态限制 |
| 技能/扩展体系 | ✗ | ✓ skills | ✗ | ✗ | ✗ | ✓ 内核 | ✓ 本身即Hermes skill |

**覆盖率：19 项对标功能已实现 17 项。** 未做的 2 项均为 Skill 形态硬限制（LSP 实时诊断、内核沙箱——需要宿主程序层能力）；1 项待做（编辑格式自适应，第二批计划）。

> 本表随功能实现逐步更新；全部完成后再整体重写 README。
