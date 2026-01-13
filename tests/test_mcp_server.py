"""
MCP Server 工具测试
"""

import json
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

    @pytest.mark.asyncio
    async def test_create_task_success(self, mock_provider):
        """测试创建任务成功"""
        from src.mcp_server import create_task

        mock_provider.create_issue.return_value = 12345

        result = await create_task(
            project="proj_xxx",
            name="Test Task",
            priority="P0",
            description="Test description",
            assignee="张三",
        )

        assert "创建成功" in result
        assert "12345" in result
        mock_provider.create_issue.assert_awaited_once_with(
            name="Test Task",
            priority="P0",
            description="Test description",
            assignee="张三",
        )

    @pytest.mark.asyncio
    async def test_create_task_error(self, mock_provider):
        """测试创建任务失败"""
        from src.mcp_server import create_task

        mock_provider.create_issue.side_effect = Exception("API Error")

        result = await create_task(
            project="proj_xxx",
            name="Test Task",
        )

        assert "创建失败" in result
        assert "API Error" in result

    @pytest.mark.asyncio
    async def test_get_tasks_success(self, mock_provider):
        """测试获取任务成功"""
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

        data = json.loads(result)
        assert data["total"] == 2
        assert len(data["items"]) == 2
        mock_provider.get_tasks.assert_awaited_once_with(
            status=None, priority=None, owner=None, page_num=1, page_size=50
        )

    @pytest.mark.asyncio
    async def test_get_tasks_error(self, mock_provider):
        """测试获取任务失败"""
        from src.mcp_server import get_tasks

        mock_provider.get_tasks.side_effect = Exception("Network Error")

        result = await get_tasks(project="proj_xxx")

        assert "获取任务列表失败" in result
        assert "Network Error" in result

    @pytest.mark.asyncio
    async def test_filter_tasks_success(self, mock_provider):
        """测试过滤任务成功"""
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

        data = json.loads(result)
        assert data["total"] == 1
        assert len(data["items"]) == 1

        # 验证参数解析
        mock_provider.filter_issues.assert_awaited_once()
        call_kwargs = mock_provider.filter_issues.call_args.kwargs
        assert call_kwargs["status"] == ["进行中"]
        assert call_kwargs["priority"] == ["P0", "P1"]

    @pytest.mark.asyncio
    async def test_filter_tasks_no_conditions(self, mock_provider):
        """测试无过滤条件"""
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

        call_kwargs = mock_provider.filter_issues.call_args.kwargs
        assert call_kwargs["status"] is None
        assert call_kwargs["priority"] is None

    @pytest.mark.asyncio
    async def test_update_task_success(self, mock_provider):
        """测试更新任务成功"""
        from src.mcp_server import update_task

        mock_provider.update_issue.return_value = None

        result = await update_task(
            project="proj_xxx",
            issue_id=12345,
            status="已完成",
            priority="P1",
        )

        assert "更新成功" in result
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
        """测试更新任务失败"""
        from src.mcp_server import update_task

        mock_provider.update_issue.side_effect = Exception("Field not found")

        result = await update_task(
            project="proj_xxx",
            issue_id=12345,
            status="未知状态",
        )

        assert "更新失败" in result
        assert "Field not found" in result

    @pytest.mark.asyncio
    async def test_get_task_options_success(self, mock_provider):
        """测试获取字段选项成功"""
        from src.mcp_server import get_task_options

        mock_provider.list_available_options.return_value = {
            "待处理": "opt_pending",
            "进行中": "opt_in_progress",
            "已完成": "opt_done",
        }

        result = await get_task_options(project="proj_xxx", field_name="status")

        data = json.loads(result)
        assert data["field"] == "status"
        assert "待处理" in data["options"]
        assert data["options"]["待处理"] == "opt_pending"

    @pytest.mark.asyncio
    async def test_get_task_options_error(self, mock_provider):
        """测试获取字段选项失败"""
        from src.mcp_server import get_task_options

        mock_provider.list_available_options.side_effect = Exception("Unknown field")

        result = await get_task_options(project="proj_xxx", field_name="unknown")

        assert "获取选项失败" in result
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
