"""
SimpleCache 单元测试
"""

import time
import pytest
from src.core.cache import SimpleCache


class TestSimpleCache:
    """SimpleCache 测试类"""

    def test_set_and_get(self):
        """测试基本的存取功能"""
        cache = SimpleCache(ttl=3600)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        """测试获取不存在的 key"""
        cache = SimpleCache(ttl=3600)
        assert cache.get("nonexistent") is None

    def test_cache_expiry(self):
        """测试缓存过期"""
        cache = SimpleCache(ttl=1)  # 1秒过期
        cache.set("key1", "value1")

        # 立即获取应该能获取到
        assert cache.get("key1") == "value1"

        # 等待过期
        time.sleep(1.1)

        # 过期后应该返回 None
        assert cache.get("key1") is None

    def test_cache_overwrite(self):
        """测试覆盖已有值"""
        cache = SimpleCache(ttl=3600)
        cache.set("key1", "value1")
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"

    def test_clear(self):
        """测试清空缓存"""
        cache = SimpleCache(ttl=3600)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_different_value_types(self):
        """测试不同类型的值"""
        cache = SimpleCache(ttl=3600)

        # 字符串
        cache.set("str", "hello")
        assert cache.get("str") == "hello"

        # 数字
        cache.set("int", 123)
        assert cache.get("int") == 123

        # 列表
        cache.set("list", [1, 2, 3])
        assert cache.get("list") == [1, 2, 3]

        # 字典
        cache.set("dict", {"a": 1})
        assert cache.get("dict") == {"a": 1}

        # None
        cache.set("none", None)
        assert cache.get("none") is None

    def test_default_ttl(self):
        """测试默认 TTL"""
        cache = SimpleCache()  # 默认 3600 秒
        assert cache.ttl == 3600
