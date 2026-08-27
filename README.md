# Hermes Code Agent

> 把 Hermes 变成会自己纠错的编程智能体：**实现 → 测试 → 修复 → 全绿才算完成**。
> 机制全部提炼自六家开源 coding agent（OpenCode / Codex CLI / Aider / Cline / Gemini CLI / Pi），不引入它们之外的原创设计。

## 安装

```bash
git clone https://github.com/bobvane/hermes-code-agent.git
cd hermes-code-agent
mkdir -p ~/.hermes/skills
cp -r . ~/.hermes/skills/hermes-code-agent/
```

装完直接在聊天里派活，例如：

- "fix the divide-by-zero bug in calc.py"
- "refactor the cache module and run pytest"

Skill 自动探测 `pytest` / `npm test` / `go test` 等并运行，**无需把任何文件复制进你的项目**。

## 它怎么干活

1. **计划 / 执行分离**：先出方案（PLAN），你确认后才动手改码（BUILD）。
2. **测试反馈循环**：每轮改完跑测试，红了就把错误结构化回喂给自己修，直到全绿。
3. **兜底机制**：危险命令拦截、补丁容错应用、找不到位置时的模糊定位救援、超支 / 卡死熔断。

## 功能对照（六家 × 本 Skill）

| 功能 | OpenCode | Codex | Aider | Cline | Gemini | Pi | 本 Skill |
|---|---|---|---|---|---|---|---|
| 测试反馈重试循环 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ 三通道分流 + 结构化自愈 |
| 计划 / 执行分离 | 半 | ✓ | ✗ | ✓ | ✗ | ✗ | ✓ 双段 + 阶段门 |
| 子代理并行 | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ 委派默认化 |
| 每角色不同模型 | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ 角色-档次映射 |
| 步数 / 花费封顶 | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ 分级提醒 + 收尾 |
| 并发数限制 | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ ≤3 |
| 权限审批分级 | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✓ 四档分级 |
| 危险命令拦截 | ✗ | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ 双引擎移植 |
| 项目规则文件 | AGENTS | AGENTS | CONV | .cline | GEMINI | ✗ | ✓ 全局 + 项目层 |
| 仓库结构图 | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ 目录卡 + 符号卡 |
| 补丁容错应用 | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ 四级匹配 |

## 适用边界

- **适用**：中强模型（编码特化 ≥8B 激活 / 通用 ≥24B）跑真实编码任务。
- **不适用**：纯聊天、非代码任务；弱模型不担保效果（可能反复修不好）。
- **与宿主关系**：上下文压缩 / 摘要等能力直接用 Hermes 宿主的，Skill 不重复实现。

## 许可

MIT —— 见 [LICENSE](LICENSE)。
