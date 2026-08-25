# 开发目标：步数/花费封顶 v2（OpenCode × Codex 强强联合版）

> 状态：已定目标，未实施。Bob 于 2026-08-25 拍板。
> 形态限制（Bob 定）：物理禁工具做不到就不做。

## 关键发现（源码扒取实证，2026-08-25）

两家的"强制停止"实为**消息注入式软停止**，非进程级硬杀：

### Codex token_budget 机制（codex-rs/core/src/session/token_budget.rs + models-manager/models.json）
- 真实阈值（gpt-5.6-sol/terra/luna 全系一致）：
  - `reminder_threshold_tokens = 6144`（剩余<6144 注入提醒，去重只发一次）
  - `auto_compact_fallback_buffer_tokens = 16384`（自动压缩缓冲）
- 默认配置 threshold=None，数值由各模型 models.json 下发
- 两级手段全是注入消息引导模型自救：①context_window_reminder（含"用 notes 工具存进度"指令）②耗尽时 auto-compact 触发压缩
- **没有 kill/terminate**

### OpenCode steps 机制（packages/opencode/src/agent/agent.ts + session/prompt.ts）
- `steps` 字段默认 **Infinity**（不限制），用户配置才生效
- 到达最后一步：注入 `MAX_STEPS_PROMPT`（CRITICAL - 工具禁用、文本回复、总结已完成/未完成/下一步）+ 宿主物理不再执行 tool call
- 物理禁工具层 = 我们唯一不做的部分

## 合成哲学

**Codex 给计量与提醒分级（何时警告），OpenCode 给收尾协议（到顶怎么体面结束）。**
两家都没有硬终止——此前"他们硬终止我们只能软约束"的对比是误判，予以修正。

## 开发目标内容

1. 对齐 Codex 提醒细节：预算提醒**只发一次+固定模板**（含进度保存指令），去重防重发
2. 采纳 Codex 阈值思想：剩余预算 ≤ 阈值 → 一级提醒；红轮/工具调用数到软帽 → 收尾触发
3. 采纳 OpenCode MAX_STEPS 收尾话术：步数/预算到顶时输出结构化总结（已完成/未完成/下一步建议），不做无声熔断
4. 步骤上限显式声明化（OpenCode steps 字段思想）：SKILL.md 写明默认上限值而非隐式约定
5. 物理禁工具：形态限制，不做

## 实施清单（v1.8.4 候选）

- hca_gate.py doomcheck/state：提醒去重标记 + 固定提醒模板
- SKILL.md：MAX_STEPS 式收尾协议替换现有无声 exit2 熔断描述；写明显式步骤上限默认值
