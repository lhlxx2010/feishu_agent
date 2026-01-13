import logging
from typing import Any, Dict, List, Optional

from src.providers.base import Provider
from src.providers.project.api.work_item import WorkItemAPI
from src.providers.project.managers import MetadataManager

logger = logging.getLogger(__name__)


class WorkItemProvider(Provider):
    """
    工作项业务逻辑提供者 (Service/Provider Layer)
    串联 MetadataManager 和 WorkItemAPI，提供人性化的接口

    设计说明:
    - 使用 MetadataManager 实现零硬编码: 所有 Key/Value 通过名称动态解析
    - 使用 WorkItemAPI 执行原子操作
    """

    def __init__(
        self,
        project_name: Optional[str] = None,
        project_key: Optional[str] = None,
        work_item_type_name: str = "Issue管理",
    ):
        if not project_name and not project_key:
            raise ValueError("Must provide either project_name or project_key")

        self.project_name = project_name
        self._project_key = project_key
        self.work_item_type_name = work_item_type_name
        self.api = WorkItemAPI()
        self.meta = MetadataManager.get_instance()

    async def _get_project_key(self) -> str:
        if not self._project_key:
            if self.project_name:
                self._project_key = await self.meta.get_project_key(self.project_name)
            else:
                raise ValueError("Project key not resolved")
        return self._project_key

    async def _get_type_key(self) -> str:
        """获取工作项类型 Key"""
        project_key = await self._get_project_key()
        return await self.meta.get_type_key(project_key, self.work_item_type_name)

    async def _field_exists(
        self, project_key: str, type_key: str, field_name: str
    ) -> bool:
        """
        检查字段是否存在（不抛异常）

        Args:
            project_key: 项目空间 Key
            type_key: 工作项类型 Key
            field_name: 字段名称

        Returns:
            True: 字段存在
            False: 字段不存在
        """
        try:
            await self.meta.get_field_key(project_key, type_key, field_name)
            return True
        except Exception as e:
            logger.debug(f"Field '{field_name}' not found: {e}")
            return False

    async def _resolve_field_value(
        self, project_key: str, type_key: str, field_key: str, value: Any
    ) -> Any:
        """解析字段值：如果是 Select 类型且值为 Label，转换为 Option Value"""
        try:
            val = await self.meta.get_option_value(
                project_key, type_key, field_key, str(value)
            )
            logger.info(f"Resolved option '{value}' -> '{val}' for field '{field_key}'")
            return val
        except Exception as e:
            logger.warning(
                f"Failed to resolve option '{value}' for field '{field_key}': {e}"
            )
            return value  # Fallback

    async def create_issue(
        self,
        name: str,
        priority: str = "P2",
        description: str = "",
        assignee: Optional[str] = None,
    ) -> int:
        """
        创建 Issue

        Args:
            name: Issue 标题
            priority: 优先级 (P0/P1/P2/P3)
            description: 描述
            assignee: 负责人（姓名或邮箱）

        Returns:
            创建的 Issue ID
        """
        project_key = await self._get_project_key()
        type_key = await self._get_type_key()

        logger.info(f"Creating Issue in Project: {project_key}, Type: {type_key}")

        # 1. Prepare fields for creation (minimal set)
        create_fields = []

        # Description
        if description:
            field_key = await self.meta.get_field_key(
                project_key, type_key, "description"
            )
            create_fields.append({"field_key": field_key, "field_value": description})

        # Assignee
        if assignee:
            field_key = "owner"
            user_key = await self.meta.get_user_key(assignee)
            create_fields.append({"field_key": field_key, "field_value": user_key})

        # 2. Create Work Item
        issue_id = await self.api.create(project_key, type_key, name, create_fields)

        # 3. Update Priority (if needed)
        # Note: Priority cannot be set during creation for some reason, so we update it after.
        if priority:
            try:
                field_key = await self.meta.get_field_key(
                    project_key, type_key, "priority"
                )
                option_val = await self._resolve_field_value(
                    project_key, type_key, field_key, priority
                )

                logger.info(f"Updating priority to {option_val}...")
                await self.api.update(
                    project_key,
                    type_key,
                    issue_id,
                    [{"field_key": field_key, "field_value": option_val}],
                )
            except Exception as e:
                logger.warning(f"Failed to update priority: {e}")

        return issue_id

    async def get_issue_details(self, issue_id: int) -> Dict:
        """获取 Issue 详情"""
        project_key = await self._get_project_key()
        type_key = await self._get_type_key()

        items = await self.api.query(project_key, type_key, [issue_id])
        if not items:
            raise Exception(f"Issue {issue_id} not found")
        return items[0]

    async def update_issue(
        self,
        issue_id: int,
        name: Optional[str] = None,
        priority: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
    ) -> None:
        """
        更新 Issue

        Args:
            issue_id: Issue ID
            name: 标题（可选）
            priority: 优先级（可选）
            description: 描述（可选）
            status: 状态（可选）
            assignee: 负责人（可选）
        """
        project_key = await self._get_project_key()
        type_key = await self._get_type_key()

        update_fields = []

        if name is not None:
            update_fields.append({"field_key": "name", "field_value": name})

        if description is not None:
            field_key = await self.meta.get_field_key(
                project_key, type_key, "description"
            )
            update_fields.append({"field_key": field_key, "field_value": description})

        if priority is not None:
            field_key = await self.meta.get_field_key(project_key, type_key, "priority")
            option_val = await self._resolve_field_value(
                project_key, type_key, field_key, priority
            )
            update_fields.append({"field_key": field_key, "field_value": option_val})

        if status is not None:
            field_key = await self.meta.get_field_key(project_key, type_key, "status")
            option_val = await self._resolve_field_value(
                project_key, type_key, field_key, status
            )
            update_fields.append({"field_key": field_key, "field_value": option_val})

        if assignee is not None:
            user_key = await self.meta.get_user_key(assignee)
            update_fields.append({"field_key": "owner", "field_value": user_key})

        if update_fields:
            await self.api.update(project_key, type_key, issue_id, update_fields)
            logger.info(f"Updated Issue {issue_id} with {len(update_fields)} fields")

    async def delete_issue(self, issue_id: int) -> None:
        """删除 Issue"""
        project_key = await self._get_project_key()
        type_key = await self._get_type_key()
        await self.api.delete(project_key, type_key, issue_id)

    async def filter_issues(
        self,
        status: Optional[List[str]] = None,
        priority: Optional[List[str]] = None,
        owner: Optional[str] = None,
        page_num: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        过滤查询 Issues

        支持按状态、优先级、负责人进行过滤，自动将人类可读的值转换为 API 所需的 Key。

        Args:
            status: 状态列表（如 ["待处理", "进行中"]）
            priority: 优先级列表（如 ["P0", "P1"]）
            owner: 负责人（姓名或邮箱）
            page_num: 页码（从 1 开始）
            page_size: 每页数量

        Returns:
            {
                "items": [...],  # 工作项列表
                "total": 100,    # 总数
                "page_num": 1,
                "page_size": 20
            }

        示例:
            # 获取所有 P0 优先级的进行中任务
            result = await provider.filter_issues(
                status=["进行中"],
                priority=["P0"]
            )
        """
        project_key = await self._get_project_key()
        type_key = await self._get_type_key()

        # 构建搜索条件
        conditions = []

        # 处理状态过滤
        if status:
            if await self._field_exists(project_key, type_key, "status"):
                field_key = await self.meta.get_field_key(
                    project_key, type_key, "status"
                )
                resolved_values = []
                for s in status:
                    try:
                        val = await self._resolve_field_value(
                            project_key, type_key, field_key, s
                        )
                        resolved_values.append(val)
                    except Exception as e:
                        logger.warning(f"Failed to resolve status '{s}': {e}")
                        resolved_values.append(s)

                conditions.append(
                    {
                        "field_key": field_key,
                        "operator": "IN",
                        "value": resolved_values,
                    }
                )
            else:
                logger.warning(f"Field 'status' not found, skipping filter")

        # 处理优先级过滤
        if priority:
            if await self._field_exists(project_key, type_key, "priority"):
                field_key = await self.meta.get_field_key(
                    project_key, type_key, "priority"
                )
                resolved_values = []
                for p in priority:
                    try:
                        val = await self._resolve_field_value(
                            project_key, type_key, field_key, p
                        )
                        resolved_values.append(val)
                    except Exception as e:
                        logger.warning(f"Failed to resolve priority '{p}': {e}")
                        resolved_values.append(p)

                conditions.append(
                    {
                        "field_key": field_key,
                        "operator": "IN",
                        "value": resolved_values,
                    }
                )
            else:
                logger.warning(f"Field 'priority' not found, skipping filter")

        # 处理负责人过滤
        if owner:
            try:
                user_key = await self.meta.get_user_key(owner)
                conditions.append(
                    {
                        "field_key": "owner",
                        "operator": "IN",
                        "value": [user_key],
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to resolve owner '{owner}': {e}, skipping owner filter")

        # 构建 search_group
        search_group = {"conjunction": "AND", "conditions": conditions}

        logger.info(f"Filtering issues with conditions: {conditions}")

        # 调用 API
        result = await self.api.search_params(
            project_key=project_key,
            work_item_type_key=type_key,
            search_group=search_group,
            page_num=page_num,
            page_size=page_size,
        )

        # 标准化返回结果
        # 处理 API 可能返回列表或字典的情况
        if isinstance(result, list):
            items = result
            pagination = {"total": len(result), "page_num": page_num, "page_size": page_size}
            logger.debug("API returned list format, converted to standard format")
        else:
            items = result.get("work_items", [])
            pagination = result.get("pagination", {})

        return {
            "items": items,
            "total": pagination.get("total", len(items)),
            "page_num": pagination.get("page_num", page_num),
            "page_size": pagination.get("page_size", page_size),
        }

    async def get_tasks(
        self,
        status: Optional[List[str]] = None,
        priority: Optional[List[str]] = None,
        owner: Optional[str] = None,
        page_num: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        获取工作项列表（支持全量或按条件过滤）

        设计理念:
        - 无参数时返回全部工作项
        - 字段不存在时自动跳过该过滤条件
        - 支持多维度组合过滤

        Args:
            status: 状态列表（可选，如 ["待处理", "进行中"]）
            priority: 优先级列表（可选，如 ["P0", "P1"]）
            owner: 负责人（可选，姓名或邮箱）
            page_num: 页码（从 1 开始）
            page_size: 每页数量

        Returns:
            {
                "items": [...],
                "total": 100,
                "page_num": 1,
                "page_size": 50
            }

        示例:
            # 获取全部工作项
            result = await provider.get_tasks()

            # 按优先级过滤
            result = await provider.get_tasks(priority=["P0", "P1"])
        """
        project_key = await self._get_project_key()
        type_key = await self._get_type_key()

        # 构建搜索条件
        conditions = []

        # 处理状态过滤
        if status:
            if await self._field_exists(project_key, type_key, "status"):
                field_key = await self.meta.get_field_key(
                    project_key, type_key, "status"
                )
                resolved_values = []
                for s in status:
                    try:
                        val = await self._resolve_field_value(
                            project_key, type_key, field_key, s
                        )
                        resolved_values.append(val)
                    except Exception as e:
                        logger.warning(f"Failed to resolve status '{s}': {e}")
                        resolved_values.append(s)

                conditions.append(
                    {
                        "field_key": field_key,
                        "operator": "IN",
                        "value": resolved_values,
                    }
                )
                logger.info(f"Added status filter: {status}")
            else:
                logger.warning(
                    f"Field 'status' not found in project, skipping status filter"
                )

        # 处理优先级过滤
        if priority:
            if await self._field_exists(project_key, type_key, "priority"):
                field_key = await self.meta.get_field_key(
                    project_key, type_key, "priority"
                )
                resolved_values = []
                for p in priority:
                    try:
                        val = await self._resolve_field_value(
                            project_key, type_key, field_key, p
                        )
                        resolved_values.append(val)
                    except Exception as e:
                        logger.warning(f"Failed to resolve priority '{p}': {e}")
                        resolved_values.append(p)

                conditions.append(
                    {
                        "field_key": field_key,
                        "operator": "IN",
                        "value": resolved_values,
                    }
                )
                logger.info(f"Added priority filter: {priority}")
            else:
                logger.warning(
                    f"Field 'priority' not found in project, skipping priority filter"
                )

        # 处理负责人过滤
        if owner:
            try:
                user_key = await self.meta.get_user_key(owner)
                conditions.append(
                    {
                        "field_key": "owner",
                        "operator": "IN",
                        "value": [user_key],
                    }
                )
                logger.info(f"Added owner filter: {owner}")
            except Exception as e:
                logger.warning(
                    f"Failed to resolve owner '{owner}': {e}, skipping owner filter"
                )

        # 构建 search_group
        search_group = {"conjunction": "AND", "conditions": conditions}

        logger.info(
            f"Querying tasks with {len(conditions)} conditions, page_num={page_num}, page_size={page_size}"
        )

        # 调用 API
        result = await self.api.search_params(
            project_key=project_key,
            work_item_type_key=type_key,
            search_group=search_group,
            page_num=page_num,
            page_size=page_size,
        )

        # 标准化返回结果
        # 处理 API 可能返回列表或字典的情况
        if isinstance(result, list):
            items = result
            pagination = {"total": len(result), "page_num": page_num, "page_size": page_size}
            logger.debug("API returned list format, converted to standard format")
        else:
            items = result.get("work_items", [])
            pagination = result.get("pagination", {})

        logger.info(f"Retrieved {len(items)} items (total: {pagination.get('total', 0)})")

        return {
            "items": items,
            "total": pagination.get("total", len(items)),
            "page_num": pagination.get("page_num", page_num),
            "page_size": pagination.get("page_size", page_size),
        }

    async def list_available_options(self, field_name: str) -> Dict[str, str]:
        """
        列出字段的可用选项

        用于帮助用户了解可用的选项值。

        Args:
            field_name: 字段名称（如 "status", "priority"）

        Returns:
            {label: value} 字典
        """
        project_key = await self._get_project_key()
        type_key = await self._get_type_key()
        field_key = await self.meta.get_field_key(project_key, type_key, field_name)
        return await self.meta.list_options(project_key, type_key, field_key)
