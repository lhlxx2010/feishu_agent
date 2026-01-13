import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.providers.project.work_item_provider import WorkItemProvider


@pytest.fixture
def mock_api():
    with patch("src.providers.project.work_item_provider.WorkItemAPI") as mock:
        yield mock.return_value


@pytest.fixture
def mock_metadata():
    with patch("src.providers.project.work_item_provider.MetadataManager") as mock_cls:
        mock_instance = AsyncMock()
        mock_cls.get_instance.return_value = mock_instance
        yield mock_instance


@pytest.mark.asyncio
async def test_create_issue(mock_api, mock_metadata):
    # Setup mocks
    mock_metadata.get_project_key.return_value = "proj_123"
    mock_metadata.get_type_key.return_value = "type_issue"
    mock_metadata.get_field_key.side_effect = lambda pk, tk, name: f"field_{name}"
    mock_metadata.get_option_value.return_value = "opt_high"
    mock_metadata.get_user_key.return_value = "user_456"

    mock_api.create = AsyncMock(return_value=1001)
    mock_api.update = AsyncMock()

    # Init provider
    provider = WorkItemProvider("My Project")

    # Execute
    issue_id = await provider.create_issue(
        name="Test Issue", priority="High", description="Desc", assignee="Alice"
    )

    # Verify
    assert issue_id == 1001

    # Check Metadata calls
    mock_metadata.get_project_key.assert_awaited_with("My Project")
    mock_metadata.get_type_key.assert_awaited_with("proj_123", "Issue管理")

    # Check Create call
    # Create should be called with minimal fields first
    mock_api.create.assert_awaited_once()
    args, _ = mock_api.create.call_args
    assert args[0] == "proj_123"
    assert args[1] == "type_issue"
    assert args[2] == "Test Issue"

    fields = args[3]
    # Expect description and owner in create fields
    assert any(
        f["field_key"] == "field_description" and f["field_value"] == "Desc"
        for f in fields
    )
    assert any(
        f["field_key"] == "owner" and f["field_value"] == "user_456" for f in fields
    )

    # Check Update call (for priority)
    mock_api.update.assert_awaited_once()
    args, _ = mock_api.update.call_args
    assert args[2] == 1001  # issue_id
    update_fields = args[3]
    assert update_fields[0]["field_key"] == "field_priority"
    assert update_fields[0]["field_value"] == "opt_high"


@pytest.mark.asyncio
async def test_get_issue_details(mock_api, mock_metadata):
    mock_metadata.get_project_key.return_value = "proj_123"
    mock_metadata.get_type_key.return_value = "type_issue"

    mock_api.query = AsyncMock(return_value=[{"id": 1001, "name": "Issue"}])

    provider = WorkItemProvider("My Project")
    details = await provider.get_issue_details(1001)

    assert details["id"] == 1001
    mock_api.query.assert_awaited_with("proj_123", "type_issue", [1001])


@pytest.mark.asyncio
async def test_delete_issue(mock_api, mock_metadata):
    mock_metadata.get_project_key.return_value = "proj_123"
    mock_metadata.get_type_key.return_value = "type_issue"
    mock_api.delete = AsyncMock()

    provider = WorkItemProvider("My Project")
    await provider.delete_issue(1001)

    mock_api.delete.assert_awaited_with("proj_123", "type_issue", 1001)


@pytest.mark.asyncio
async def test_update_issue(mock_api, mock_metadata):
    """测试更新 Issue"""
    # Setup mocks
    mock_metadata.get_project_key.return_value = "proj_123"
    mock_metadata.get_type_key.return_value = "type_issue"
    mock_metadata.get_field_key.side_effect = lambda pk, tk, name: f"field_{name}"
    mock_metadata.get_option_value.return_value = "opt_p0"
    mock_metadata.get_user_key.return_value = "user_789"

    mock_api.update = AsyncMock()

    provider = WorkItemProvider("My Project")

    # Execute: 更新多个字段
    await provider.update_issue(
        issue_id=1001,
        name="Updated Title",
        priority="P0",
        assignee="Bob",
    )

    # Verify
    mock_api.update.assert_awaited_once()
    args, _ = mock_api.update.call_args

    assert args[0] == "proj_123"  # project_key
    assert args[1] == "type_issue"  # type_key
    assert args[2] == 1001  # issue_id

    update_fields = args[3]
    # 应该包含 name, priority, owner 三个字段
    field_keys = [f["field_key"] for f in update_fields]
    assert "name" in field_keys
    assert "field_priority" in field_keys
    assert "owner" in field_keys


@pytest.mark.asyncio
async def test_update_issue_partial(mock_api, mock_metadata):
    """测试部分更新 Issue（只更新一个字段）"""
    mock_metadata.get_project_key.return_value = "proj_123"
    mock_metadata.get_type_key.return_value = "type_issue"
    mock_metadata.get_field_key.side_effect = lambda pk, tk, name: f"field_{name}"
    mock_metadata.get_option_value.return_value = "opt_done"

    mock_api.update = AsyncMock()

    provider = WorkItemProvider("My Project")

    # Execute: 只更新状态
    await provider.update_issue(issue_id=1001, status="已完成")

    # Verify
    mock_api.update.assert_awaited_once()
    args, _ = mock_api.update.call_args

    update_fields = args[3]
    assert len(update_fields) == 1
    assert update_fields[0]["field_key"] == "field_status"
    assert update_fields[0]["field_value"] == "opt_done"


@pytest.mark.asyncio
async def test_filter_issues(mock_api, mock_metadata):
    """测试过滤查询 Issues"""
    # Setup mocks
    mock_metadata.get_project_key.return_value = "proj_123"
    mock_metadata.get_type_key.return_value = "type_issue"
    mock_metadata.get_field_key.side_effect = lambda pk, tk, name: f"field_{name}"
    mock_metadata.get_option_value.side_effect = lambda pk, tk, fk, val: f"opt_{val}"
    mock_metadata.get_user_key.return_value = "user_alice"

    mock_api.search_params = AsyncMock(
        return_value={
            "work_items": [
                {"id": 1001, "name": "Issue 1"},
                {"id": 1002, "name": "Issue 2"},
            ],
            "pagination": {"total": 2, "page_num": 1, "page_size": 20},
        }
    )

    provider = WorkItemProvider("My Project")

    # Execute: 按状态和负责人过滤
    result = await provider.filter_issues(
        status=["进行中", "待处理"],
        owner="Alice",
        page_num=1,
        page_size=20,
    )

    # Verify result
    assert result["total"] == 2
    assert len(result["items"]) == 2
    assert result["items"][0]["id"] == 1001

    # Verify API call
    mock_api.search_params.assert_awaited_once()
    args, kwargs = mock_api.search_params.call_args

    assert kwargs["project_key"] == "proj_123"
    assert kwargs["work_item_type_key"] == "type_issue"
    assert kwargs["page_num"] == 1
    assert kwargs["page_size"] == 20

    # 检查 search_group 结构
    search_group = kwargs["search_group"]
    assert search_group["conjunction"] == "AND"
    assert len(search_group["conditions"]) == 2  # status + owner


@pytest.mark.asyncio
async def test_filter_issues_by_priority(mock_api, mock_metadata):
    """测试按优先级过滤"""
    mock_metadata.get_project_key.return_value = "proj_123"
    mock_metadata.get_type_key.return_value = "type_issue"
    mock_metadata.get_field_key.side_effect = lambda pk, tk, name: f"field_{name}"
    mock_metadata.get_option_value.side_effect = lambda pk, tk, fk, val: f"opt_{val}"

    mock_api.search_params = AsyncMock(
        return_value={
            "work_items": [{"id": 1001, "name": "P0 Issue"}],
            "pagination": {"total": 1, "page_num": 1, "page_size": 20},
        }
    )

    provider = WorkItemProvider("My Project")

    # Execute: 按优先级过滤
    result = await provider.filter_issues(priority=["P0", "P1"])

    # Verify
    assert result["total"] == 1

    # 检查 search_group 包含 priority 条件
    _, kwargs = mock_api.search_params.call_args
    search_group = kwargs["search_group"]
    conditions = search_group["conditions"]

    assert len(conditions) == 1
    assert conditions[0]["field_key"] == "field_priority"
    assert conditions[0]["operator"] == "IN"
    assert "opt_P0" in conditions[0]["value"]
    assert "opt_P1" in conditions[0]["value"]


@pytest.mark.asyncio
async def test_get_active_issues(mock_api, mock_metadata):
    """测试获取活跃 Issues"""
    mock_metadata.get_project_key.return_value = "proj_123"
    mock_metadata.get_type_key.return_value = "type_issue"
    mock_metadata.get_field_key.side_effect = lambda pk, tk, name: f"field_{name}"
    mock_metadata.get_option_value.side_effect = lambda pk, tk, fk, val: f"opt_{val}"

    mock_api.search_params = AsyncMock(
        return_value={
            "work_items": [
                {"id": 1001, "name": "Active Issue 1"},
                {"id": 1002, "name": "Active Issue 2"},
            ],
            "pagination": {"total": 2, "page_num": 1, "page_size": 50},
        }
    )

    provider = WorkItemProvider("My Project")

    # Execute
    items = await provider.get_active_issues(page_size=50)

    # Verify
    assert len(items) == 2
    assert items[0]["id"] == 1001

    # 检查调用了 search_params
    mock_api.search_params.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_available_options(mock_api, mock_metadata):
    """测试列出字段可用选项"""
    mock_metadata.get_project_key.return_value = "proj_123"
    mock_metadata.get_type_key.return_value = "type_issue"
    mock_metadata.get_field_key.return_value = "field_status"
    mock_metadata.list_options.return_value = {
        "待处理": "opt_pending",
        "进行中": "opt_in_progress",
        "已完成": "opt_done",
    }

    provider = WorkItemProvider("My Project")

    # Execute
    options = await provider.list_available_options("status")

    # Verify
    assert "待处理" in options
    assert options["待处理"] == "opt_pending"
    mock_metadata.list_options.assert_awaited_with(
        "proj_123", "type_issue", "field_status"
    )


@pytest.mark.asyncio
async def test_filter_issues_empty_conditions(mock_api, mock_metadata):
    """测试无过滤条件时的查询"""
    mock_metadata.get_project_key.return_value = "proj_123"
    mock_metadata.get_type_key.return_value = "type_issue"

    mock_api.search_params = AsyncMock(
        return_value={
            "work_items": [],
            "pagination": {"total": 0, "page_num": 1, "page_size": 20},
        }
    )

    provider = WorkItemProvider("My Project")

    # Execute: 无任何过滤条件
    result = await provider.filter_issues()

    # Verify
    assert result["total"] == 0
    assert result["items"] == []

    # 检查 search_group 为空条件
    _, kwargs = mock_api.search_params.call_args
    search_group = kwargs["search_group"]
    assert search_group["conditions"] == []
