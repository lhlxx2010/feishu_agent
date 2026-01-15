"""
Integration Test Configuration
集成测试配置 - Track 2: Live Integration Testing

测试环境:
- 项目: 从环境变量 FEISHU_TEST_PROJECT_KEY 或 FEISHU_PROJECT_KEY 读取
- 工作项类型: 问题管理

必须配置的环境变量:
- FEISHU_TEST_PROJECT_KEY 或 FEISHU_PROJECT_KEY
- FEISHU_PROJECT_PLUGIN_ID + FEISHU_PROJECT_PLUGIN_SECRET + FEISHU_PROJECT_USER_KEY
  或 FEISHU_PROJECT_USER_TOKEN + FEISHU_PROJECT_USER_KEY
"""

import pytest

from src.core.config import settings

# =============================================================================
# Integration Test Constants
# =============================================================================
# 优先使用测试专用的 FEISHU_TEST_PROJECT_KEY，否则回退到 FEISHU_PROJECT_KEY
TEST_PROJECT_KEY = settings.FEISHU_TEST_PROJECT_KEY or settings.FEISHU_PROJECT_KEY
TEST_WORK_ITEM_TYPE = "问题管理"


# =============================================================================
# Skip Condition: Check if credentials are available
# =============================================================================
def _has_credentials() -> bool:
    """Check if Feishu credentials are configured (supports both auth methods)."""
    # Must have project key
    if not TEST_PROJECT_KEY:
        return False

    # Method 1: User Token + User Key
    has_user_auth = bool(
        settings.FEISHU_PROJECT_USER_TOKEN and settings.FEISHU_PROJECT_USER_KEY
    )
    # Method 2: Plugin ID + Plugin Secret
    has_plugin_auth = bool(
        settings.FEISHU_PROJECT_PLUGIN_ID
        and settings.FEISHU_PROJECT_PLUGIN_SECRET
        and settings.FEISHU_PROJECT_USER_KEY  # User Key is still needed
    )
    return has_user_auth or has_plugin_auth


skip_without_credentials = pytest.mark.skipif(
    not _has_credentials(),
    reason="Feishu credentials not configured (need PROJECT_KEY + auth credentials)",
)


# =============================================================================
# Fixtures
# =============================================================================
@pytest.fixture(autouse=True, scope="function")
def reset_singletons():
    """
    在每个测试后重置单例实例以避免事件循环问题。

    清理逻辑:
    1. 测试前：强制重置单例引用，确保每个测试使用新的实例
    2. 测试后：不关闭client，只重置单例引用，让下一个测试创建新的client
    3. 异常时记录警告日志，而非静默忽略

    注意：不在teardown时关闭client，避免影响后续测试
    """
    import src.core.project_client as pc_module
    from src.providers.project.managers.metadata_manager import MetadataManager

    # 测试前：强制重置单例引用，确保每个测试使用新的实例
    # 如果存在旧的client且已关闭，先清理它
    old_client = pc_module._project_client
    if old_client is not None:
        try:
            # 检查client是否已关闭
            if hasattr(old_client, "client") and old_client.client.is_closed:
                # client已关闭，直接重置引用
                pc_module._project_client = None
                old_client = None
        except Exception:
            # 如果检查失败，也重置引用
            pc_module._project_client = None
            old_client = None
    else:
        pc_module._project_client = None

    # 同时重置 MetadataManager 单例
    MetadataManager._instance = None

    yield

    # 测试后：只重置单例引用，不关闭client
    # 这样可以避免影响后续测试，让每个测试都创建新的client
    pc_module._project_client = None
    MetadataManager._instance = None


@pytest.fixture
def test_project_key():
    """Return the test project key (from env)."""
    return TEST_PROJECT_KEY


@pytest.fixture
def test_work_item_type():
    """Return the test work item type."""
    return TEST_WORK_ITEM_TYPE
