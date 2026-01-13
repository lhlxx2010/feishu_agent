import logging
from typing import Any, Dict, List, Optional

from src.core.config import settings
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
    - 支持从环境变量 FEISHU_PROJECT_KEY 读取默认项目
    """

    def __init__(
        self,
        project_name: Optional[str] = None,
        project_key: Optional[str] = None,
        work_item_type_name: str = "问题管理",
    ):
        # 优先使用显式传入的参数，否则使用环境变量配置
        if not project_name and not project_key:
            if settings.FEISHU_PROJECT_KEY:
                project_key = settings.FEISHU_PROJECT_KEY
            else:
                raise ValueError(
                    "Must provide either project_name or project_key, "
                    "or set FEISHU_PROJECT_KEY environment variable"
                )

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

    def _extract_field_value(self, item: dict, field_key: str) -> Optional[str]:
        """
        从工作项中提取字段值（辅助方法）

        Args:
            item: 工作项字典
            field_key: 字段 Key

        Returns:
            字段值（字符串），如果不存在则返回 None
        """
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
                logger.warning("Field 'status' not found, skipping filter")

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
                logger.warning("Field 'priority' not found, skipping filter")

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
                logger.warning(
                    f"Failed to resolve owner '{owner}': {e}, skipping owner filter"
                )

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
            pagination = {
                "total": len(result),
                "page_num": page_num,
                "page_size": page_size,
            }
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
        name_keyword: Optional[str] = None,
        status: Optional[List[str]] = None,
        priority: Optional[List[str]] = None,
        owner: Optional[str] = None,
        related_to: Optional[int] = None,
        page_num: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        获取工作项列表（支持全量或按条件过滤）

        设计理念:
        - 无参数时返回全部工作项
        - 字段不存在时自动跳过该过滤条件
        - 支持多维度组合过滤
        - 如果提供 name_keyword，优先使用高效的 filter API
        - 支持按关联工作项 ID 过滤（客户端过滤）

        Args:
            name_keyword: 任务名称关键词（可选，支持模糊搜索）
            status: 状态列表（可选，如 ["待处理", "进行中"]）
            priority: 优先级列表（可选，如 ["P0", "P1"]）
            owner: 负责人（可选，姓名或邮箱）
            related_to: 关联工作项 ID（可选），用于查找与指定工作项关联的其他工作项
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

            # 按名称关键词搜索
            result = await provider.get_tasks(name_keyword="SG06VA")

            # 按优先级过滤
            result = await provider.get_tasks(priority=["P0", "P1"])

            # 查找与指定工作项关联的工作项
            result = await provider.get_tasks(related_to=6181818812)
        """
        project_key = await self._get_project_key()
        type_key = await self._get_type_key()

        # 特殊处理：当只有 related_to 参数时，需要获取所有工作项进行客户端过滤
        # 因为关联字段不支持 API 级别的过滤
        if related_to and not name_keyword and not status and not priority and not owner:
            logger.info(f"Getting all items for related_to filtering: {related_to}")
            
            all_items = []
            current_page = 1
            batch_size = 100
            
            while True:
                result = await self.api.filter(
                    project_key=project_key,
                    work_item_type_keys=[type_key],
                    page_num=current_page,
                    page_size=batch_size,
                )
                
                # 标准化返回结果
                if isinstance(result, list):
                    items = result
                elif isinstance(result, dict):
                    items = result.get("work_items", [])
                else:
                    break
                
                if not items:
                    break
                
                all_items.extend(items)
                logger.debug(f"Fetched page {current_page}, got {len(items)} items, total: {len(all_items)}")
                
                # 如果这一页的数据少于 batch_size，说明已经是最后一页
                if len(items) < batch_size:
                    break
                
                current_page += 1
                
                # 安全限制：最多获取 20 页（2000 条记录）
                if current_page > 20:
                    logger.warning("Reached maximum page limit (20 pages)")
                    break
            
            logger.info(f"Fetched {len(all_items)} items in total, now filtering by related_to={related_to}")
            
            # 过滤关联工作项
            filtered_items = []
            for item in all_items:
                is_related = False
                fields = item.get("fields", [])
                for field in fields:
                    field_value = field.get("field_value")
                    if field_value:
                        if isinstance(field_value, list):
                            if related_to in field_value:
                                is_related = True
                                break
                        elif field_value == related_to:
                            is_related = True
                            break
                if is_related:
                    filtered_items.append(item)
            
            logger.info(f"Found {len(filtered_items)} items related to {related_to}")
            
            return {
                "items": filtered_items,
                "total": len(filtered_items),
                "page_num": 1,
                "page_size": len(filtered_items),
            }
        
        # 如果提供了 name_keyword，优先使用 filter API（更高效）
        # filter API 支持 work_item_name 和 work_item_status，但不支持 priority/owner/related_to
        if name_keyword:
            logger.info(f"Using filter API for name keyword search: '{name_keyword}'")

            # 准备 filter API 参数
            filter_kwargs = {}
            if name_keyword:
                filter_kwargs["work_item_name"] = name_keyword

            # filter API 支持 status，但需要转换为状态值
            if status:
                # 尝试解析状态值
                try:
                    field_key = await self.meta.get_field_key(
                        project_key, type_key, "status"
                    )
                    resolved_statuses = []
                    for s in status:
                        try:
                            val = await self._resolve_field_value(
                                project_key, type_key, field_key, s
                            )
                            resolved_statuses.append(val)
                        except Exception as e:
                            logger.warning(f"Failed to resolve status '{s}': {e}")
                    if resolved_statuses:
                        filter_kwargs["work_item_status"] = resolved_statuses
                        logger.info(
                            f"Added status filter to filter API: {resolved_statuses}"
                        )
                except Exception as e:
                    logger.warning(f"Status field not available for filter API: {e}")

            # filter API 不支持 priority、owner 和 related_to，记录警告
            if priority:
                logger.warning(
                    "Filter API does not support priority filter, "
                    "will filter results after retrieval"
                )
            if owner:
                logger.warning(
                    "Filter API does not support owner filter, "
                    "will filter results after retrieval"
                )
            if related_to:
                logger.warning(
                    "Filter API does not support related_to filter, "
                    "will filter results after retrieval"
                )

            result = await self.api.filter(
                project_key=project_key,
                work_item_type_keys=[type_key],
                page_num=page_num,
                page_size=page_size,
                **filter_kwargs,
            )

            # 标准化返回结果
            if isinstance(result, list):
                items = result
                pagination = {
                    "total": len(result),
                    "page_num": page_num,
                    "page_size": page_size,
                }
                logger.debug("API returned list format, converted to standard format")
            elif isinstance(result, dict):
                items = result.get("work_items", [])
                pagination = result.get("pagination", {})
                # 如果 pagination 不是字典，创建默认的
                if not isinstance(pagination, dict):
                    pagination = {
                        "total": result.get("total", len(items)),
                        "page_num": page_num,
                        "page_size": page_size,
                    }
            else:
                logger.warning(f"Unexpected result type: {type(result)}, value: {result}")
                items = []
                pagination = {
                    "total": 0,
                    "page_num": page_num,
                    "page_size": page_size,
                }

            # 如果 filter API 不支持某些条件，在结果中进一步筛选
            if priority or owner or related_to:
                filtered_items = []
                for item in items:
                    # 检查优先级
                    if priority:
                        item_priority = self._extract_field_value(item, "priority")
                        if item_priority not in priority:
                            continue

                    # 检查负责人
                    if owner:
                        try:
                            user_key = await self.meta.get_user_key(owner)
                            item_owner_key = self._extract_field_value(item, "owner")
                            # 如果提取的是 user_key，直接比较
                            if item_owner_key and item_owner_key != user_key:
                                # 尝试匹配名称（owner 字段可能返回名称）
                                if owner.lower() not in (item_owner_key or "").lower():
                                    continue
                        except Exception as e:
                            logger.debug(f"Failed to filter by owner '{owner}': {e}")
                            # 如果无法解析 owner，跳过该过滤条件
                            pass

                    # 检查关联工作项
                    if related_to:
                        is_related = False
                        fields = item.get("fields", [])
                        for field in fields:
                            field_value = field.get("field_value")
                            # 检查字段值是否包含目标工作项 ID
                            if field_value:
                                if isinstance(field_value, list):
                                    if related_to in field_value:
                                        is_related = True
                                        break
                                elif field_value == related_to:
                                    is_related = True
                                    break
                        if not is_related:
                            continue

                    filtered_items.append(item)

                items = filtered_items
                logger.info(
                    f"Filtered results: {len(items)} items after priority/owner/related_to filtering"
                )

            logger.info(
                f"Retrieved {len(items)} items (total: {pagination.get('total', 0)})"
            )

            return {
                "items": items,
                "total": pagination.get("total", len(items)),
                "page_num": pagination.get("page_num", page_num),
                "page_size": pagination.get("page_size", page_size),
            }

        # 没有 name_keyword，使用 search_params API 进行复杂条件查询
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
                    "Field 'status' not found in project, skipping status filter"
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
                    "Field 'priority' not found in project, skipping priority filter"
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
            pagination = {
                "total": len(result),
                "page_num": page_num,
                "page_size": page_size,
            }
            logger.debug("API returned list format, converted to standard format")
        else:
            items = result.get("work_items", [])
            pagination = result.get("pagination", {})

        logger.info(
            f"Retrieved {len(items)} items (total: {pagination.get('total', 0)})"
        )

        # 如果指定了 related_to，进行客户端过滤
        # search_params API 不支持关联字段过滤
        if related_to:
            logger.info(f"Applying client-side related_to filter: {related_to}")
            filtered_items = []
            for item in items:
                is_related = False
                fields = item.get("fields", [])
                for field in fields:
                    field_value = field.get("field_value")
                    # 检查字段值是否包含目标工作项 ID
                    if field_value:
                        if isinstance(field_value, list):
                            if related_to in field_value:
                                is_related = True
                                break
                        elif field_value == related_to:
                            is_related = True
                            break
                if is_related:
                    filtered_items.append(item)
            
            items = filtered_items
            logger.info(
                f"Filtered results: {len(items)} items after related_to filtering"
            )

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
