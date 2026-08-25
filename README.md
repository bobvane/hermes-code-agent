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

依据源码深扒（详见 `references/`）。✓=已实现，半=部分实现/近似形态，✗=未做。

| 功能 | OpenCode | Codex CLI | Aider | Cline | Gemini CLI | Pi | 本 Skill |
|---|---|---|---|---|---|---|---|
| 测试反馈重试循环 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ 三通道分流+结构化错误自愈 |
| 计划/执行分离 | 半 | ✓ 双模式 | ✗ | ✓ Plan/Act | ✗ | ✗ | ✓ 双段模式指令+clarify阶段门 |
| 子代理并行 | ✓ | ✓ | ✗ | ✗ | ✓ | ✓扩展 | ✓ 委派默认化+生命周期编排 |
| 每角色不同模型 | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ 角色-档次映射表(提醒制) |
| 步数/花费封顶 | ✓ steps | ✓ 硬预算 | ✗ | ✗ | ✗ | ✗ | ✓ 分级提醒+收尾协议 |
| 并发数限制 | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ ≤3并发上限 |
| 权限审批分级 | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✓ 四档操作分级表 |
| 危险命令拦截 | ✗ | ✓ execpolicy | ✗ | ✗ | ✓ 注入检测 | ✗ | ✓ check_cmd双引擎移植 |
| 项目规则文件 | AGENTS.md | AGENTS.md | CONVENTIONS | .clinerules | GEMINI.md | ✗ | ✓ 全局CONVENTIONS+项目层自动生成 |
| 仓库结构图 | ✗ | ✗ | ✓ PageRank | ✗ | ✗ | ✗ | ✓ 两张索引卡(目录卡+符号卡) |
| 补丁容错应用 | ✗ | ✓ apply-patch | ✓ 多级容错 | ✗ | ✗ | ✗ | ✓ seek_sequence四级匹配全量移植 |

> 本表只列在做的功能；随每步实现更新，全部完成后再整体重写 README。
