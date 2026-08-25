# 基准协议 / Benchmark Protocol (v1 固化 2026-08-25)

> 可重复的 A/B 基准协议。目标：任何 skill 改动后，同协议重跑即可归因边际收益。
> 指标对应 ROADMAP 目标体系：北极星=难题首过率；约束=tokens/题 + 红→修轮次 + wall-clock/题。

## 固定要素（改动需升协议版本）

| 要素 | 值 |
|---|---|
| 题目 | 嵌套事务+TTL+并发 KVStore（TASK.md，11 用例裁判已验证可解） |
| 裁判 | test_kvstore_judge.py（共享 pytest，禁止被测模型修改；hca_gate guard 校验） |
| 重复次数 | N≥3 取均值 |
| A组 | 无 harness：只给题面，明确"写完即完成，不运行测试" |
| B组 | 带 harness：硬性标准=hca_gate verify exit 0 才算完成 |
| 工作目录 | /opt/data/workspace/hca-bench-<date>/（测完删除） |
| 环境 | .venv + pytest 预装（排除环境噪声）；裁判文件先 guard record |

## 记录字段（每组每次运行一行）

```
run | group | model | first_pass_rate | redfix_cycles | tokens≈ | wall_clock | fake_done? | converged?
```

- first_pass_rate: 首次 verify/pytest 通过用例数 / 11
- fake_done?: 是否在未全绿时宣布完成
- converged?: 红→修循环是否收敛到全绿

## 判读规则

- B 相对 A 的首过率提升 ≥2 用例 → harness 有实证价值；
- B 组撞 5 轮上限未收敛 → 能力天花板，记录为有效结论非 skill 失败；
- 出现新失败模式（假完成/改裁判/绕 gate/上下文崩溃）→ 单独立项，反哺 hca_gate。

## 历史

- v1 协议(2026-08-25): 由 4 组探索性实验(ministral-8b/qwen3-8b/laguna-s-2.1)固化而成。
