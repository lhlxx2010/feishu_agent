from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable
import pytest
import asyncio
import sys


# =============================================================================
# Pytest Markers Registration
# =============================================================================
def pytest_configure(config):
    """注册自定义标记以避免警告。"""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test (requires real Feishu API)",
    )


# =============================================================================
# Snapshot Fixtures (Track 1 - Snapshot-based Unit Testing)
# =============================================================================
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "snapshots"


@pytest.fixture
def load_snapshot() -> Callable[[str], dict[str, Any]]:
    """
    从 tests/fixtures/snapshots/ 加载 JSON 快照文件。

    用法:
        def test_example(load_snapshot):
            data = load_snapshot("work_item_list.json")
    """

    def _load(filename: str) -> dict[str, Any]:
        filepath = FIXTURES_DIR / filename
        if not filepath.exists():
            raise FileNotFoundError(f"快照文件不存在: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    return _load


@pytest.fixture
def save_snapshot() -> Callable[[str, dict[str, Any]], None]:
    """
    将 API 响应保存为 JSON 快照供 Track 1 测试使用。
    由集成测试使用以捕获真实响应。

    用法:
        def test_example(save_snapshot):
            response = await api.get_items()
            save_snapshot("work_item_list.json", response)
    """

    def _save(filename: str, data: dict[str, Any]) -> None:
        FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
        filepath = FIXTURES_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return _save


# =============================================================================
# Logging Configuration
# =============================================================================
# 配置测试日志
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)
logger.info("测试日志配置完成: level=DEBUG")


@pytest.fixture(autouse=True)
def log_test_start(request):
    """为每个测试记录开始和结束日志。"""
    logger.info("=" * 80)
    logger.info("开始测试: %s", request.node.name)
    yield
    logger.info("完成测试: %s", request.node.name)
    logger.info("=" * 80)
