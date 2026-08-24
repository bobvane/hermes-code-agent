# Hermes Code Agent

> **Hermes 代码助手（自纠错编程工作流）**
> 把 Hermes 变成一个会自己纠错的编程智能体：用「先验证、后完成」的硬循环包裹模型，让弱到中档模型也能稳定产出可靠代码。
> 项目说明以中文为主体，英文为辅助参考。

Make Hermes a self-correcting coding agent. A packaging of the verify-before-done loop that powers tools like OpenCode / Claude Code / Codex — as a plain Hermes skill, model-agnostic and planner-agnostic.

## 为什么需要它 / Why

编程智能体之所以「强」，不是因为模型本身，而是因为它把模型包在一个**有真实反馈的窄工具循环**里：编辑 → 运行 → 看报错 → 修复 → 重跑。一个中/弱模型一旦进入这个循环，表现会远超它裸聊的水平。本 Skill 就是把这个循环给到 Hermes。

Coding agents feel "strong" not because of the model alone, but because they wrap the model in a **narrow tool loop with real feedback**: edit → run → see error → fix → re-run. A mid/weak model inside that loop performs far above its bare-chat level. This skill gives Hermes the same loop.

本 Skill **不替代** Hermes 既有的开发类 Skill（`test-driven-development`、`systematic-debugging`、`requesting-code-review`、`simplify-code`），而是把它们当作**阶段工人（stage workers）**来编排，让纪律变成结构性的，而非「建议性的」。

It does **not** replace Hermes's existing dev skills. It **orchestrates** them as stage workers, so the discipline is structural, not advisory.

## 安装 / Install

```bash
git clone https://github.com/bobvane/hermes-code-agent.git
mkdir -p ~/.hermes/skills
cp -r hermes-code-agent ~/.hermes/skills/
```

**装完即用，零配置。** 安全规则与测试/lint 命令已内置，无需为任何项目复制配置文件。

> **可选覆盖（非必须）**：若某仓库需要非标准测试命令或专属约定，可复制模板自行调整：
> ```bash
> cp ~/.hermes/skills/hermes-code-agent/templates/AGENTS.md ./AGENTS.md
> ```
> 这一步**不是必需的**——Skill 会自动探测命令并强制执行安全门禁。
## 使用 / Use

在任何 Hermes 对话里，直接描述任务即可：
- 「用 FastAPI 搭个鉴权服务」
- 「修 src/parser.py 里的 bug」
- 「重构鉴权模块」

智能体会自动跑硬循环：澄清 → 规划 → 实现 → 验证 → 红了就修 → 全绿才过关。

The agent will run the hard loop automatically: clarify → plan → implement → verify → loop on red → green gate.

## 与主流工具对比 / How it compares

| 工具 Tool | 开源 Open | 模型 Model | 本项目中的角色 Role here |
|---|---|---|---|
| OpenCode | MIT | 75+（模型无关） | **主要参考** — harness 架构 |
| OpenAI Codex CLI | Apache-2.0 | OpenAI 优先 | 次要 — exec/审批/子代理模式 |
| Claude Code | 闭源 | Claude | 仅借鉴循环形态（非代码参考） |
| **Hermes Code Agent** | MIT | **任意（Hermes 默认）** | 你正在安装的这个 Skill |

## 设计红线（通用性）/ Design red lines

1. 自洽的硬循环 —— 不依赖任何外部组件。
2. 规划输入可选 —— 默认从一条原始指令就能跑。
3. 不硬编码任何私有工作流命令（omh 等只是可选上游）。
4. 不绑定固定模型 —— 用 Hermes 的默认模型。

## 链接 / Links

- 仓库 Repo：https://github.com/bobvane/hermes-code-agent
- 路线图 Roadmap：见 `ROADMAP.md`
- 实测报告 Benchmark：见 `benchmarks/README.md`

## 许可证 / License

MIT —— 见 `LICENSE`。
