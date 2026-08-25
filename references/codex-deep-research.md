# Codex CLI 深挖（codex-rs，浅克隆研读，2026-08）

已有蒸馏（inspiration.md 的 ModeKind/Guardian/Budget）之外的新机制：

## 可移植清单

1. **加权 rollout 预算 + 分级提醒**（`core/src/rollout_budget.rs:46-100`）
   `weighted_tokens_used += output*sampling_weight + non_cached_input*prefill_weight`，跨子 agent 线程共享记账；`reminder_at_remaining_tokens[]` 多阈值，剩余量跌破阈值时向模型注入"剩余 N tokens"的 ContextualUserFragment，且按 (thread_id, window_id, reminder_index) 去重防重发。超限 → `SessionBudgetExceeded` 终止。
   → 移植：hca_gate 现在只有硬上限；加**多阈值软提醒注入**（如 50%/20% 剩余时提示模型收敛），比一刀切中断更省首过率。

2. **TokenBudget 上下文窗口预算**（`core/src/session/token_budget.rs`, `core/src/context/token_budget_context.rs`）
   与 rollout 预算分开：管的是上下文窗口占用，含 `auto_compact_fallback_prompt` + buffer——接近窗口时先注入提醒、再自动 compact、compact 失败有 fallback prompt。双轨制（花费预算 vs 窗口预算）值得照搬。

3. **apply_patch 三级宽松匹配 seek_sequence**（`apply-patch/src/seek_sequence.rs:7-60`）
   匹配依次降级：精确 → rstrip → trim 双端；EOF chunk 先从文件尾试。`compute_replacements` 先收集全部 (start,len,new_lines) 再一次 apply（`file_update.rs:87-225`），避免行号漂移。多文件 patch = 一个文本协议（Add/Update/Delete/Move to:），可流式解析（`streaming_parser.rs:139 push_delta`）。
   → 移植：我们用 edit 工具逐处替换，弱模型易失败；一个带三级 fallback 的批量补丁应用器能显著提高编辑成功率。

4. **命令规范化做审批缓存**（`core/src/command_canonicalization.rs:11-30`）
   把 `/bin/bash -lc 'x'` 与 `bash -lc 'x'` 归一化后再匹配审批决策，避免重复弹审批。配合 Guardian fail-closed 自审。
   → 移植：hca_gate 的 guard 判定可对命令做归一化缓存，同形命令不重复审。

5. **输出截断策略**（`utils/output-truncation/src/lib.rs:12-28`）
   按 Bytes 或 Tokens 截断，截中间保头尾，并附"原始 token 数 + 总行数"警告头。比我们的双限摘要更细：**token 级中段截断 + 元信息回注**。

6. **turn diff 追踪器**（`core/src/turn_diff_tracker.rs:17-19`）
   每轮累积文件内容版本，生成 git 风格 per-turn diff，diff 计算限时 100ms 超时则退化为粗粒度。给 doomcheck/审查提供"本轮改了什么"的结构化输入。

7. **rollout 持久化格式**（`rollout/src/`）：JSONL 追加 + zst 透明压缩（`compression.rs:41-64`）、reverse_jsonl_scanner 从文件尾反向扫（恢复最近状态不用读全文件）、SQLite 索引并存。→ 我们的状态外置可用"JSONL+尾部反向扫描"替代整文件读。

8. **seccomp 网络沙箱细节**（`linux-sandbox/src/landlock.rs:165-268`）
   文件系统已改用 bubblewrap，Landlock 仅作 legacy 备份（ABI V5, BestEffort 兼容，NotEnforced 即报错=fail-closed）。网络限制是 seccomp 白名单式：默认 Allow，命中规则返回 EPERM；deny ptrace/process_vm/io_uring 防逃逸；Restricted 模式 deny connect/bind/sendto 等，但 socket 仅放行 AF_UNIX（条件规则 arg0≠AF_UNIX→EPERM），保留子进程 IPC；ProxyRouted 模式反过来只放 AF_INET/6 走本地 TCP bridge。PR_SET_NO_NEW_PRIVS 只在需要时设置以免破坏 setuid bwrap。
   → 对 Hermes 参考价值：若未来做本地执行沙箱，"seccomp 条件规则放行 unix socket + 本地代理桥"是最小可行方案；纯 Python 层面不可复制内核机制，但 fail-closed 校验（NotEnforced→报错）思想可移植到 guard。

## 不可移植及原因
- bwrap/seccomp/Landlock 内核机制：Hermes skill 是提示层+shell 编排，无特权安装过滤器的能力；只能借其策略分类（写根白名单/网络 deny 列表）写成 gate 规则。
- StreamingPatchParser / exec_server / SQLite state db：Rust 基础设施，超出 bash+python gate 的复杂度预算；取 JSONL 思路即可。
- Guardian 完整会话克隆：需二次模型调用基础设施，已有蒸馏版自审近似覆盖。
