import threading
import time

import pytest
import importlib


def load_impl(module_name):
    return importlib.import_module(module_name)


@pytest.fixture(params=["impl_a", "impl_b"])
def module_name(request):
    return request.param


# ---------- 基础功能 ----------
def test_set_get_delete(module_name):
    m = load_impl(module_name)
    c = m.Cache()
    c.set("a", 1, ttl=10)
    assert c.get("a") == 1
    c.delete("a")
    assert c.get("a") is None


# ---------- 嵌套事务: 子回滚不影响父 ----------
def test_nested_rollback_isolation(module_name):
    m = load_impl(module_name)
    c = m.Cache()
    c.set("x", 0, ttl=100)
    c.begin()            # A
    c.set("x", 1, ttl=100)
    c.begin()            # B
    c.set("x", 2, ttl=100)
    c.rollback()         # 回滚 B
    assert c.get("x") == 1, "子事务回滚后, 父事务的修改应保留 (期望1, 实际%s)" % c.get("x")
    c.commit()           # 提交 A
    assert c.get("x") == 1, "提交后应为父事务值1, 实际%s" % c.get("x")


# ---------- 嵌套事务: 子提交仅合并到父, 父回滚全丢 ----------
def test_nested_child_commit_then_parent_rollback(module_name):
    m = load_impl(module_name)
    c = m.Cache()
    c.set("y", 0, ttl=100)
    c.begin()            # A
    c.set("y", 1, ttl=100)
    c.begin()            # B
    c.set("y", 9, ttl=100)
    c.commit()           # 提交 B -> 合并到 A
    assert c.get("y") == 9
    c.rollback()         # 回滚 A -> 一切复原
    assert c.get("y") == 0, "父回滚后应为初始值0, 实际%s" % c.get("y")


# ---------- 并发读写一致性 (无丢失更新) ----------
def test_concurrent_increment(module_name):
    m = load_impl(module_name)
    c = m.Cache()
    c.set("cnt", 0, ttl=1000)
    c.begin()
    n = 50

    def worker():
        for _ in range(n):
            while True:
                cur = c.get("cnt")
                if c.compare_and_swap("cnt", cur, cur + 1, ttl=1000):
                    break

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    c.commit()
    assert c.get("cnt") == 8 * n, "并发自增应=%d, 实际%s" % (8 * n, c.get("cnt"))


# ---------- TTL: 惰性删除 ----------
def test_ttl_lazy_expiry(module_name):
    m = load_impl(module_name)
    c = m.Cache()
    c.set("k", "v", ttl=1)
    time.sleep(1.2)
    assert c.get("k") is None, "过期 key 应惰性返回 None"


# ---------- TTL 主动清理不误删事务内 key ----------
def test_active_cleanup_no_clobber_txn(module_name):
    m = load_impl(module_name)
    c = m.Cache()
    c.begin()
    c.set("live", 1, ttl=1)      # 1秒后过期
    time.sleep(1.2)
    # 主动清理线程不应在事务未提交时把 live 删掉(get 在事务内应仍可见)
    assert c.get("live") == 1, "事务内读取未提交 key, 即便 ttl 到期也应可见, 实际%s" % c.get("live")
    c.commit()


# ---------- 后台清理线程优雅退出 (无泄漏) ----------
def test_cleanup_thread_stops(module_name):
    m = load_impl(module_name)
    c = m.Cache(cleanup_interval=0.2)
    c.set("z", 1, ttl=10)
    time.sleep(0.5)
    c.shutdown()
    # shutdown 后线程应已结束
    assert not any(t.is_alive() for t in c._cleanup_threads()), "后台清理线程应已退出, 存在泄漏"
