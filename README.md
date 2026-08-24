# Hermes Code Agent

> **Hermes 代码助手** — 一个让 Hermes 编程更靠谱的 Skill。安装一次即可使用，零配置。
> 
> 把 Hermes 变成一个**会自己纠错**的编程智能体：通过「实现→校验→修复→全绿才完成」的硬循环，把弱到中档模型在真实编程题上的表现，拉平到一流开源编码 agent（OpenCode / Aider / Codex）的水准。

## 这是什么? / What is this?

一个 **自纠错编程工作流** 打包成 Hermes Skill。

**核心洞察**：编程能力的提升来自**「验证循环」** 而非单纯的模型档次。Claude Code / OpenCode / Aider 看起来「强」，很大部分是因为它们把模型塞在一个有真实反馈（跑测试 → 报错 → 修复 → 重跑）的窄工具环里。本技能把这个环给 Hermes，让一个普通模型也能写出能被测试覆盖、能被绿点验证的代码。

- **对比6个开源 agent** 阅读并提炼机制 (OpenCode 主体, Codex/Aider/Cline/Gemini CLI/Pi 补充)
- **模型无关**：用你 Hermes 配置的任意模型，包括本地部署的
- **零配置**：安装到 `skills/` 就能用，自动探测项目的 build/test/lint 命令
- **硬安全规则内置**：不会提交密钥，不会 force push，破坏性操作需确认

## 快速上手 / Quick start

```bash
# 1. 安装 (一次即可)
mkdir -p ~/.hermes/skills
cp -r hermes-code-agent ~/.hermes/skills/

# 2. 在聊天中直接使用
# "fix the divide-by-zero bug in calc.py"
# "refactor the cache module and run pytest"
# "implement LRU+TTL cache per benchmarks/README.md"
```

**不需要复制任何文件到项目**，Skill 自动探测 `pytest` / `npm test` / `go test` 等命令并执行。

## 工作流 / The hard loop

```
CLARIFY  →  PLAN  →  BUILD  →  VERIFY(pytest/lint)  →  LOOP ON RED  →  GATE(green)
```

- **探测命令后才提问**：CLARIFY 步骤会先自动找 `Makefile`/`pyproject.toml` 等，不确定时才问
- **规划与修改分离**：PLAN 阶段只探查+决策，不写代码；BUILD 阶段最小改动
- **红就回灌**：验证失败把**准确错误**回灌模型，最多 5 次 red→fix；5 次还红就停報阻塞
- **绿才算完成**：只有所有校验通过才报 done

詳見 `SKILL.md`。

## 三档模型實測 / Benchmark results

同題對比 (DeepSeek V4 Flash via OmniRoute),三对象 (OpenCode / Aider / hermes-code-agent Skill):

| 題 | OpenCode | Aider | Skill |
|---|---|---|---|
| A: 嵌套事务 KV 缓存 (7 裁判) | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| B: TTLCache LRU+TTL (6 裁判) | ✅ 6/6 | ✅ 6/6 | ✅ 6/6 |

**結論**：強模型下 Skill 與一流開源 agent 齊平；題 C(Async 调度器)雖然因 DSv4 流式波動 OpenCode/Aider 都失敗, Skill 靠 `stream:false` 穩定通過 —— **工程鲁棅性優勢**。

> ⚠️ 題 C 對比詳見 `benchmarks/README.md`。強調：Skill 價值由「模型档次 × 題目難度」交互決定；简单題/强模型時邊际為零；難題/弱模型時救命兔。

## 項目結構 / Structure

```
hermes-code-agent/
├── SKILL.md                    # 主設計文檔 (中文/雙語)
├── README.md                   # 這裡
├── ROADMAP.md                  # 開發路線圖 + 歷史版本
├── LICENSE                     # MIT
├── templates/
│   └── AGENTS.md               # 可選項目規則 (零配可不放)
├── benchmarks/
│   ├── README.md               # 測試框架+對比報告
│   └── test_ttlcache.py        # LRU+TTL pytest 裁判
├── references/
│   ├── inspiration.md          # OpenCode+Codex 機制提煉
│   ├── extra-distillation.md   # Aider/Cline/Gemini/Pi 機制
│   ├── workflow.md             # 各語言 verify 命令
│   ├── benchmark.md            # 弱模型驗證實驗
│   └── parallel-implement-review.md
└── scripts/
    └── make_bugbench.py        # benchmark harness
```

## 對比六大開源 Agent / Reference

| 機制 | OpenCode | Codex | Aider | Cline | Gemini CLI | Pi | 本 Skill |
|---|---|---|---|---|---|---|---|
| 硬驗證循環 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Plan/Exec 分離 | implicit | ModeKind | — | Plan/Act | — | — | ✅ |
| 子Agent fan-out | ✅ | ✅ | — | — | — | ext | delegate_task |
| 預算上限 | steps | Token/Rollout | — | — | — | — | ✅ |
| Repo map | — | — | ✅ PageRank | — | — | — | ✅ |
| 快照回滾 | /undo | — | — | shadow-git | — | — | ✅ |
| 模型感知上下文 | compact | compact | map | — | 1M load | — | ✅ |

## 開發路線 / Roadmap

| 版本 | 里程 |
|---|---|
| v0.1.0 | 初始 skeleton: 硬循環 + 階段協作路由 |
| v0.2.0 | 吸收 OpenCode/Codex 機制進 SKILL.md |
| v0.5.0 | Codex 對等深度交叉驗證 |
| v0.6.0 | 額外 4 agent 機制 (Aider/Cline/Gemini/Pi) |
| v0.7.0 | benchmark 測試框架固化 |
| v0.8.0 | 强模型实测 (LRA+TTL) |
| v0.10.0 | README 中文主体 |
| v0.11.0 | **零配設計**：內置安全+自动探测, AGENTS.md 可選 |
| v0.11.1 | **当前**：文档口径统一修正 |
| v1.0+ | 計劃: Hermes plugin/ACP-server 實現程序級硬門禁 |

詳見 `ROADMAP.md`。

## License

MIT — see LICENSE.
