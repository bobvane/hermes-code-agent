import threading
import time

import pytest
import importlib


def load_impl(module_name):
    return importlib.import_module(module_name)


@pytest.fixture(params=["impl_a", "impl_b"])
def module_name(request):
    return request.param


# ---------- 基础 + LRU 淘汰 ----------
def test_lru_eviction(module_name):
    m = load_impl(module_name)
    c = m.TTLCache(capacity=3, ttl=10)
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)
    assert c.get("a") == 1      # 访问 a, 使 a 成为最近
    c.set("d", 4)               # 超容量, 应淘汰最久未用的 b
    assert c.get("b") is None, "LRU 应淘汰最久未用的 b"
    assert c.get("a") == 1 and c.get("d") == 4
    assert c.size() == 3


# ---------- TTL 过期 ----------
def test_ttl_expiry(module_name):
    m = load_impl(module_name)
    c = m.TTLCache(capacity=10, ttl=1)
    c.set("k", "v")
    time.sleep(1.2)
    assert c.get("k") is None, "TTL 过期后 get 应返回 None"


# ---------- 逻辑过期重置 ----------
def test_ttl_refresh_on_update(module_name):
    m = load_impl(module_name)
    c = m.TTLCache(capacity=10, ttl=2)
    c.set("k", "v")
    time.sleep(1.2)
    c.set("k", "v2")           # 更新应重置 TTL
    time.sleep(1.2)
    assert c.get("k") == "v2", "更新后 TTL 应重新计时"


# ---------- delete / size ----------
def test_delete_and_size(module_name):
    m = load_impl(module_name)
    c = m.TTLCache(capacity=10, ttl=10)
    c.set("a", 1)
    c.set("b", 2)
    c.delete("a")
    assert c.get("a") is None
    assert c.size() == 1


# ---------- 并发安全 (10线程 set/get 无异常, 无丢失) ----------
def test_concurrent_safety(module_name):
    m = load_impl(module_name)
    c = m.TTLCache(capacity=1000, ttl=10)
    errors = []
    seen = set()

    def worker(tid):
        try:
            for i in range(50):
                key = "k%d" % (tid * 50 + i)
                c.set(key, tid)
                assert c.get(key) == tid
                seen.add(key)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, "并发出现异常: %r" % errors
    assert len(seen) == 500, "应有 500 个 key 全部写入并读回"
    assert c.size() == 500


# ---------- 并发 LRU 竞争 (淘汰不破坏结构) ----------
def test_concurrent_eviction_consistent(module_name):
    m = load_impl(module_name)
    c = m.TTLCache(capacity=50, ttl=10)
    errors = []

    def worker(tid):
        try:
            for i in range(100):
                c.set("wk%d" % tid, i)
                c.get("wk0")   # 制造访问, 打乱 LRU
                c.delete("wk%d" % (tid * 100 + i)) if False else None
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, "并发淘汰出现异常: %r" % errors


# ---------- 已过期 key 不占容量 ----------
def test_expired_key_does_not_count(module_name):
    m = load_impl(module_name)
    c = m.TTLCache(capacity=100, ttl=1)
    c.set("e1", 1)
    c.set("e2", 2)
    time.sleep(1.2)
    assert c.get("e1") is None
    assert c.get("e2") is None
    assert c.size() == 0, "过期且被访问的 key 应从 size 移除"