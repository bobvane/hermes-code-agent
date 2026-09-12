# Current Task

## 当前目标
hermes-code-agent v2.4.0 **可靠性版本**已交付：不加任何新 Agent 功能，专修"文档宣称的确定性高于代码实际提供的确定性"。

## 当前进度
- [x] v2.1.x feature-complete + 自检升级
- [x] v2.2.0 安全硬化（路径校验 / SHA-256 / 解释器逃逸拦截）
- [x] v2.3.0 单一改码入口（砍 `patch`）
- [x] **v2.4.0 可靠性版本（2026-09-12）**：
  - [x] P0 `autocommit` 密钥保护（`.env` / `*.key` 不再被提交）
  - [x] P0 同文件多 block 链式叠加（此前第一次改动静默丢失）
  - [x] P0 `apply` 多文件事务提交 + 失败全量回滚
  - [x] P0 `run()` 真杀进程组（`Popen` + `killpg`）
  - [x] P0 二进制文件结构化拒绝
  - [x] P1 `mkstemp` / 删除重命名显式拒绝 / git 根锚定 / runner 提示 / `.gitignore` / 去 `--force` / repomap 截断告警
  - [x] 测试：`tests/test_apply.py`（16 项，纯 stdlib）+ `pyproject.toml`
  - [x] 文档漂移整肃（goal-*.md 状态行 ×9、死引用、README 畸形表格）
  - [x] 删除死代码 `benchmarks/run_v180.py`

## 当前正在处理
无。等待 Bob 的新指令。

## 最近一次修改
- **v2.4.0**（2026-09-12）：reliability release
  - `scripts/hca_gate.py`：
    - 新增 `SECRET_PATH_RE` + autocommit 敏感路径 `git reset`
    - `apply_seek_patch_file(path, hunks, base_text=None)` — 支持链式叠加
    - `cmd_apply` phase 1 用 `working` dict、phase 2 事务提交 + 回滚
    - `run()` 改 `Popen` + `communicate(timeout)` + `killpg(p.pid)`
    - 新增 `repo_root()`（git toplevel）；`safe_repo_path` 改用它
    - 新增 `runner_fix_hint()`；`detect`/`verify` 无 runner 时输出
    - `parse_patch` 显式拒绝 delete / rename / binary
    - repomap 截断 WARNING
  - 新增 `tests/test_apply.py`（16 项）+ `pyproject.toml`
  - 删除 `benchmarks/run_v180.py`
  - `.gitignore` 加 `.hca_state.json` / `.venv/`
  - SKILL.md / README.md / ROADMAP.md / PROJECT_CONTEXT.md / references 全面对齐

## 当前问题
无阻塞性问题。

## 已知但未做（下一版候选）
1. detect 置信度排序 + 候选 fallback
2. `\ No newline at end of file` 语义（apply 当前忽略）
3. 非 pytest 框架的 failure fingerprint（go/cargo/npm 不触发语义 doom）
4. `run(cmd.split())` 带引号参数会切错

## 下一步
1. **等待 Bob 的新需求**
2. 发新版流程见 SKILL.md「Release procedure」：改 dev → bump 版本（三处同步）→ git tag → GitHub Release → **不手动同步安装副本**，让 Skill 自检升级
3. 回归验证：`python tests/test_apply.py`（应 16/16）

---

*最后更新：2026-09-12（v2.4.0 交付完成）*
