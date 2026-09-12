# PROJECT_CONTEXT — hermes-code-agent v2.4.0

> 本文档固化 hermes-code-agent Skill 的完整上下文，供任何 Hermes session 在不了解聊天记录的情况下继续开发。版本：v2.4.0（截至 2026-09-12）。

---

## 1. 项目目标

把一个弱/中档模型变成会"先验证、后完成"的编程智能体：实现 → 测试/校验 → 修复 → 全绿才算完成。

**对标六家**（OpenCode 主要，Codex + Aider + Cline + Gemini CLI + Pi）：
- **不引入任何六家没有的原创机制** — 砍掉功能在文档中消失，不提
- 对标清单见 `references/six-agent-feature-matrix.md`
- 决策记录：Bob 2026-08-24 拍板「六家没有的不做，有的尽量加，Skill 形态达不到的除外」

**模型门槛**：编码特化 ≥8B 激活参数 / 通用 ≥24B；弱模型实验性不担保（v1.2.1 起明示）。

---

## 2. 架构（唯一权威源）

```
upstream plan (optional: omh / AGENTS.md / raw instruction)
        │
        ▼
hermes-code-agent  ── orchestrates ──► existing dev skills (stage workers)
 (hard verify loop)                   TDD / debug / review / simplify / delegate
        │
        ▼
 green gate ──► done
```

**核心原则**：Skill **永远重写** stage-worker 技能。它调用它们。单一来源真值。

**部署形态**：Hermes Skill（SKILL.md + scripts/hca_gate.py + templates + references）。无宿主程序、无数据库、无后台进程。纯提示词协议 + stdlib Python 门禁脚本。

**关键约束**：
- 凡 Hermes 宿主已有能力（上下文压缩/摘要），Skill 直接用宿主，不重复实现
- 任何 "计划"（如 AGENTS.md / omh）是**可选上游**，不是依赖
- 安装一次零配置：内置安全规则 + 自动探测测试/lint 命令

---

## 3. 目录结构

```
/opt/data/workspace/hermes-code-agent/       # git 仓库（开发源）
├── SKILL.md                                 # Skill 主文件（frontmatter: name/version/author）
├── README.md                                # 用户文档（中文主体）
├── ROADMAP.md                               # 版本历史 + 目标体系
├── LICENSE                                  # MIT (c) 2026 Bob Vane
├── .gitignore                               # 本地忽略
├── scripts/
│   ├── hca_gate.py                          # 核心门禁脚本（stdlib Python，~1626 行）
│   ├── cmd_policy.yaml                      # 危险命令策略表（三段：allow/confirm/deny）
│   └── make_bugbench.py                     # 基准测试 harness（保留历史）
├── templates/
│   ├── CONVENTIONS.md                       # 全局编程约定骨架（六节）
│   └── project-rules.md                     # 项目层规则骨架
├── tests/
│   └── test_apply.py                        # 回归检查 16 项（纯 stdlib，v2.4.0 新增）
├── pyproject.toml                           # 项目标记 + testpaths（v2.4.0 新增，让 detect 能找到测试）
├── references/                              # 源码研究 + 设计决策记录
│   ├── inspiration.md / opencode-deep-research.md / codex-deep-research.md
│   ├── six-agent-feature-matrix.md
│   ├── goal-*.md                            # 各目标详细设计
│   └── ...
└── benchmarks/                              # 基准测试（v1 固定协议）
    ├── protocol.md                          # 固定题+裁判+指标定义
    ├── run_v180.py                          # v1.8.0 编排器
    ├── test_ttlcache.py                     # 裁判：LRU+TTL 缓存 7 用例
    └── README.md                            # 基准文档
```

**安装副本**（只读，由同步脚本维护）：
```
/opt/data/skills/hermes-code-agent/           # Hermes 实际加载的 Skill
├── SKILL.md                                  # 版本 2.1.1
├── scripts/hca_gate.py                       # 同 workspace 副本
├── skill_state.json                          # 运行时状态（不在 git 仓库里）
└── backups/SKILL.md.bak-<timestamp>          # 升级前备份
```

---

## 4. 核心模块：hca_gate.py 子命令全集

所有子命令通过 `python scripts/hca_gate.py <cmd>` 调用。exit-code 语义：

| exit | 含义 | 操作 |
|---|---|---|
| 0 | GREEN | 步骤可以继续 |
| 1 | RED | 按 digest 修复，再跑测试 |
| 2 | DOOM-LOOP | 回滚到上一个 snapshot 或换策略，禁止再 patch |
| 3 | CONFIRM | 向用户展示完整命令并获取确认 |

### 主流程子命令

| 命令 | 触发阶段 | 功能 |
|---|---|---|
| `detect` | CLARIFY | 探测项目 test/lint/build 命令（Python pytest、Node npm、Go test、Rust cargo、Makefile） |
| `snapshot` | BUILD 前 | 记录可回滚的 git snapshot（`refs/hca/snapshots/<id>`） |
| `plancheck` | PLAN→BUILD 边界 | exit!=0 时方案阶段误改了源码 → 回滚再进 BUILD |
| `quickcheck f.py` | 每次编辑后 | 秒级语法门（py_compile / tsc --noEmit / go build 等） |
| `doomcheck "tag"` | 每轮循环 | 同 tag 连续 3 次 → exit 2 熔断 |
| `locate f.py <<< snippet` | apply 失败时 | Aider 式模糊定位：最佳候选区+相似度分数（无硬阈值，判断权给模型） |
| `apply <patch.diff>` | BUILD 编辑 | Codex seek_sequence 四级匹配 + 事务提交（失败全量回滚，v2.4.0）+ 同文件多 block 链式叠加 + `safe_repo_path()`（锚定 git 根） |
| ~~`patch <diff>`~~ | ~~fallback~~ | **v2.3.0 已砍除** —— 单一改码入口，用 `apply` |
| `verify` | GATE | 跑全套测试/lint，exit 0/1/2 |
| `state show/reset/bump` | 调试 | 看循环计数器（steps/redfix/doom/snapshots，存在 `.hca_state.json`） |
| `repomap` | 任务开始 | 轻量仓库符号卡（grep class/def/function，top 40） |
| `compact` | 会话长时 | 确定性状态压缩（保留最近 10 条 snapshot + 20 条 telemetry） |
| `check_cmd "<cmd>"` | 执行任何 shell 前 | 三段策略（allow/confirm/deny）+ 注入扫描 |
| `restore <id>` | 回滚 | 事务性恢复到 snapshot |

### v2.1.1 新增：自检升级子命令

| 命令 | 触发阶段 | 功能 |
|---|---|---|
| `update-check [--force]` | CLARIFY（每任务首次） | 探 GitHub release；72h 节流；失败静默降级 |
| `update-pending` | GATE（全部绿后） | 非空输出 = 有新版本待升级（3 天冷却内不弹） |
| `update-status` | 调试 | 打印版本号 + 节流指针 + pending 信息 |
| `update-apply [--version]` | 用户选 A 后 | 下载 tarball、备份旧 SKILL.md、覆盖 Skill 目录、写 `skill_state.json` |

**节流指针（skill_state.json，不在项目目录）**：
- `last_check_ts`：上次真实检测时间，<72h 不发网络请求（`--force` 绕过）
- `next_prompt_ts`：选 B 后写 now+3天，期间不弹升级提示
- `pending`：null 或 `{remote, checked_at, local}`

**关键常量**（hca_gate.py 顶部）：
```python
GITHUB_REPO = "bobvane/hermes-code-agent"
GITHUB_TARBALL = f"https://github.com/{GITHUB_REPO}/archive/refs/tags/v{{v}}.tar.gz"
UPDATE_CHECK_HOURS = 72          # 3 天检测节流
UPGRADE_PROMPT_DAYS = 3          # 选 B 后 3 天再提示
UPDATE_HTTP_TIMEOUT = 5          # 最长 5 秒
EXEMPT_FILES = {"skill_state.json"}  # 升级时豁免覆盖
```

---

## 5. 工作流（CLARIFY → PLAN → BUILD → VERIFY → GATE）

### 硬循环（唯一不可协商部分）

```text
1. CLARIFY SCOPE   — 什么文件/行为？done 的定义？先探测命令（再问人）
                      + update-check --force（首次探版本）
2. PLAN            — 探索，读文件，决定方案；输出 3-5 步 mini-plan；禁 edit
3. BUILD           — 最小改动，一步一 verify
4. VERIFY          — 跑测试/lint；捕获真实输出
5. LOOP ON RED     — 原样报错做输入，修，重跑；最多 5 红→修
6. GATE            — 全绿 + 范围达标 → 标记完成；update-pending；有则弹 A/B
7. REPEAT          — 下一步
```

### 三路三态分流（FAIL 时优先走便宜通道）

| 通道 | 触发 | 先做什么 | 预算 |
|---|---|---|---|
| ① PATCH | apply 失败 | 结构化错误自愈合；deep miss 用 locate | 3 次 |
| ② STATIC | patch 落地但语法/lint 报错 | 直接从 quickcheck 输出修 | 3 次 |
| ③ TEST | 静态清洁，测试 red | 喂 exact verify digest，修，重跑 | 5 红→修 |

### Plan/Build 边界（Cline-style user switch）
- 每次 PLAN→BUILD 边界必须 `clarify("切换模式？", ["进入 BUILD", "留在 PLAN"])`
- 边界前后必须跑 `plancheck`（exit!=0 → roll back 改动的文件）
- PLAN mode 禁 edit（write_file/mutating 命令）；BUILD mode 禁重规划

### 预算封顶（Codex TokenBudget）
- 硬步数：5 步；TEST 通道 5 红→修；PATCH/STATIC 通道 3 次
- 软提醒（各发一次，去重）：step 4/5 → "plan the finish"；3k tok → targeted reads；8k tok → write progress note
- 硬超支：exit 2，打印 MAX_STEPS close-out protocol（DONE/NOT DONE/NEXT），禁止再 tool call

### 上下文管理
- 弱模型：先建目录卡（ls -R），挑相关文件再建符号卡（grep def/class）
- 大窗口模型：宽读；弱模型：repo map
- compact 子命令：确定性的尾部保留 split，LLM 不参与（Gemini 风格）

---

## 6. 已完成功能（按版本）

### v2.4.0（2026-09-12，当前版本）— 可靠性版本
- [x] `autocommit` 密钥保护（`SECRET_PATH_RE`：`.env*`/密钥扩展名/凭据配置文件不再被 `git add -A` 扫入）
- [x] 同文件多 block 链式叠加（第一次改动静默丢失的 P0 修复）
- [x] `apply` 多文件事务提交 + 失败全量回滚（此前半应用 + 裸 traceback）
- [x] `run()` 真杀进程组（`Popen` + `killpg`；此前 `TimeoutExpired.pid` 恒为 None 的死代码）
- [x] 二进制文件结构化拒绝（此前裸 `UnicodeDecodeError`）
- [x] `mkstemp` 替代可预测 tmp 名
- [x] 删除/重命名补丁显式拒绝（错误信息不再误导）
- [x] `safe_repo_path` 锚定 git 根（`git rev-parse --show-toplevel`）
- [x] `runner_fix_hint()`：无 runner 时给出具体安装命令
- [x] `tests/test_apply.py` 16 项回归检查 + `pyproject.toml`（本项目首次可自校验）
- [x] 文档漂移整肃（9 个 goal-*.md 状态行、死引用、README 畸形表格、SKILL 死引用）
- [x] 删除 `benchmarks/run_v180.py`（调用已删的 `guard record`，死代码）

### v2.3.0（2026-09-07，当前版本）— 单一改码入口
- [x] 砍掉 `patch` 子命令（`cmd_patch` + `_unified_diff_blocks` + `_wsfree_*`，共 130 行）
- [x] `apply` 成为唯一改码入口
- [x] SKILL.md 全部 `patch` 引用替换为 `apply`
- [x] README 对照表更新
- [x] Breaking change：任何调用 `hca_gate.py patch <diff>` 的脚本需改为 `apply <diff>`
- [x] Smoke test 通过：apply 修改成功、patch 子命令清晰报错

### v2.2.0（2026-09-07）— 安全硬化
- [x] `safe_repo_path()` 路径校验（拒绝 `..`/绝对路径/`.git`/受保护文件/逃逸符号链接）
- [x] `apply` 两阶段原子写入（内存预验证 + `os.replace()`）
- [x] `update-apply` SHA-256 校验（`.sha256` sidecar 比对 + `--skip-verify` 逃生口）
- [x] `check_cmd` 解释器逃逸拦截（python -c / node -e / bash -c / find -exec / xargs / env）
- [x] README 加「系统支持」章节
- [x] GitHub Release v2.2.0

### v2.1.1（2026-08-28）— 自检升级
- [x] `update-check` 子命令：GitHub release 探新，72h 节流
- [x] `update-pending` 子命令：GATE 后调，弹 A/B
- [x] `update-apply` 子命令：tarball 下载 + 备份 + 覆盖（skill_state.json 豁免）
- [x] `update-status` 子命令：调试指针
- [x] SKILL.md 步骤 6/7 加挂点
- [x] .gitignore 豁免 skill_state.json
- [x] install-free 升级（不需要重新安装 Skill）
- [x] 升级后提示"重启网关生效"
- [x] 网络失败静默降级，不阻塞主流程
- [x] 节流双指针（last_check_ts 72h + next_prompt_ts 3d）
- [x] GitHub Release v2.1.1（commit 57ec489）
- [x] 安装副本 `/opt/data/skills/hermes-code-agent/` 同步 v2.1.1
- [x] skill_state.json 已生成于安装副本（last_check_ts=1788075511，up-to-date）

### v2.1.0（2026-08-27）— feature-complete 里程碑
- [x] 六家对标 11/11 功能全部落地
- [x] SKILL.md README 重写（中文主体）
- [x] LICENSE 规范化（Copyright (c) 2026 Bob Vane）
- [x] 基准文件精简（保留 run_v180.py + protocol.md）
- [x] 测试套件暂不维护

### v2.0.1（2026-08-26）
- [x] locate 模糊救援重写：逐行字符级相似度（无硬阈值）

### v2.0.0（2026-08-26）
- [x] 项目规则两层设计：CONVENTIONS.md（全局）+ `<项目名>.md`（项目）
- [x] repo map 两张索引卡：目录卡 + 符号卡
- [x] patch 容错应用：seek_sequence 四级匹配（Codex apply-patch 全量移植）
- [x] 砍除 8 项（快照回滚、自动 commit、LSP、压缩… — 在文档中消失）

### v1.8.0
- [x] auto-commit（Aider 式，verify 绿后自动 checkpoint）
- [x] patch 三级降级（git-apply 三档）
- [x] repomap（Aider 思路，stdlib 实现）
- [x] overflow 强制压缩

### v1.7.0
- [x] 预算超支硬熔断（15000 tok / 5 红轮）
- [x] 升级建议（exit 2 时提示换模型）

### v1.6.0
- [x] doomcheck 语义级检测（failure fingerprint 同失败集连续 3 轮 → exit 2）

### v1.5.0
- [x] 事务性 snapshot/restore
- [x] compact 状态压缩
- [x] budget_fired 分层软提醒

### v1.4.0
- [x] verify 输出双限（200 行 + max_chars 字节）
- [x] tokens≈ 遥测写入 state

### v1.2.1
- [x] guard record/check（防篡改，后砍除）
- [x] verify venv 自举（.venv/bin/python fallback）

---

## 7. 当前正在进行的工作

**暂无活跃开发任务。**

v2.1.1 已于 2026-09-07 完整交付，包括：
- GitHub Release v2.1.1（https://github.com/bobvane/hermes-code-agent/releases/tag/v2.1.1）
- 安装副本同步（/opt/data/skills/hermes-code-agent/）
- skill_state.json 已生成（up-to-date，节流正常）

---

## 8. 已排除的方案及原因

| 排除项 | 原因 | 记录位置 |
|---|---|---|
| guard 反作弊子系统（judge sha256 封存 + exit 3） | v1.8.2 砍除，六家没有 | ROADMAP v1.8.2 |
| exit-code 硬门禁降级为提示词重试 | v1.8.2 砍除，过于激进 | ROADMAP v1.8.2 |
| state 断点恢复 | v1.8.2 砍除，单家冷门 | ROADMAP v1.8.2 |
| LSP 实时诊断 | v2.0.0 砍除，Skill 形态做不到 | ROADMAP v2.0.0 |
| 上下文压缩子程序 | v2.0.0 砍除，宿主已有 | ROADMAP v2.0.0 |
| 会话持久恢复 | v2.0.0 砍除，宿主层职责 | ROADMAP v2.0.0 |
| 内核沙箱 | v2.0.0 砍除，宿主层职责 | ROADMAP v2.0.0 |
| 扩展/插件体系 | v2.0.0 砍除，单家冷门 | ROADMAP v2.0.0 |
| OpenCode 优先于 Gemini CLI 的设计参考 | 研究阶段讨论，最终六家等权重 | references/inspiration.md |

---

## 9. 已知问题 & Bug

| 问题 | 状态 | 解决方式 |
|---|---|---|
| `tests/` 目录不存在 | 已知，按 Bob 指令不重建 | 按需响应问题，不主动维护 |
| `benchmarks/` 报告冗余（v180 后） | 已清理，保留 run_v180.py + protocol.md | v2.1.0 已执行 |
| `hermes-code-agent.md`（本地构建笔记）被意外推送 | 已撤回 commit cb62f13 | .gitignore 永久拦截 |
| `make_release.py` 临时脚本 | 已删除 | 改用 Python 一行式 curl 调用 |
| `gh` CLI 不可用 | 已知 | 用 curl + token 手动建 Release |

---

## 10. API / 数据结构 / 配置

### hca_gate.py 数据结构（`.hca_state.json` — 项目内）

```json
{
  "steps": 0,
  "redfix": {"verify": 0, "patch": 0},
  "doom": [],              // action tag sha1 历史
  "fail_fp": [],           // failure fingerprint 历史（v1.6+）
  "git_head": "...",       // 用于 stale 检测
  "snapshots": [],         // {id, ref, timestamp}
  "tokens_verify": [],     // 最近 20 条 telemetry
  "autocommits": 0,
  "budget_fired": {}
}
```

### skill_state.json（安装副本内，不进 git）

```json
{
  "last_check_ts": 1788075511.655,   // epoch，72h 节流
  "next_prompt_ts": 0,               // epoch，选 B 后 3d 冷却
  "pending": null                    // null 或 {remote, checked_at, local}
}
```

### cmd_policy.yaml（危险命令策略）

```yaml
default_decision: confirm
rules:
  - { pattern: ["git", "push", "--force"], decision: deny, reason: "force push to any branch" }
  # ... 更多规则
```

### 环境变量

| 变量 | 用途 |
|---|---|
| `BENCH_MODEL` | 基准测试指定模型（逗号分隔，支持多模型轮换） |
| `HERMES_HOME` | 默认 `/opt/data` |
| `NO_PROXY` | 本地网段（旁路由配置） |

---

## 11. 运行方式

### 安装（一次性）
```bash
# 把 hermes-code-agent/ 复制到 Hermes skills 目录
cp -r /opt/data/workspace/hermes-code-agent /opt/data/skills/hermes-code-agent
# 或通过 Hermes TUI 菜单 u. 更新 hermes-code-agent
```

### 使用
在 Hermes chat 中直接说：
- "build X"
- "fix bug in Y"
- "refactor Z"

Skill 自动触发 hard loop，无需额外配置。

### 调试子命令
```bash
python scripts/hca_gate.py update-status    # 查看节流指针
python scripts/hca_gate.py state show       # 查看循环计数器
python scripts/hca_gate.py compact          # 手动压缩 state
python scripts/hca_gate.py locate file.py <<< "snippet"  # 模糊定位
python scripts/hca_gate.py check_cmd "rm -rf /"           # 危险命令检测
```

### 升级
```bash
# 手动触发
python scripts/hca_gate.py update-check --force
python scripts/hca_gate.py update-apply     # 需先有 pending

# 正常流程（GATE 后自动弹 A/B）
```

---

## 12. 测试情况

**自测状态**：
- `tests/test_hca_gate.py` 已删除（v2.1.0 清理）
- **`tests/test_apply.py`（v2.4.0 起）**：16 项回归检查，纯 stdlib
  - 运行：`python tests/test_apply.py`（或 `python -m pytest tests/`）
  - 覆盖：多 hunk / 同文件多 block / 新建文件 / 多文件回滚 / 二进制拒绝 /
    删除+重命名拒绝 / 路径安全 4 项 / 子目录锚定 git 根 / autocommit 密钥保护 / 超时杀进程组
- **本项目现已可自校验**：`pyproject.toml` 提供项目标记，`detect` → `verify` → autocommit 全链路可用
- Benchmark：`run_v180.py` 已删除（调用 v1.8.2 砍除的 `guard record`，死代码）；
  保留 `protocol.md`（协议定义）+ `test_ttlcache.py`（可复用裁判）

**最近一次验证**（v2.4.0，2026-09-12）：
- `python tests/test_apply.py`：16/16 通过 ✓
- `hca_gate.py detect`：识别 `.venv/bin/python -m pytest -q` ✓
- `hca_gate.py verify`：全绿 + autocommit 落盘 ✓

---

## 13. TODO（按优先级）

### P0（阻塞性问题）
- 无

### P1（功能完善）
1. **verify 命令自动探测增强**：置信度排序 + 候选 fallback（ChatGPT 建议，当前探测失败即放弃）
2. **`\ No newline at end of file` 语义**：apply 当前忽略该标记，无末尾换行的文件会被打上换行
3. **非 pytest 测试框架的 failure fingerprint**：当前只认 pytest 的 `FAILED` 行，go/cargo/npm 不触发语义 doom
4. **多模型轮换基准测试**：中档模型轨常态化（需可用模型额度）

### P2（体验优化）
5. SKILL.md 中 locate 段落的中文翻译对齐（当前混合中英）
6. 升级后自动写 changelog 到 `backups/`
7. `run(cmd.split())` 对带引号参数会切错（低危，可换 shlex）

### P3（长期）
8. Hermes plugin / ACP-server 程序级硬门禁（roadmap 远期目标，"apply 是唯一入口"目前仍是提示词纪律）
9. 更细粒度的 token 消耗追踪（per-step 维度）

---

## 14. 设计约束（不可破坏）

以下条目在任何修改中**必须保持**，破坏即回归：

| # | 约束 | 理由 |
|---|---|---|
| 1 | **verify 前必须 quickcheck** | 秒级语法失败不进测试套件，省 token |
| 2 | **三步渠道分离**（PATCH / STATIC / TEST） | 避免在不同失败信号上乱修 |
| 3 | **PLAN 阶段禁止 edit** | Plan/Build 分离是 Codex/Cline 核心机制 |
| 4 | **hca_gate.py 是 stdlib-only** | 无 pip install 依赖，任何环境可跑 |
| 5 | **exit-code 语义固定**（0/1/2/3） | 模型靠 exit code 判断状态，不能随意改 |
| 6 | **apply 四级匹配不跳级** | exact→rstrip→trim→Unicode-norm，跳过级别会漏匹配 |
| 7 | **事务性提交**（v2.4.0 起） | 任一 hunk 失败 → 整补丁不落盘；任一文件提交失败 → 全量回滚 |
| 8 | **doomcheck 同 tag 3 次熔断** | 盲修循环检测，不能改阈值 |
| 9 | **failure fingerprint 集合语义** | 序无关、计数无关，有修复立即重置 |
| 10 | **skill_state.json 不在项目目录** | 升级豁免；放在 `/opt/data/skills/hermes-code-agent/` |
| 11 | **72h 检测节流 + 3d 提示冷却** | Bob 2026-08-28 两次确认，不可缩短 |
| 12 | **六家对标零原创原则** | Bob 2026-08-24 拍板；任何新功能必须有对标 |
| 13 | **README 中文主体，简洁** | Bob 2026-08-26 明确要求 |
| 14 | **版本号三处同步**（SKILL.md + ROADMAP + git tag） | CI 从 tag 打 Release，漏改会跳号 |

---

## 15. 环境要求

| 组件 | 要求 |
|---|---|
| Python | 3.8+（stdlib only：argparse, hashlib, json, os, re, subprocess, sys, shutil, tempfile, time, urllib.request, tarfile） |
| Git | 必须（snapshot/restore/plancheck 依赖） |
| Hermes | 任意版本（Skill 形态不依赖特定 Hermes 版本） |
| 网络 | 仅 update-check 需要（5s 超时，失败静默降级） |
| OS | Linux/macOS/Windows（stdlib 跨平台） |

**旁路由配置**（Bob 环境）：
- 旁路由：192.168.2.5，HTTP 7890 / Mixed 7893
- NO_PROXY：192.168.0.0/16, 192.168.2.0/24, 10.0.0.0/8, 172.16.0.0/12, .local
- Hermes 走 7890，camofox 走 7893

---

## 16. 关键文件位置速查

| 文件 | 路径 | 用途 |
|---|---|---|
| Skill 主文件 | `/opt/data/workspace/hermes-code-agent/SKILL.md` | 入口定义 |
| 门禁脚本 | `/opt/data/workspace/hermes-code-agent/scripts/hca_gate.py` | 核心逻辑 |
| 安装副本 | `/opt/data/skills/hermes-code-agent/` | Hermes 加载源 |
| 节流指针 | `/opt/data/skills/hermes-code-agent/skill_state.json` | 升级状态 |
| 项目状态 | `<项目目录>/.hca_state.json` | 循环计数器 |
| 危险命令策略 | `/opt/data/workspace/hermes-code-agent/scripts/cmd_policy.yaml` | 策略表 |
| 全局约定模板 | `/opt/data/workspace/hermes-code-agent/templates/CONVENTIONS.md` | 随 Skill 分发 |
| GitHub Release | https://github.com/bobvane/hermes-code-agent/releases/tag/v2.1.1 | 升级源 |

---

## 17. 版本历史摘要

| 版本 | 日期 | 关键变更 |
|---|---|---|
| v0.1.0 | 2026-08-24 | 初始 Skeleton |
| v0.6.0 | 2026-08-24 | 四家额外研究 + 模型感知上下文 |
| v1.0.0 | 2026-08-25 | 正式发布（文档重写 + 3 题基准） |
| v1.2.1 | 2026-08-25 | guard + venv 自举 |
| v1.6.0 | 2026-08-25 | doomcheck 语义级检测 |
| v1.8.0 | 2026-08-25 | auto-commit + patch 三级 + repomap |
| v2.0.0 | 2026-08-26 | 两层规则 + repo map + patch 容错 |
| v2.0.1 | 2026-08-26 | locate 重写 |
| v2.1.0 | 2026-08-27 | feature-complete 里程碑 |
| **v2.1.1** | **2026-09-07** | **自检升级（72h 节流 + 3d 冷却）** |

---

*本文档由 hermes-code-agent Skill 自身生成，version: 2.1.1。任何修改请同步更新本文档顶部的版本声明。*
