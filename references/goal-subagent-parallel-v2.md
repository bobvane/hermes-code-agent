# 开发目标：子代理并行 v2（OpenCode × Codex 强强联合版）

> 状态：已定目标，未实施。Bob 于 2026-08-25 拍板作为该功能的开发目标。
> 评判规则（Bob 定）：五项能力逐项裁决三方最优——OpenCode / Codex / Hermes(delegate_task)。
> "Hermes 能实现"不算数，要判断其方式是否真的最优；确实优于两家才采用。

## 五项能力逐项裁决

| # | 能力 | OpenCode | Codex | Hermes delegate_task | 裁决 | 目标采纳 |
|---|---|---|---|---|---|---|
| 1 | 委派为默认反射 | ✓ 提示词示例驱动成条件反射 | ✓ | 半——规则在 SKILL.md 但非强制反射 | **OpenCode**：示例驱动的"默认委派文化"最成熟；Codex 同理但无更优细节 | 采纳 OpenCode 方式：SKILL.md 强化"非平凡任务必须先评估拆分"为硬规则+触发清单 |
| 2 | 自包含任务书 | ✓ 完整任务书(目标/文件/产出/验证) | ✓ isolated session | ✓ 已有同规格要求(g目标/文件/产出物/验证命令+写vs研声明) | **Hermes 现状已达标**：我们的任务书纪律=两家的并集且含"写vs研"声明这一独有细节 | 保持现状 |
| 3 | 中途传话 | — 无 | ✓ send_message 单向传话 | ✓ steer 可实时纠偏、stop 可叫停，语义更强 | **Hermes**：steer 支持双向实时纠正,强于 Codex 单向 message | 保持现状(Hermes steer) |
| 4 | 生命周期管理动作集 | 部分(Task tool 基础动作) | ✓✓ spawn/wait/list/interrupt/followup 六件套 | 半——有 list/steer/stop+后台运行通知,缺 wait 阻塞等待与 followup 续任务 | **Codex**：六件套覆盖全生命周期最完整 | 采纳 Codex 编排协议:用 process(wait)/再次 delegate 组合模拟 wait 与 followup,写进 SKILL.md 标准编排序列 |
| 5 | 并发硬上限 | ✗ | ✓ AgentExecutionLimiter RAII 运行时强制 | ✓≤3 但属提示词软约束 | **Codex**：运行时硬限制优于提示词约束;Hermes 有子进程上限但 Skill 层无法配置 | 形态折中:保留≤3 软约束,标注形态限制(Skill 无法做运行时限流);Hermes 层已有 child cap 兜底 |

## 合成哲学

**OpenCode 给文化（什么时候拆活），Codex 给流程（拆完怎么管）。**
委派默认化解决"想不到拆"，生命周期六件套解决"拆了管不好"。Hermes 底座在传话/隔离两项天然占优，直接继承。

## 目标流程（融合版）

```
接到非平凡任务
→ 按触发清单评估：≥2 个独立文件级改动？宽泛只读探索？
   是 → 必须扇出（OpenCode 默认化）
→ 写自包含任务书（现状纪律保持）：目标/精确文件/产出物/验证命令/写vs研声明
→ spawn N 个 builder（N≤3）+ 1 个 reviewer 并行
→ 过程中：steer 实时纠偏 / stop 叫停失控者（Hermes 底座）
→ 全部返回后按 Codex 协议收尾：
   wait 确认无悬挂 → followup 补漏任务（如有）→ 合并
→ 合并树跑全项目 verify（非各自验证）→ GATE
```

## 实施清单（v1.8.4 候选，与计划/执行分离同版）

1. SKILL.md：把"≥2 独立文件改动必评估扇出"从建议升级为硬规则 + 触发条件清单（OpenCode）
2. SKILL.md：新增标准编排序列——wait 确认/followup 补漏/合并后统一 verify 的收尾协议（Codex）
3. 并发上限维持 ≤3，标注"Skill 层软约束"形态限制
4. 任务书纪律与 steer 不动（已是最优）

## 讨论纪要要点

- Bob 纠正评判标准："Hermes 能实现"不是理由，要证明方式最优才采用——逐项裁决后第2/3项 Hermes 现状胜出，予以保留
