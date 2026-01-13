"""
MCP Server - 飞书 Agent 工具接口

提供给 LLM 调用的工具集，用于操作飞书项目中的工作项。

工具列表:
- list_projects: 列出所有可用项目
- create_task: 创建工作项
- get_tasks: 获取工作项列表（支持全量或过滤）
- filter_tasks: 高级过滤查询
- update_task: 更新工作项
- get_task_options: 获取字段可用选项

重要说明:
- 所有工具都支持 project_name（项目名称）参数，会自动转换为 project_key
- 如果用户提供的是项目名称（如 "SR6D2VA-7552-Lark"），系统会自动查找对应的 project_key
"""

import json
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

from src.providers.project.work_item_provider import WorkItemProvider
from src.providers.project.managers import MetadataManager

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("Lark")


def _extract_field_value(item: dict, field_key: str) -> Optional[str]:
    """从工作项中提取字段值"""
    field_pairs = item.get("field_value_pairs", [])
    for pair in field_pairs:
        if pair.get("field_key") == field_key:
            value = pair.get("field_value")
            # 处理选项类型字段
            if isinstance(value, dict):
                return value.get("label") or value.get("value")
            # 处理用户类型字段
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, dict):
                    return first.get("name") or first.get("name_cn")
            return str(value) if value else None
    return None


def _simplify_work_item(item: dict) -> dict:
    """将工作项简化为摘要格式，减少 Token 消耗"""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "status": _extract_field_value(item, "status"),
        "priority": _extract_field_value(item, "priority"),
        "owner": _extract_field_value(item, "owner"),
    }


def _looks_like_project_key(identifier: str) -> bool:
    """
    判断标识符是否像 project_key 格式

    project_key 通常是:
    - 以 "project_" 开头
    - 纯字母数字下划线组合
    - 不包含中文或空格
    """
    if not identifier:
        return False

    # 明确的 project_key 前缀
    if identifier.startswith("project_"):
        return True

    # 包含中文或空格，肯定是名称
    if any("\u4e00" <= c <= "\u9fff" for c in identifier):
        return False
    if " " in identifier or "-" in identifier:
        return False

    return False


def _create_provider(project: str) -> WorkItemProvider:
    """
    根据 project 参数创建 Provider

    自动判断传入的是 project_key 还是 project_name，并相应处理。

    Args:
        project: 项目标识符（可以是 project_key 或 project_name）

    Returns:
        WorkItemProvider 实例
    """
    if _looks_like_project_key(project):
        return WorkItemProvider(project_key=project)
    else:
        # 当作项目名称处理
        return WorkItemProvider(project_name=project)


@mcp.tool()
async def list_projects() -> str:
    """
    列出所有可用的飞书项目空间。

    当你不知道项目的 project_key 时，先调用此工具获取项目列表。
    返回的列表包含项目名称和对应的 project_key。

    Returns:
        JSON 格式的项目列表，格式为 {project_name: project_key}。
        失败时返回错误信息。

    Examples:
        # 查看有哪些项目可用
        list_projects()
    """
    try:
        meta = MetadataManager.get_instance()
        projects = await meta.list_projects()

        return json.dumps(
            {
                "count": len(projects),
                "projects": projects,
                "hint": "使用项目名称或 project_key 都可以调用其他工具",
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.exception(f"Failed to list projects: {e}")
        return f"获取项目列表失败: {str(e)}"


@mcp.tool()
async def create_task(
    project: str,
    name: str,
    priority: str = "P2",
    description: str = "",
    assignee: Optional[str] = None,
) -> str:
    """
    在指定项目中创建新的工作项（任务/Issue）。

    这是创建飞书项目工作项的主要工具。系统会自动处理字段值的转换
    （如将 "P0" 转换为对应的选项 Key）。

    Args:
        project: 项目标识符。可以是:
                - 项目名称（如 "SR6D2VA-7552-Lark"）
                - project_key（如 "project_xxx"）
                系统会自动识别并处理。
        name: 工作项标题，必填。
        priority: 优先级，可选值: P0(最高), P1, P2(默认), P3(最低)。
        description: 工作项描述，支持纯文本。
        assignee: 负责人的姓名或邮箱。如不指定则为空。

    Returns:
        成功时返回 "创建成功，Issue ID: xxx"。
        失败时返回错误信息。

    Examples:
        # 使用项目名称创建任务
        create_task(
            project="SR6D2VA-7552-Lark",
            name="修复登录页面崩溃问题",
            priority="P0"
        )

        # 使用 project_key 创建任务
        create_task(
            project="project_xxx",
            name="修复登录页面崩溃问题",
            priority="P0",
            assignee="张三"
        )
    """
    try:
        provider = _create_provider(project)
        issue_id = await provider.create_issue(
            name=name,
            priority=priority,
            description=description,
            assignee=assignee,
        )
        return f"创建成功，Issue ID: {issue_id}"
    except Exception as e:
        logger.exception(f"Failed to create task: {e}")
        return f"创建失败: {str(e)}"


@mcp.tool()
async def get_tasks(
    project: str,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    owner: Optional[str] = None,
    page_num: int = 1,
    page_size: int = 50,
) -> str:
    """
    获取项目中的工作项列表（支持全量获取或按条件过滤）。

    这是通用的任务获取工具，具备以下特性：
    1. 无过滤参数时，返回项目的全部工作项
    2. 支持按状态、优先级、负责人进行灵活过滤
    3. 如果项目不存在某个字段（如状态），会自动跳过该过滤条件

    Args:
        project: 项目标识符。可以是:
                - 项目名称（如 "Project Management"）
                - project_key（如 "project_xxx"）
        status: 状态过滤（多个用逗号分隔），如 "待处理,进行中"（可选）。
        priority: 优先级过滤（多个用逗号分隔），如 "P0,P1"（可选）。
        owner: 负责人过滤（姓名或邮箱）（可选）。
        page_num: 页码，从 1 开始（默认 1）。
        page_size: 每页数量（默认 50，最大 100）。

    Returns:
        JSON 格式的工作项列表，包含 id, name, status, priority, owner。
        失败时返回错误信息。

    Examples:
        # 获取项目的全部工作项
        get_tasks(project="Project Management")

        # 获取指定优先级的任务
        get_tasks(project="Project Management", priority="P0,P1")

        # 组合多个条件过滤
        get_tasks(
            project="Project Management",
            status="进行中",
            priority="P0",
            owner="张三"
        )
    """
    try:
        provider = _create_provider(project)

        # 解析逗号分隔的过滤条件
        status_list = [s.strip() for s in status.split(",")] if status else None
        priority_list = [p.strip() for p in priority.split(",")] if priority else None

        result = await provider.get_tasks(
            status=status_list,
            priority=priority_list,
            owner=owner,
            page_num=page_num,
            page_size=min(page_size, 100),
        )

        # 确保 result 是字典类型
        if not isinstance(result, dict):
            logger.error(f"Unexpected result type: {type(result)}, value: {result}")
            return f"获取任务列表失败: 返回数据格式错误"

        # 简化返回结果
        simplified = [_simplify_work_item(item) for item in result.get("items", [])]

        return json.dumps(
            {
                "total": result.get("total", 0),
                "page_num": result.get("page_num", page_num),
                "page_size": result.get("page_size", page_size),
                "items": simplified,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.exception(f"Failed to get tasks: {e}")
        return f"获取任务列表失败: {str(e)}"


@mcp.tool()
async def filter_tasks(
    project: str,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    owner: Optional[str] = None,
    page_num: int = 1,
    page_size: int = 20,
) -> str:
    """
    高级过滤查询工作项。

    支持按状态、优先级、负责人进行组合过滤。
    字段值会自动转换为 API 所需的格式。

    Args:
        project: 项目标识符。可以是项目名称或 project_key。
        status: 状态过滤（多个用逗号分隔），如 "待处理,进行中"。
        priority: 优先级过滤（多个用逗号分隔），如 "P0,P1"。
        owner: 负责人过滤（姓名或邮箱）。
        page_num: 页码，从 1 开始。
        page_size: 每页数量，默认 20，最大 100。

    Returns:
        JSON 格式的过滤结果，包含:
        - total: 符合条件的总数
        - items: 工作项列表（简化格式）
        失败时返回错误信息。

    Examples:
        # 查找所有 P0 优先级的待处理任务
        filter_tasks(
            project="SR6D2VA-7552-Lark",
            status="待处理",
            priority="P0"
        )

        # 查找张三负责的所有进行中任务
        filter_tasks(
            project="SR6D2VA-7552-Lark",
            status="进行中",
            owner="张三"
        )
    """
    try:
        provider = _create_provider(project)

        # 解析逗号分隔的过滤条件
        status_list = [s.strip() for s in status.split(",")] if status else None
        priority_list = [p.strip() for p in priority.split(",")] if priority else None

        result = await provider.filter_issues(
            status=status_list,
            priority=priority_list,
            owner=owner,
            page_num=page_num,
            page_size=min(page_size, 100),
        )

        # 简化返回结果
        simplified_items = [
            _simplify_work_item(item) for item in result.get("items", [])
        ]

        return json.dumps(
            {
                "total": result.get("total", 0),
                "page_num": result.get("page_num", page_num),
                "page_size": result.get("page_size", page_size),
                "items": simplified_items,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.exception(f"Failed to filter tasks: {e}")
        return f"过滤失败: {str(e)}"


@mcp.tool()
async def update_task(
    project: str,
    issue_id: int,
    name: Optional[str] = None,
    priority: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
) -> str:
    """
    更新工作项的字段。

    可以同时更新多个字段，只需提供要更新的字段值即可。
    未提供的字段将保持不变。

    Args:
        project: 项目标识符。可以是项目名称或 project_key。
        issue_id: 要更新的工作项 ID。
        name: 新标题（可选）。
        priority: 新优先级（可选），如 "P0", "P1" 等。
        description: 新描述（可选）。
        status: 新状态（可选），如 "进行中", "已完成" 等。
        assignee: 新负责人（可选），姓名或邮箱。

    Returns:
        成功时返回 "更新成功"。
        失败时返回错误信息。

    Examples:
        # 将任务标记为进行中
        update_task(
            project="SR6D2VA-7552-Lark",
            issue_id=12345,
            status="进行中"
        )

        # 提升任务优先级并更换负责人
        update_task(
            project="SR6D2VA-7552-Lark",
            issue_id=12345,
            priority="P0",
            assignee="李四"
        )
    """
    try:
        provider = _create_provider(project)
        await provider.update_issue(
            issue_id=issue_id,
            name=name,
            priority=priority,
            description=description,
            status=status,
            assignee=assignee,
        )
        return f"更新成功，Issue ID: {issue_id}"
    except Exception as e:
        logger.exception(f"Failed to update task: {e}")
        return f"更新失败: {str(e)}"


@mcp.tool()
async def get_task_options(project: str, field_name: str) -> str:
    """
    获取字段的可用选项列表。

    当你不确定某个字段有哪些可选值时，使用此工具查询。
    这对于了解状态流转、优先级选项等非常有用。

    Args:
        project: 项目标识符。可以是项目名称或 project_key。
        field_name: 字段名称，如 "status", "priority"。

    Returns:
        JSON 格式的选项列表，格式为 {label: value}。
        失败时返回错误信息。

    Examples:
        # 查看状态字段有哪些可选值
        get_task_options(project="SR6D2VA-7552-Lark", field_name="status")

        # 查看优先级字段有哪些可选值
        get_task_options(project="SR6D2VA-7552-Lark", field_name="priority")
    """
    try:
        provider = _create_provider(project)
        options = await provider.list_available_options(field_name)

        return json.dumps(
            {"field": field_name, "options": options},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.exception(f"Failed to get options: {e}")
        return f"获取选项失败: {str(e)}"
