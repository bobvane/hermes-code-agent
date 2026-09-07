# Current Task

## 当前目标
hermes-code-agent v2.3.0 单一改码入口已完成（砍掉 `patch` 子命令），当前处于**稳定运行阶段**。

## 当前进度
- [x] v2.1.0 feature-complete 里程碑（2026-08-27）
- [x] v2.1.1 自检升级功能（2026-09-07）
- [x] v2.2.0 安全硬化（2026-09-07）：
  - [x] `safe_repo_path()` 路径校验
  - [x] `apply` 两阶段原子写入
  - [x] `update-apply` SHA-256 校验
  - [x] `check_cmd` 解释器逃逸拦截
- [x] v2.3.0 单一改码入口（2026-09-07）：
  - [x] 砍掉 `cmd_patch()` + `_unified_diff_blocks()` + `_wsfree_*` 共 130 行
  - [x] 移除 argparse `patch` 注册 + dispatch table 条目
  - [x] SKILL.md 全部 `patch` 引用替换为 `apply`
  - [x] README 对照表更新
  - [x] ROADMAP.md v2.3.0 + v2.2.0 条目
  - [x] 版本号 2.2.0 → 2.3.0（SKILL.md）
  - [x] Smoke test：syntax OK、apply 修改成功、`patch` 子命令清晰报错

## 当前正在处理
无。等待 Bob 的新指令。

## 最近一次修改
- **v2.3.0 commit**（2026-09-07）：single edit entry point
  - hca_gate.py: 删除 `cmd_patch()`/`_unified_diff_blocks()`/`_wsfree_count`/`_wsfree_iter`/`_wsfree_span`（约 130 行），删除 argparse `patch` 子命令注册，删除 dispatch table 的 `patch` 条目
  - SKILL.md: PLAN 模式禁令去掉 `patch`，PATCH 通道 trigger 改为 `apply`，「Preferred edit path」段落重写（强调 v2.3.0 `apply` 是唯一入口），L1 审批表更新，version 2.2.0 → 2.3.0
  - README.md: 对照表「补丁容错应用」改为「四级匹配 + 原子写入」
  - ROADMAP.md: v2.3.0 条目 + 保留 v2.2.0

## 当前问题
无阻塞性问题。

## 下一步（按优先级）
1. **等待 Bob 的新需求** — 当前无活跃开发任务
2. 如需要新功能：检查 ROADMAP.md "Next steps" 章节确认优先级
3. 如需发新版本：遵循版本规则（末位 0-9 递增，满 9 进位），三处同步（SKILL.md + ROADMAP + git tag）
4. 如需回归验证：运行 `python scripts/hca_gate.py update-status` 确认节流指针正常

---

*最后更新：2026-09-07（v2.3.0 交付完成）*
