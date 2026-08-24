# Benchmark: hermes-code-agent 实测报告（LRU+TTL 缓存题）

## 测试目的
验证"编程能力平齐度来自外壳(验证循环)还是模型档次"。
同一道题、同一套 pytest 裁判，在**强模型**档次下对比：
- A 组（不用 Skill，写完即交付不验证）
- B 组（走 SKILL.md 硬循环：写→测→红就修→全绿才停）

## 测试题（Prompt 原文）

**任务**：实现线程安全的 LRU 缓存，支持 TTL 自动过期。

```python
class TTLCache:
    def __init__(self, capacity, ttl):
        pass

    def set(self, key, value):
        # 新增/更新，超容量淘汰最久未用
        pass

    def get(self, key):
        # 存在且未过期返回 value，过期删除返回 None，更新 LRU
        pass

    def delete(self, key):
        pass

    def size(self):
        pass
```

**要求**：
- capacity 限制 + LRU 淘汰策略
- TTL 自动过期（get 时惰性删除）
- 多线程并发安全（不允许数据损坏/KeyError/size错误/LRU异常）
- get/set 平均时间复杂度 O(1)

**完整题面**：`/opt/data/workspace/AI编程能力测试题_TTLCache.md`（133 行）

## 裁判测试（pytest，A/B 共用）

文件：`benchmarks/test_ttlcache.py`，参数化 fixture `module_name ∈ {impl_a, impl_b}`。

7 个边界用例：
1. **test_lru_eviction**：capacity=3，访问 a 后 set(d)，应淘汰最久的 b
2. **test_ttl_expiry**：ttl=1 秒，sleep 1.2s 后 get 应返回 None
3. **test_ttl_refresh_on_update**：set 更新应重置 TTL 计时
4. **test_delete_and_size**：delete 删除 + size 正确
5. **test_concurrent_safety**：10 线程×50 次 set/get，无异常、无丢失
6. **test_concurrent_eviction_consistent**：并发淘汰不破坏 LRU 结构
7. **test_expired_key_does_not_count**：过期且被访问的 key 应从 size 移除

## A/B 跑法约定
- **A 组（裸写）**：模型一次性写 `impl_a.py`（含实现），写完即宣布"完成"，**不主动跑 pytest**。为采集数据可事后跑一次记录首过率，但修复不属于 A 组流程。
- **B 组（用 Skill）**：严格 SKILL.md 硬循环：CLARIFY→PLAN→BUILD(写 `impl_b.py`)→VERIFY(跑 pytest)→红就修（精确报错回灌，上限 5 轮）→全绿(GATE)才停。撞 5 轮仍红 → STOP 报阻塞（有效结论，非失败）。
- **计时**：B 组从 PLAN 起点到 GATE 通过；A 组不计时（无流程约束）。
- **Token**：Hermes 本层不回传 usage，该列标 ≈ 估算。

## 对比维度表
| # | 维度 | 测量 |
|---|---|---|
| 1 | 最终正确性 | pytest 通过数/7 |
| 2 | 首次提交即通过率 | 首轮通过数 |
| 3 | 红→修循环次数 | B 组 red→fix 轮次 |
| 4 | 工具调用次数 | 数 tool call |
| 5 | 耗时(wall-clock) | 时间戳差 |
| 6 | 是否主动写测试 | 有/无 |
| 7 | 是否校验后宣布完成 | 有/无（关键差异） |
| 8 | Token(≈) | 估算 |

## 实测结果

### claude-sonnet-4.5（强模型，2026-08-25）

| 维度 | A组 | B组 |
|---|---|---|
| 正确性 | 7/7 | 7/7 |
| 首过率 | 7/7 | 7/7 |
| 红修轮次 | 0 | 0 |
| 工具调用 | 2 | 2 |
| 耗时 | 极短 | 32.5s |
| 主动写测试 | 是（题目自带） | 否（跑裁判） |
| 校验后宣布 | 否 | 是 |
| Token(≈) | 少 | 略多 |

**结论**：强模型 A 组裸写一次全对，B 组硬循环首轮全绿无修复。**Skill 边际价值趋零**——验证步骤未发现任何 bug，循环变成"确认"而非"修复"。这正是预期的正确收窄：强模型自己不犯错，外壳(验证循环)无用武之地。

## 复现命令
```bash
cd /opt/data/bench_ttl_opus  # 或任意工作区
uv venv .venv && . .venv/bin/activate && uv pip install pytest
cp /opt/data/hermes-code-agent/benchmarks/test_ttlcache.py .
# A 组：写 impl_a.py 后：python -m pytest test_ttlcache.py -k impl_a
# B 组：写 impl_b.py 后：python -m pytest test_ttlcache.py -k impl_b
```

## 三档模型历史趋势（跨题汇总，仅供参考）

> ⚠️ 以下为**跨题**对比（弱/中模型跑「并发KV缓存」题，强模型跑「LRU+TTL」题），
> 因题目难度不同，不能直接作为"同题对比"结论。仅作模型能力档次的粗略参考。

| 模型档次 | 题目 | A组通过 | B组通过 | Skill边际价值 |
|---|---|---|---|---|
| 弱(hy3-free) | 并发KV缓存(难) | 5/7 | 7/7 | **大**（救2核心bug） |
| 中(deepseek-v4) | 并发KV缓存(难) | 6/7 | 7/7 | **中**（救1边界+死锁） |
| 强(claude-sonnet-4.5) | LRU+TTL缓存(易) | 7/7 | 7/7 | **≈0**（零修复） |

## 严格同题对比（LRU+TTL 缓存，三档模型)

> ✅ 以下为**同题**对比：hy3-free（弱）、claude-sonnet-4.5（强）都跑同一道 LRU+TTL 题。

| 模型 | A组裸写 | B组循环 | 红修轮次 | Skill边际价值 |
|---|---|---|---|---|
| hy3-free (弱) | 7/7 | 7/7 | 0 | **≈0** |
| claude-sonnet-4.5 (强) | 7/7 | 7/7 | 0 | **≈0** |

**关键修正**：同题下弱/强模型都一次全对，Skill 边际价值均为 ≈0。
这说明 **Skill 价值不单纯由模型档次决定，更由题目难度决定**：
- 简单题（LRU+TTL，教科书级结构）：无论弱强模型都一次对，Skill 无用
- 难题（并发KV缓存+嵌套事务）：弱模型掉到 5/7，Skill 救回 2 bug；强模型若跑同题预期也掉分

**严谨结论**：编程能力平齐度来自「模型档次 × 题目难度」的交互。
外壳(验证循环)是**难题下弱/中模型的兜底机制**；简单题或强模型跑简单题时边际价值趋零。
"强制验证"流程始终有工程价值——保证交付代码经过真实测试，而非"写完即信"。

### hy3-free 同题实测记录（2026-08-25, 补测）
- A组裸写：7/7（一次性写对，含并发安全/淘汰一致等边界）
- B组硬循环：7/7 首轮全绿，红修=0，耗时 26.9s
- 结论：本题对 hy3-free 属"一次对"档，Skill 在这题上无修复收益
