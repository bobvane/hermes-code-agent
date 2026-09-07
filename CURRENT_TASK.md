# Current Task

## 当前目标
hermes-code-agent v2.2.0 安全硬化已完成交付，当前处于**稳定运行阶段**。

## 当前进度
- [x] v2.1.0 feature-complete 里程碑（2026-08-27）
- [x] v2.1.1 自检升级功能（2026-09-07）
- [x] v2.2.0 安全硬化（2026-09-07）：
  - [x] `safe_repo_path()` 路径校验（拒绝 `..` 穿越、绝对路径、`.git/`、受保护文件、逃逸符号链接）
  - [x] `apply` 两阶段原子写入（内存预验证 + `os.replace()`）
  - [x] `update-apply` SHA-256 校验（拉 `.sha256` sidecar 比对 + `--skip-verify` 逃生口）
  - [x] `check_cmd` 解释器逃逸拦截（`python -c`/`node -e`/`bash -c`/`find -exec`/`xargs`/`env`）
  - [x] `patch` tier3 输出 WARNING
  - [x] `detect` 加 project-script review 提示
  - [x] README 加「系统支持」章节（平台/依赖/网络/无网络环境）

## 当前正在处理
无。等待 Bob 的新指令。

## 最近一次修改
- **v2.2.0 commit**（2026-09-07）：security hardening
  - hca_gate.py:
    - 新增 `safe_repo_path()` 函数（路径校验）
    - `apply_seek_patch_file` 改为只返回新内容，**不**直接写盘
    - `cmd_apply` 改两阶段：内存预验证 → 统一 `os.replace()` 写入
    - `cmd_patch` 加 `safe_repo_path` 校验，tier3 输出 WARNING
    - 新增 `_check_interpreter_escape()` 函数
    - `cmd_check_cmd` 集成解释器逃逸检测
    - `cmd_update_apply` 加 SHA-256 sidecar 校验 + `--skip-verify` 参数
    - `cmd_detect` 加 project-script review 提示
  - README.md: 加「系统支持」章节
  - SKILL.md: version 2.1.1 → 2.2.0
  - ROADMAP.md: v2.2.0 条目

## 当前问题
无阻塞性问题。

## 下一步（按优先级）
1. **等待 Bob 的新需求** — 当前无活跃开发任务
2. 如需要新功能：检查 ROADMAP.md "Next steps" 章节确认优先级
3. 如需发新版本：遵循版本规则（末位 0-9 递增，满 9 进位），三处同步（SKILL.md + ROADMAP + git tag）
4. 如需回归验证：运行 `python scripts/hca_gate.py update-status` 确认节流指针正常

---

*最后更新：2026-09-07（v2.2.0 交付完成）*
