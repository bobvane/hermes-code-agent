# Benchmark: hermes-code-agent vs 裸写 — 弱/中/强模型跨档对比

## 目的
验证"编程能力平齐度来自外壳(验证循环)还是模型档次"。同一道题、同一套 pytest 裁判，
分别测：A组(不用 Skill, 写完即交付不验证) vs B组(走 SKILL.md 硬循环: 写→测→红就修→全绿才停)。
在不同模型档次下重复，观察差异是否随模型增强而缩小/反转。

## 测试题 (Prompt 原文 — 直接发给模型)
请用 Python 从零实现一个支持事务和 TTL（过期时间）的高并发内存 Key-Value 缓存系统。
要求：
1. 基本功能：Set(key, val, ttl), Get(key), Delete(key)。
2. 嵌套事务：Begin(), Commit(), Rollback()。支持嵌套（事务A中开B，B提交仅合并到A，
   仅A提交才最终持久化；B回滚不影响A已有修改）。
3. TTL：惰性删除 + 定期清理结合；事务执行期间 Key 过期行为符合一致性
   （事务开启时未过期的 Key，事务内被读取不能突变）。
4. 线程安全：高并发读写，细粒度锁（读写锁/分段锁），避免全局大锁，防死锁/内存泄漏。
提供完整可运行实现 + 单元测试（嵌套事务 + 并发读写场景）。

## 裁判测试 (pytest, 两组共用同一份, 保证公平)
文件: `benchmarks/test_cache_param.py`
参数化 fixture `module_name ∈ {impl_a, impl_b}`，A组实现存 `impl_a.py`、B组 `impl_b.py`。
7 个用例（边界触发）：
1. test_set_get_delete          — 基础
2. test_nested_rollback_isolation     — 子回滚不影响父
3. test_nested_child_commit_then_parent_rollback — 子提交合并父, 父回滚全丢
4. test_concurrent_increment    — 8线程×50次 CAS 自增, 无丢失更新
5. test_ttl_lazy_expiry         — 惰性删除
6. test_active_cleanup_no_clobber_txn — 事务内 key 不因 TTL 清理消失(快照隔离)
7. test_cleanup_thread_stops    — 后台线程 shutdown() 后真正退出(无泄漏)

## A/B 跑法约定
- A组(裸写): 模型一次性写 impl_a.py (含实现), 写完即宣布"完成", **不主动跑 pytest**。
  为采集数据可事后跑一次记录首过率, 但修复不属于 A组流程。
- B组(用 Skill): 严格 SKILL.md 硬循环:
  CLARIFY→PLAN→BUILD(写 impl_b.py)→VERIFY(跑 pytest)→红就修(精确报错回灌, 上限5轮)
  →全绿(GATE)才停。撞5轮仍红 → STOP 报阻塞(有效结论, 非失败)。
- 计时: B组从 PLAN 起点到 GATE 通过; A组不计时(无流程约束)。
- Token: Hermes 本层不回传 usage, 该列标 ≈ 估算。

## 对比维度表
| # | 维度 | 测量 |
|---|---|---|
| 1 | 最终正确性 | pytest 通过数/7 |
| 2 | 首次提交即通过率 | 首轮通过数 |
| 3 | 红→修循环次数 | B组 red→fix 轮次 |
| 4 | 工具调用次数 | 数 tool call |
| 5 | 耗时(wall-clock) | 时间戳差 |
| 6 | 是否主动写测试 | 有/无 |
| 7 | 是否校验后宣布完成 | 有/无(关键差异) |
| 8 | Token(≈) | 估算 |

## 已测结果
### hy3-free (弱模型, 2026-08-25)
| 维度 | A组 | B组 |
|---|---|---|
| 正确性 | 5/7 | 7/7 |
| 首过率 | 5/7 | 3/7 |
| 红修轮次 | 0 | 3 |
| 工具调用 | 1 | ~8 |
| 耗时 | 未计 | 122.1s |
| 主动写测试 | 是(不跑) | 是(强制跑) |
| 校验后宣布 | 否 | 是 |
| Token(≈) | 少 | 多3-4× |
结论: Skill 在难题下价值爆发 — A组带2核心bug交付, B组3轮修全绿(含事务内TTL快照隔离)。

### deepseekv4flash (中模型) — 待测
### 强模型(GPT-5级) — 待测

## 复现命令
```bash
cd benchmarks && uv venv .venv && . .venv/bin/activate && uv pip install pytest
# A组: 写 impl_a.py 后: python -m pytest test_cache_param.py -k impl_a
# B组: 写 impl_b.py 后: python -m pytest test_cache_param.py -k impl_b
```
