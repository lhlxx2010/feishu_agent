"""
MCP Server 工具测试

测试策略:
- 返回 JSON 的工具: 解析 JSON 后验证结构化数据
- 返回纯文本的工具: 验证关键信息存在，而非精确匹配文案
"""

import json
import re
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestMCPTools:
    """MCP 工具函数测试"""

    @pytest.fixture
    def mock_provider(self):
        """Mock WorkItemProvider"""
        with patch("src.mcp_server.WorkItemProvider") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            yield mock_instance

    # =========================================================================
    # create_task 测试 (返回纯文本)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_create_task_success(self, mock_provider):
        """测试创建任务成功 - 验证返回包含 issue_id"""
        from src.mcp_server import create_task

        mock_provider.create_issue.return_value = 12345

        result = await create_task(
            project="proj_xxx",
            name="Test Task",
            priority="P0",
            description="Test description",
            assignee="张三",
        )

        # 验证返回的 issue_id（核心信息）
        assert "12345" in result
        # 验证 API 调用参数
        mock_provider.create_issue.assert_awaited_once_with(
            name="Test Task",
            priority="P0",
            description="Test description",
            assignee="张三",
        )

    @pytest.mark.asyncio
    async def test_create_task_error(self, mock_provider):
        """测试创建任务失败 - 验证错误信息被包含"""
        from src.mcp_server import create_task

        mock_provider.create_issue.side_effect = Exception("API Error")

        result = await create_task(
            project="proj_xxx",
            name="Test Task",
        )

        # 验证错误信息被传递（核心信息）
        assert "API Error" in result

    # =========================================================================
    # get_tasks 测试 (返回 JSON)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_tasks_success(self, mock_provider):
        """测试获取任务成功 - 验证 JSON 结构"""
        from src.mcp_server import get_tasks

        mock_provider.get_tasks.return_value = {
            "items": [
                {"id": 1, "name": "Task 1", "field_value_pairs": []},
                {"id": 2, "name": "Task 2", "field_value_pairs": []},
            ],
            "total": 2,
            "page_num": 1,
            "page_size": 50,
        }

        result = await get_tasks(project="proj_xxx", page_size=50)

        # 解析 JSON 并验证结构
        data = json.loads(result)
        assert isinstance(data, dict), "返回值应为 JSON 对象"
        assert "total" in data, "应包含 total 字段"
        assert "items" in data, "应包含 items 字段"
        assert data["total"] == 2
        assert len(data["items"]) == 2
        # 验证 items 结构
        for item in data["items"]:
            assert "id" in item
            assert "name" in item

        mock_provider.get_tasks.assert_awaited_once_with(
            name_keyword=None,
            status=None,
            priority=None,
            owner=None,
            related_to=None,
            page_num=1,
            page_size=50,
        )

    @pytest.mark.asyncio
    async def test_get_tasks_error(self, mock_provider):
        """测试获取任务失败 - 验证错误信息被包含"""
        from src.mcp_server import get_tasks

        mock_provider.get_tasks.side_effect = Exception("Network Error")

        result = await get_tasks(project="proj_xxx")

        # 验证错误信息被传递
        assert "Network Error" in result

    # =========================================================================
    # filter_tasks 测试 (返回 JSON)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_filter_tasks_success(self, mock_provider):
        """测试过滤任务成功 - 验证 JSON 结构和参数解析"""
        from src.mcp_server import filter_tasks

        mock_provider.filter_issues.return_value = {
            "items": [{"id": 1, "name": "P0 Task", "field_value_pairs": []}],
            "total": 1,
            "page_num": 1,
            "page_size": 20,
        }

        result = await filter_tasks(
            project="proj_xxx",
            status="进行中",
            priority="P0,P1",
            page_num=1,
            page_size=20,
        )

        # 解析 JSON 并验证结构
        data = json.loads(result)
        assert isinstance(data, dict)
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == 1

        # 验证参数解析（逗号分隔 -> 列表）
        mock_provider.filter_issues.assert_awaited_once()
        call_kwargs = mock_provider.filter_issues.call_args.kwargs
        assert call_kwargs["status"] == ["进行中"]
        assert call_kwargs["priority"] == ["P0", "P1"]

    @pytest.mark.asyncio
    async def test_filter_tasks_no_conditions(self, mock_provider):
        """测试无过滤条件 - 验证空结果 JSON"""
        from src.mcp_server import filter_tasks

        mock_provider.filter_issues.return_value = {
            "items": [],
            "total": 0,
            "page_num": 1,
            "page_size": 20,
        }

        result = await filter_tasks(project="proj_xxx")

        data = json.loads(result)
        assert data["total"] == 0
        assert data["items"] == []

        call_kwargs = mock_provider.filter_issues.call_args.kwargs
        assert call_kwargs["status"] is None
        assert call_kwargs["priority"] is None

    # =========================================================================
    # update_task 测试 (返回纯文本)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_update_task_success(self, mock_provider):
        """测试更新任务成功 - 验证返回包含 issue_id"""
        from src.mcp_server import update_task

        mock_provider.update_issue.return_value = None

        result = await update_task(
            project="proj_xxx",
            issue_id=12345,
            status="已完成",
            priority="P1",
        )

        # 验证返回的 issue_id（核心信息）
        assert "12345" in result
        mock_provider.update_issue.assert_awaited_once_with(
            issue_id=12345,
            name=None,
            priority="P1",
            description=None,
            status="已完成",
            assignee=None,
        )

    @pytest.mark.asyncio
    async def test_update_task_error(self, mock_provider):
        """测试更新任务失败 - 验证错误信息被包含"""
        from src.mcp_server import update_task

        mock_provider.update_issue.side_effect = Exception("Field not found")

        result = await update_task(
            project="proj_xxx",
            issue_id=12345,
            status="未知状态",
        )

        # 验证错误信息被传递
        assert "Field not found" in result

    # =========================================================================
    # get_task_options 测试 (返回 JSON)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_task_options_success(self, mock_provider):
        """测试获取字段选项成功 - 验证 JSON 结构"""
        from src.mcp_server import get_task_options

        mock_provider.list_available_options.return_value = {
            "待处理": "opt_pending",
            "进行中": "opt_in_progress",
            "已完成": "opt_done",
        }

        result = await get_task_options(project="proj_xxx", field_name="status")

        # 解析 JSON 并验证结构
        data = json.loads(result)
        assert isinstance(data, dict)
        assert "field" in data
        assert "options" in data
        assert data["field"] == "status"
        assert isinstance(data["options"], dict)
        assert "待处理" in data["options"]
        assert data["options"]["待处理"] == "opt_pending"

    @pytest.mark.asyncio
    async def test_get_task_options_error(self, mock_provider):
        """测试获取字段选项失败 - 验证错误信息被包含"""
        from src.mcp_server import get_task_options

        mock_provider.list_available_options.side_effect = Exception("Unknown field")

        result = await get_task_options(project="proj_xxx", field_name="unknown")

        # 验证错误信息被传递
        assert "Unknown field" in result


class TestHelperFunctions:
    """辅助函数测试"""

    def test_extract_field_value_simple(self):
        """测试提取简单字段值"""
        from src.mcp_server import _extract_field_value

        item = {
            "field_value_pairs": [
                {"field_key": "name", "field_value": "Task Name"},
                {"field_key": "priority", "field_value": "P0"},
            ]
        }

        assert _extract_field_value(item, "name") == "Task Name"
        assert _extract_field_value(item, "priority") == "P0"
        assert _extract_field_value(item, "nonexistent") is None

    def test_extract_field_value_dict(self):
        """测试提取字典类型字段值（选项类型）"""
        from src.mcp_server import _extract_field_value

        item = {
            "field_value_pairs": [
                {
                    "field_key": "status",
                    "field_value": {"label": "进行中", "value": "opt_in_progress"},
                }
            ]
        }

        assert _extract_field_value(item, "status") == "进行中"

    def test_extract_field_value_user_list(self):
        """测试提取用户列表类型字段值"""
        from src.mcp_server import _extract_field_value

        item = {
            "field_value_pairs": [
                {
                    "field_key": "owner",
                    "field_value": [{"name": "张三", "user_key": "user_xxx"}],
                }
            ]
        }

        assert _extract_field_value(item, "owner") == "张三"

    def test_simplify_work_item(self):
        """测试简化工作项"""
        from src.mcp_server import _simplify_work_item

        item = {
            "id": 12345,
            "name": "Test Task",
            "field_value_pairs": [
                {
                    "field_key": "status",
                    "field_value": {"label": "进行中"},
                },
                {
                    "field_key": "priority",
                    "field_value": {"label": "P0"},
                },
                {
                    "field_key": "owner",
                    "field_value": [{"name": "张三"}],
                },
            ],
        }

        simplified = _simplify_work_item(item)

        assert simplified["id"] == 12345
        assert simplified["name"] == "Test Task"
        assert simplified["status"] == "进行中"
        assert simplified["priority"] == "P0"
        assert simplified["owner"] == "张三"
