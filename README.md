# Hermes Code Agent

> 把 Hermes 变成会自己纠错的编程智能体：**实现 → 测试 → 修复 → 全绿才算完成**。
> **编程机制**提炼自六家开源 coding agent（OpenCode / Codex CLI / Aider / Cline / Gemini CLI / Pi），不引入它们之外的原创编程机制。
> 自检升级等**服务性功能**与编程能力无关，不在对标范围内 —— 它们是本项目自身的基本服务。

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
3. **兜底机制**：危险命令拦截、补丁容错应用（失败自动回滚）、找不到位置时的模糊定位救援、超支 / 卡死熔断。

## 自检

```bash
python tests/test_apply.py     # 回归检查，纯 stdlib，不需要装 pytest
```

覆盖补丁事务提交、路径安全、二进制/删除/重命名拒绝、autocommit 密钥保护、超时杀进程组。

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
| 补丁容错应用 | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ 四级匹配 + 事务提交 |
| 自检升级 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ 节流 72h + 3 天冷却 |

## 适用边界

- **适用**：中强模型（编码特化 ≥8B 激活 / 通用 ≥24B）跑真实编码任务。
- **不适用**：纯聊天、非代码任务；弱模型不担保效果（可能反复修不好）。
- **与宿主关系**：上下文压缩 / 摘要等能力直接用 Hermes 宿主的，Skill 不重复实现。

## 系统支持

- **平台**：Linux / macOS 完整支持；**Windows 仅部分支持**，以下能力降级：
  - 超时杀进程组：`os.killpg` / `os.getpgid` 不存在 → 回退为只杀直接子进程（其 fork 出的孙进程可能残留）
  - 依赖 `git` 的命令（snapshot / restore / autocommit）行为一致，但路径大小写不敏感需注意
  - `chmod` 类权限语义不同
  - 其余子命令（`apply` / `check_cmd` / `verify` / `quickcheck` / `repomap` / 更新检查）跨平台可用
- **依赖**：Python 3.8+（stdlib only，无第三方依赖），Git 必须（snapshot/restore/auto-commit 用到）。
  - `tarfile` 的 `filter="data"` 需 3.12+，旧版本自动回退为无过滤解压。
- **网络**：仅 `update-check` / `update-apply` 需要（5s 超时，失败静默降级，不阻塞主流程）。
- **外部工具**：`pytest` / `npm` / `cargo` / `go` 等只是被探测和调用，不强制安装。
- **无网络环境**：除更新相关的子命令外全部可离线运行。

## 许可

MIT —— 见 [LICENSE](LICENSE)。
