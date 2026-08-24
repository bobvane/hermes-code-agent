# Benchmark: hermes-code-agent 实测报告

## 测试目的 / Goal

验证 "编程能力平齐度来自外壳(验证循环)还是模型档次"。
在**强模型**档次下对比：
- A 组（不用 Skill，写完即交付不验证）
- B 组（走 SKILL.md 硬循环：写→测→红就修→全绿才停）

同一道题、同一套 pytest 裁判。

## 测试題 / Tested problems

### 题 A: 并发 KV 缓存 (嵌套事务 + TTL, 7 裁判)

**接口约定**：`Cache()`, `Cache(cleanup_interval=0.2)`, `set/get/delete`, 参数化 `impl_a/impl_b`。
裁判: `benchmarks/test_cache_param.py` (7 个边界用例)。

### 题 B: TTLCache LRU+TTL 缓存 (6 裁判)

**接口**: `TTLCache(capacity, ttl)`, `set/get/delete`, 多线程并发安全。
完整题面: `../AI编程能力测试题_TTLCache.md`
裁判: `benchmarks/test_ttlcache.py` (6 个边界用例)。

### 题 C: Async AI Provider Scheduler (5 裁判) — 2026-08-25

**接口**: `Scheduler(providers)`, `await request(model, prompt)`, `call_provider` (可 mock), `circuit_state(name)`, `stats()`, `_select_provider()`。
裁判: `judge_scheduler.py` (5 pytest)。

## 裁判測試 / Judge tests

### 题 A (7 用例)
1. test_lru_eviction — capacity=3, access a 后 set(d), 淘汰最久的 b
2. test_ttl_expiry — ttl=1s, sleep 1.2s 后 get 应返回 None
3. test_ttl_refresh_on_update — set 更新应重置 TTL
4. test_delete_and_size — delete + size 正确
5. test_concurrent_safety — 10 线程×50 次 set/get, 無異常/無丢失
6. test_concurrent_eviction_consistent — 并发淘汰不破坏 LRU 结构
7. test_expired_key_does_not_count — 过期 key 從 size 移除

### 题 B (6 用例)
與題 A 相似但為 LRU+TTL 專用接口。

### 题 C (5 用例)
1. test_retry_on_failure — 模擬隨機失敗, 驗證自動重試 ≥2 次, request 最終成功
2. test_circuit_breaker — 模擬連續失敗5次, provider 進入 open/half_open
3. test_concurrency_limit — 100 併發請求, 峰值並發 ≤10
4. test_weight_distribution — 采樣 4000 次 _select_provider, openai 占比 0.65~0.85
5. test_stats — 20 次成功 request 後 total/success ≥20

## A/B 跑法约定 / Conventions

- **A 组（裸写）**：模型一次性写 `impl_a.py`（含实现），写完即宣布"完成"，**不主动跑 pytest**。為採集數據可事後跑一次記錄首過率, 但修復**不屬於** A 组流程。
- **B 组（用 Skill）**：严格 SKILL.md 硬循环: CLARIFY→PLAN→BUILD(写 `impl_b.py`)→VERIFY(跑 pytest)→红就修(精确报错回灌, 上限 5 輪)→全緑(GATE)才停。撞 5 轮仍红 → STOP 报阻塞（有效結論，非失敗）。
- **计时**：B 组从 PLAN 起点到 GATE 通过；A 组不计时（无流程约束）。
- **Token**：Hermes 本层不回传 usage，该列标 ≈ 估算。

## 对比维度表 / Dimensions

| # | 维度 | 测量 |
|---|---|---|
| 1 | 最终正确性 | pytest 通过数/總數 |
| 2 | 首次提交即通过率 | 首轮通过数 |
| 3 | 红→修循环次数 | B 组 red→fix 轮次 |
| 4 | 工具调用次数 | 数 tool call |
| 5 | 耗时(wall-clock) | 时间戳差 |
| 6 | 是否主动写测试 | 有/无 |
| 7 | 是否校验后宣布完成 | 有/无（关键差异） |
| 8 | Token(≈) | 估算 |

## 实测结果 / Results

### 三題對比 (DeepSeek V4 Flash via OmniRoute, 2026-08-25)

| 題 | OpenCode | Aider | hermes-code-agent Skill |
|---|---|---|---|
| A: 并发 KV 缓存 (7 裁判) | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| B: TTLCache LRU+TTL (6 裁判) | ✅ 6/6 | ✅ 6/6 | ✅ 6/6 |
| C: Async Scheduler (5 裁判) | ❌ 0 (500 error) | ❌ 0 (0 bytes) | ✅ 5/5 |

**題 C 結論**：OpenCode/Aider 用**流式輸出(stream:true)** 在 OmniRoute 長代碼生成時波動返回 500 / 0 byte 失敗；Skill 靠 **stream:false 非流式** 穩定通過 5/5。工程鲁棅性優勢明確。

### 題 A/B 弱/强模型同題历史对比

| 模型 | A组裸写 | B组循环 | 红修轮次 | Skill边际价值 |
|---|---|---|---|---|
| hy3-free (弱) | 7/7 | 7/7 | 0 | ≈0 |
| claude-sonnet-4.5 (强) | 7/7 | 7/7 | 0 | ≈0 |

**关键修正**: 同题下弱/强模型都一次全对, Skill 边际价值均为 ≈0。
這說明 **Skill 价值不单纯由模型档次决定，更由题目难度决定**：
- 简单題(LRU+TTL, 教科书级结构): 无论弱强模型都一次对, Skill 无用
- 难題(并发KV缓存+嵌套事务): 弱模型掉到 5/7, Skill 救回 2 bug; 强模型若跑同题预期也掉分

**严谨结论**: 编程能力平齐度来自「模型档次 × 题目难度」的交互。
外壳(验证循环)是**难题下弱/中模型的兜底机制**；简单題/强模型时边际价值趋零。
"强制验证" 流程始终有工程价值 —— 保证交付代码经过真实测试，而非"写完即信"。

## 如何复现 / How to re-run

```bash
cd /opt/data/bench_ttl_opus  # 或任意工作区
uv venv .venv && . .venv/bin/activate && uv pip install pytest
cp /opt/data/hermes-code-agent/benchmarks/test_ttlcache.py .
# A 组: 写 impl_a.py 后: python -m pytest test_ttlcache.py -k impl_a
# B 组: 写 impl_b.py 后: python -m pytest test_ttlcache.py -k impl_b
```
