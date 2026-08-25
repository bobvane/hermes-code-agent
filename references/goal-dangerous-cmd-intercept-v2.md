# 开发目标：危险命令拦截 v2（Codex × Gemini CLI 强强联合版）

> 状态：已定目标，暂缓实施。Bob 于 2026-08-25 拍板计入开发计划，扒源码工作等后续指示。
> 最强两家：Codex CLI（execpolicy 策略引擎）× Gemini CLI（白名单+注入特征检测）。

## 合成哲学

**Codex 给裁决引擎结构（三态前缀表），Gemini 给语义识别层（注入特征）。**
移植的不是文档描述，是两家的引擎本体——确定性代码转译为 Python，裁决结果与原版一致。

## 两家引擎拆解

### Codex execpolicy（codex-rs/execpolicy + config/requirements_exec_policy.rs）
- 三态前缀规则表：allow / deny / require-approval，命令串逐段解析
- 最长前缀匹配 + 星号通配
- `RequirementsExecPolicyDecisionToml` 结构化裁决结果

### Gemini CLI
- 双层确认：安全模式白名单直接放行；白名单外展示**完整命令原文**给用户确认
- 注入特征检测（六家唯一做语义级危险识别的）：命令替换 `$()`/反引号、管道到 sh、重定向覆盖系统文件等组合技

## 移植可行性结论

全部为确定性代码，不依赖宿主特权能力（不同于工具过滤/请求路由）：
| 组成 | 本质 | Python 移植 |
|---|---|---|
| Codex 前缀规则表 | 结构化数据 | ✓ 转 YAML/JSON |
| 前缀匹配算法 | 字符串逻辑 ~百行 | ✓ |
| Gemini 白名单+原文确认流 | 放行逻辑+clarify | ✓ |
| 注入特征检测 | 正则+启发式 | ✓ |

## 开发目标内容

1. **数据层**：`scripts/cmd_policy.yaml` —— Codex 三态前缀表 + Gemini 安全白名单 + 注入特征清单
2. **引擎层**：hca_gate.py 新增 `check_cmd` 子命令——最长前缀匹配+通配符+注入扫描，返回三态：
   - ALLOW → 放行
   - DENY → 拦截+原因
   - CONFIRM → 输出完整命令原文，用户 clarify 批准后执行
3. **接入层**：SKILL.md 规则"非只读终端命令执行前必须先 check_cmd"
4. 与 goal-permission-tiers-v2.md 四档表衔接：check_cmd 是 L2/L3 的机器裁决器

## 形态限制

仅剩一条老问题：模型须自觉先调脚本；忘调由事后审计兜底。

## 实施前置

- [ ] 扒取 Codex execpolicy 完整规则表与匹配算法源码（等 Bob 指示）
- [ ] 扒取 Gemini CLI 白名单默认值与注入检测正则
