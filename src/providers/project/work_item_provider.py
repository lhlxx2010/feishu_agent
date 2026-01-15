import asyncio
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from src.core.cache import SimpleCache
from src.core.config import settings
from src.providers.base import Provider
from src.providers.project.api.work_item import WorkItemAPI
from src.providers.project.api.user import UserAPI
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

    # 类常量：缓存中"未找到"的标记值
    _NOT_FOUND_MARKER: str = "__NOT_FOUND__"

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
        self.user_api = UserAPI()
        self.meta = MetadataManager.get_instance()

        # 线程安全：用于保护类型 Key 解析的锁和缓存
        self._type_key_lock = asyncio.Lock()
        self._resolved_type_key: Optional[str] = None

        # 缓存配置
        # 用户ID到姓名的缓存，TTL 10分钟（600秒）
        self._user_cache = SimpleCache(ttl=600)
        # 工作项ID到名称的缓存，TTL 5分钟（300秒）
        self._work_item_cache = SimpleCache(ttl=300)

    async def _get_project_key(self) -> str:
        if not self._project_key:
            if self.project_name:
                self._project_key = await self.meta.get_project_key(self.project_name)
            else:
                raise ValueError("Project key not resolved")
        return self._project_key

    async def _get_type_key(self) -> str:
        """
        获取工作项类型 Key（线程安全）

        使用锁保护状态检查和修改，避免竞态条件。
        当指定的类型不存在时，如果使用的是默认类型 "问题管理"，
        会自动 fallback 到项目中的第一个可用类型。

        Returns:
            工作项类型 Key

        Raises:
            ValueError: 当类型不存在且无法 fallback 时
        """
        async with self._type_key_lock:
            # 快速路径：已解析过则直接返回缓存
            if self._resolved_type_key is not None:
                return self._resolved_type_key

            project_key = await self._get_project_key()

            try:
                self._resolved_type_key = await self.meta.get_type_key(
                    project_key, self.work_item_type_name
                )
                return self._resolved_type_key
            except (ValueError, KeyError) as e:
                # 仅当使用默认类型 "问题管理" 时才尝试 fallback
                if self.work_item_type_name != "问题管理":
                    raise

                types = await self.meta.list_types(project_key)
                if not types:
                    raise ValueError(
                        f"项目 {project_key} 中没有可用的工作项类型"
                    ) from e

                # 使用 items() 同时获取 key 和 value，更 Pythonic
                first_type_name, first_type_key = next(iter(types.items()))
                logger.warning(
                    "默认类型 '问题管理' 不存在，临时使用 '%s' 替代",
                    first_type_name,
                )
                # 缓存解析结果，避免后续调用再次触发 fallback
                self._resolved_type_key = first_type_key
                return self._resolved_type_key

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
        except (ValueError, KeyError) as e:
            logger.debug("Field '%s' not found: %s", field_name, e)
            return False

    def _extract_field_value(self, item: dict, field_key: str) -> Optional[str]:
        """
        从工作项中提取字段值（辅助方法）

        支持两种数据结构：
        1. field_value_pairs: 旧版结构，字段以键值对列表形式存在
        2. fields: 新版结构，字段以对象列表形式存在

        Args:
            item: 工作项字典
            field_key: 字段 Key

        Returns:
            字段值（字符串），如果不存在则返回 None
        """
        logger.debug(
            "_extract_field_value: Looking for field_key='%s' in item id=%s",
            field_key,
            item.get("id"),
        )

        # 首先尝试从 fields 数组中查找
        fields = item.get("fields", [])
        logger.debug(
            "_extract_field_value: fields count=%d, available field_keys=%s",
            len(fields),
            [f.get("field_key") for f in fields],
        )
        for field in fields:
            if field.get("field_key") == field_key:
                value = field.get("field_value")
                logger.debug("_extract_field_value: Found field, value=%s", value)
                # 处理选项类型字段
                if isinstance(value, dict):
                    result = value.get("label") or value.get("value")
                    logger.debug(
                        "_extract_field_value: Extracted from dict: %s", result
                    )
                    return result
                # 处理用户类型字段
                if isinstance(value, list) and value:
                    first = value[0]
                    if isinstance(first, dict):
                        result = first.get("name") or first.get("name_cn")
                        logger.debug(
                            "_extract_field_value: Extracted from user list: %s", result
                        )
                        return result
                result = str(value) if value else None
                logger.debug("_extract_field_value: Extracted as string: %s", result)
                return result

        # 回退到 field_value_pairs
        field_pairs = item.get("field_value_pairs", [])
        logger.debug(
            "_extract_field_value: field_value_pairs count=%d", len(field_pairs)
        )
        for pair in field_pairs:
            if pair.get("field_key") == field_key:
                value = pair.get("field_value")
                logger.debug("_extract_field_value: Found in pairs, value=%s", value)
                # 处理选项类型字段
                if isinstance(value, dict):
                    result = value.get("label") or value.get("value")
                    logger.debug(
                        "_extract_field_value: Extracted from dict (pairs): %s", result
                    )
                    return result
                # 处理用户类型字段
                if isinstance(value, list) and value:
                    first = value[0]
                    if isinstance(first, dict):
                        result = first.get("name") or first.get("name_cn")
                        logger.debug(
                            "_extract_field_value: Extracted from user list (pairs): %s",
                            result,
                        )
                        return result
                result = str(value) if value else None
                logger.debug(
                    "_extract_field_value: Extracted as string (pairs): %s", result
                )
                return result

        logger.debug("_extract_field_value: Field key '%s' not found", field_key)
        return None

    async def simplify_work_item(
        self, item: dict, field_mapping: Optional[Dict[str, str]] = None
    ) -> dict:
        """
        将工作项简化为摘要格式，减少 Token 消耗

        Args:
            item: 原始工作项字典
            field_mapping: 字段名称到字段Key的映射（可选）

        Returns:
            简化后的工作项字典，包含 id, name, status, priority, owner
        """

        # 使用field_mapping获取实际的字段Key，如果没有映射则使用字段名称作为Key
        def get_field_key(field_name: str) -> str:
            if field_mapping and field_name in field_mapping:
                return field_mapping[field_name]
            return field_name

        priority_key = get_field_key("priority")
        priority_value = self._extract_field_value(item, priority_key)

        logger.info(
            "simplify_work_item: item id=%s, keys=%s, field_mapping=%s, priority_key=%s, priority_value=%s",
            item.get("id"),
            list(item.keys()),
            field_mapping,
            priority_key,
            priority_value,
        )

        if "fields" in item:
            fields = item.get("fields", [])
            logger.info(
                "simplify_work_item: fields count=%d, field_keys=%s",
                len(fields),
                [f.get("field_key") for f in fields],
            )
            for field in fields:
                if field.get("field_key") == priority_key:
                    logger.info("simplify_work_item: found priority field: %s", field)
        elif "field_value_pairs" in item:
            pairs = item.get("field_value_pairs", [])
            logger.info("simplify_work_item: field_value_pairs count=%d", len(pairs))
            for pair in pairs:
                if pair.get("field_key") == priority_key:
                    logger.info("simplify_work_item: found priority in pairs: %s", pair)

        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "status": self._extract_field_value(item, get_field_key("status")),
            "priority": priority_value,
            "owner": self._extract_field_value(item, get_field_key("owner")),
        }

    async def simplify_work_items(
        self, items: List[dict], field_mapping: Optional[Dict[str, str]] = None
    ) -> List[dict]:
        """
        批量简化工作项列表

        Args:
            items: 原始工作项列表
            field_mapping: 字段名称到字段Key的映射（可选）

        Returns:
            简化后的工作项列表，owner 字段会转换为人名以提高可读性
        """
        logger.info("simplify_work_items: processing %d items", len(items))
        if items:
            logger.info("First item keys: %s", list(items[0].keys()))
            if "fields" in items[0]:
                fields = items[0].get("fields", [])
                logger.info(
                    "First item fields count: %d, field_keys: %s",
                    len(fields),
                    [f.get("field_key") for f in fields],
                )
        # 并行简化所有工作项
        tasks = [self.simplify_work_item(item, field_mapping) for item in items]
        simplified_items = await asyncio.gather(*tasks)

        # 批量转换 owner user_key 为人名
        owner_keys = []
        for item in simplified_items:
            owner = item.get("owner")
            if owner and isinstance(owner, str):
                # 检查是否是 user_key 格式（长数字字符串）
                if owner.isdigit() and len(owner) > 10:
                    owner_keys.append(owner)

        if owner_keys:
            # 去重
            unique_keys = list(set(owner_keys))
            logger.info("Converting %d unique owner keys to names", len(unique_keys))
            try:
                key_to_name = await self.meta.batch_get_user_names(unique_keys)
                # 替换 owner 字段
                for item in simplified_items:
                    owner = item.get("owner")
                    if owner and owner in key_to_name:
                        item["owner"] = key_to_name[owner]
            except Exception as e:
                logger.warning("Failed to convert owner keys to names: %s", e)
                # 失败时保持原样，不影响正常返回

        return simplified_items

    async def resolve_related_to(
        self, related_to: Union[int, str], project: Optional[str] = None
    ) -> int:
        """
        解析 related_to 参数，将名称转换为工作项 ID

        支持三种输入方式：
        1. 整数: 直接返回
        2. 数字字符串: 转换为整数返回
        3. 非数字字符串: 在多个工作项类型中搜索，返回匹配的 ID

        Args:
            related_to: 工作项 ID 或名称
            project: 项目标识符（可选），用于名称搜索

        Returns:
            工作项 ID

        Raises:
            ValueError: 未找到匹配的工作项
        """
        # 整数: 直接返回
        if isinstance(related_to, int):
            logger.info("resolve_related_to: 直接使用整数 ID: %s", related_to)
            return related_to

        # 字符串处理
        if isinstance(related_to, str):
            # 数字字符串: 转换为整数
            if related_to.isdigit():
                result = int(related_to)
                logger.info("resolve_related_to: 字符串转整数 ID: %s", result)
                return result

            # 非数字字符串: 按名称搜索
            logger.info("resolve_related_to: 按名称搜索 '%s'", related_to)

            # 在常见工作项类型中搜索
            search_types = [
                "项目管理",
                "需求管理",
                "Issue管理",
                "任务",
                "Epic",
                "事务管理",
            ]
            found_item = None

            for search_type in search_types:
                try:
                    # 创建临时 Provider 搜索
                    temp_provider = WorkItemProvider(
                        project_name=self.project_name,
                        project_key=self._project_key,
                        work_item_type_name=search_type,
                    )
                    search_result = await temp_provider.get_tasks(
                        name_keyword=related_to, page_num=1, page_size=10
                    )

                    items = search_result.get("items", [])
                    if items:
                        # 优先精确匹配
                        for item in items:
                            if item.get("name") == related_to:
                                found_item = item
                                logger.info(
                                    "resolve_related_to: 精确匹配 '%s' (ID: %s, Type: %s)",
                                    item.get("name"),
                                    item.get("id"),
                                    search_type,
                                )
                                break

                        # 如果没有精确匹配，取第一个部分匹配
                        if not found_item:
                            found_item = items[0]
                            logger.info(
                                "resolve_related_to: 部分匹配 '%s' (ID: %s, Type: %s)",
                                found_item.get("name"),
                                found_item.get("id"),
                                search_type,
                            )
                        break
                except Exception as e:
                    logger.debug(
                        "resolve_related_to: 在类型 '%s' 中搜索失败: %s",
                        search_type,
                        e,
                    )
                    continue

            if found_item:
                result = found_item.get("id")
                logger.info(
                    "resolve_related_to: 解析 '%s' -> ID: %s", related_to, result
                )
                return result
            else:
                raise ValueError(f"未找到名称为 '{related_to}' 的工作项")

        # 其他类型: 尝试转换
        try:
            result = int(related_to)
            logger.info("resolve_related_to: 类型转换 ID: %s", result)
            return result
        except (ValueError, TypeError):
            raise ValueError(
                f"related_to 必须是工作项 ID（整数）或名称（字符串），当前类型: {type(related_to)}"
            )

    async def _resolve_field_value(
        self, project_key: str, type_key: str, field_key: str, value: Any
    ) -> Any:
        """解析字段值：如果是 Select 类型且值为 Label，转换为 Option Value"""
        try:
            val = await self.meta.get_option_value(
                project_key, type_key, field_key, str(value)
            )
            logger.info(
                "Resolved option '%s' -> '%s' for field '%s'", value, val, field_key
            )
            return val
        except Exception as e:
            logger.warning(
                "Failed to resolve option '%s' for field '%s': %s",
                value,
                field_key,
                e,
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

        logger.info("Creating Issue in Project: %s, Type: %s", project_key, type_key)

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

                logger.info("Updating priority to %s...", option_val)
                await self.api.update(
                    project_key,
                    type_key,
                    issue_id,
                    [{"field_key": field_key, "field_value": option_val}],
                )
            except Exception as e:
                logger.warning("Failed to update priority: %s", e)

        return issue_id

    async def get_issue_details(self, issue_id: int) -> Dict[str, Any]:
        """获取 Issue 详情"""
        project_key = await self._get_project_key()
        type_key = await self._get_type_key()

        items = await self.api.query(project_key, type_key, [issue_id])
        if not items:
            raise Exception(f"Issue {issue_id} not found")
        return items[0]

    async def _try_fetch_type(
        self, project_key: str, type_key: str, work_item_ids: List[int]
    ) -> List[Dict[str, Any]]:
        """
        尝试从指定类型中获取工作项

        Args:
            project_key: 项目 Key
            type_key: 工作项类型 Key
            work_item_ids: 工作项 ID 列表

        Returns:
            工作项列表，查询失败时返回空列表
        """
        try:
            return await self.api.query(project_key, type_key, work_item_ids)
        except Exception:
            return []

    async def _get_users_with_cache(self, user_keys: List[str]) -> Dict[str, str]:
        """
        通过缓存获取用户信息

        Args:
            user_keys: 用户Key列表

        Returns:
            用户Key到姓名的映射字典
        """
        user_map = {}
        users_to_fetch = []

        # 首先检查缓存
        for user_key in user_keys:
            cached_name = self._user_cache.get(user_key)
            if cached_name is not None:
                user_map[user_key] = cached_name
            else:
                users_to_fetch.append(user_key)

        # 如果有未缓存的用户，批量查询
        if users_to_fetch:
            try:
                users = await self.user_api.query_users(user_keys=users_to_fetch)
                for user in users:
                    user_key = user.get("user_key")
                    user_name = user.get("name_cn") or user.get("name_en") or user_key
                    if user_key:
                        user_map[user_key] = user_name
                        # 存入缓存
                        self._user_cache.set(user_key, user_name)
            except Exception as e:
                logger.warning("Failed to fetch users: %s", e)
                # 如果查询失败，将用户 Key 作为名称使用
                for user_key in users_to_fetch:
                    user_map[user_key] = user_key

        return user_map

    async def _get_work_items_with_cache(
        self, work_item_ids: List[int], project_key: str, type_key: str
    ) -> Tuple[Dict[int, str], List[int]]:
        """
        通过缓存获取工作项名称

        Args:
            work_item_ids: 工作项 ID 列表
            project_key: 项目 Key
            type_key: 工作项类型 Key

        Returns:
            (工作项 ID 到名称的映射字典, 未找到的 ID 列表)
        """
        work_item_map: Dict[int, str] = {}
        items_to_fetch: List[int] = []

        # 首先检查缓存
        for item_id in work_item_ids:
            cached_value = self._work_item_cache.get(str(item_id))
            if cached_value is not None:
                if cached_value != self._NOT_FOUND_MARKER:
                    work_item_map[item_id] = cached_value
                # 如果是 _NOT_FOUND_MARKER，则跳过，不添加到 items_to_fetch
            else:
                items_to_fetch.append(item_id)

        # 如果有未缓存的工作项，批量查询当前类型
        if items_to_fetch:
            try:
                items = await self.api.query(project_key, type_key, items_to_fetch)
                found_ids: Set[int] = set()
                for item in items:
                    item_id = item.get("id")
                    item_name = item.get("name") or ""
                    if item_id:
                        work_item_map[item_id] = item_name
                        # 存入缓存
                        self._work_item_cache.set(str(item_id), item_name)
                        found_ids.add(item_id)

                # 计算未找到的 ID，并缓存"未找到"标记
                not_found_ids = [
                    item_id for item_id in items_to_fetch if item_id not in found_ids
                ]
                for item_id in not_found_ids:
                    self._work_item_cache.set(str(item_id), self._NOT_FOUND_MARKER)

            except Exception as e:
                logger.debug("Failed to fetch work items in current type: %s", e)
                # 如果查询失败，所有待查询的 ID 都视为未找到
                not_found_ids = items_to_fetch
                # 不缓存失败结果，因为可能是临时错误
        else:
            not_found_ids = []

        return work_item_map, not_found_ids

    async def get_readable_issue_details(self, issue_id: int) -> Dict[str, Any]:
        """
        获取 Issue 详情，并将用户相关字段转换为人名以提高可读性

        Args:
            issue_id: Issue ID

        Returns:
            增强后的 Issue 详情，包含原始数据和可读字段
        """
        item = await self.get_issue_details(issue_id)
        return await self._enhance_work_item_with_readable_names(item)

    async def _enhance_work_item_with_readable_names(
        self, item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        增强工作项数据，将字段 Key 和 ID 转换为可读名称

        Args:
            item: 原始工作项字典

        Returns:
            增强后的工作项字典，包含 readable_fields 字段
        """
        if not item:
            return item

        # 创建副本，避免修改原始数据
        enhanced = item.copy()

        # 获取项目和类型 Key
        project_key = item.get("project_key") or await self._get_project_key()
        type_key = item.get("work_item_type_key") or await self._get_type_key()

        # 获取字段定义映射 (Name -> Key)
        try:
            fields_map = await self.meta.list_fields(project_key, type_key)
            # 反转映射 (Key -> Name)
            # 注意: 如果有多个名称映射到同一个 Key (别名)，会随机保留一个
            key_to_name = {v: k for k, v in fields_map.items()}
        except Exception as e:
            logger.warning("Failed to load field definitions: %s", e)
            key_to_name = {}

        # 准备收集 ID 的容器
        users_to_fetch = set()
        work_items_to_fetch = set()

        # 统一处理 fields (新版) 和 field_value_pairs (旧版)
        fields = item.get("fields", [])
        if not fields:
            # 尝试转换旧版结构
            field_value_pairs = item.get("field_value_pairs", [])
            for pair in field_value_pairs:
                fields.append(
                    {
                        "field_key": pair.get("field_key"),
                        "field_value": pair.get("field_value"),
                        # 旧版可能没有 type_key，后续只能尽力猜测
                        "field_type_key": "unknown",
                    }
                )

        # 第一遍遍历: 收集需要查询的 ID
        for field in fields:
            f_key = field.get("field_key")
            f_val = field.get("field_value")
            f_type = field.get("field_type_key", "")

            if not f_val:
                continue

            # 用户相关字段
            if f_type in ["user", "owner", "creator", "modifier"]:
                if isinstance(f_val, str):
                    users_to_fetch.add(f_val)
            elif f_type in ["multi_user", "role_owners"]:
                if isinstance(f_val, list):
                    for u in f_val:
                        if isinstance(u, str):
                            users_to_fetch.add(u)
            # 兼容 owner 字段 (可能不在 fields 中，而在根目录)
            elif f_key == "owner" and isinstance(f_val, str):
                users_to_fetch.add(f_val)

            # 关联工作项字段
            if f_type in ["work_item_related_select", "work_item_related_multi_select"]:
                if isinstance(f_val, list):
                    for wid in f_val:
                        if isinstance(wid, (int, str)) and str(wid).isdigit():
                            work_items_to_fetch.add(int(wid))
                elif isinstance(f_val, (int, str)) and str(f_val).isdigit():
                    work_items_to_fetch.add(int(f_val))

        # 根目录的 owner, created_by, updated_by
        for key in ["owner", "created_by", "updated_by"]:
            val = item.get(key)
            if val and isinstance(val, str):
                users_to_fetch.add(val)

        # 批量获取数据
        user_map = {}
        work_item_map = {}

        if users_to_fetch:
            # 使用缓存获取用户信息
            user_map = await self._get_users_with_cache(list(users_to_fetch))

        if work_items_to_fetch:
            # 首先使用缓存获取当前类型中的工作项
            cached_map, not_found_ids = await self._get_work_items_with_cache(
                list(work_items_to_fetch), project_key, type_key
            )
            work_item_map.update(cached_map)

            # 如果有未找到的工作项，尝试其他所有类型
            if not_found_ids:
                remaining_ids = set(not_found_ids)

                try:
                    # 获取项目中所有可用类型
                    try:
                        all_types = await self.meta.list_types(project_key)
                        target_types = {
                            name: key
                            for name, key in all_types.items()
                            if key != type_key  # 排除当前类型
                        }
                    except Exception as e:
                        logger.warning("Failed to list project types: %s", e)
                        target_types = {}

                    if target_types:
                        # 限制并发数，避免触发 API 限流
                        # 分批处理类型，每批 5 个
                        type_items = list(target_types.items())
                        batch_size = 5

                        for i in range(0, len(type_items), batch_size):
                            if not remaining_ids:
                                break

                            batch = type_items[i : i + batch_size]
                            search_tasks = [
                                self._try_fetch_type(
                                    project_key, t_key, list(remaining_ids)
                                )
                                for _t_name, t_key in batch
                            ]

                            results = await asyncio.gather(*search_tasks)

                            for items in results:
                                for related_item in items:
                                    related_id = related_item.get("id")
                                    related_name = related_item.get("name") or ""
                                    if related_id:
                                        work_item_map[related_id] = related_name
                                        # 存入缓存
                                        self._work_item_cache.set(
                                            str(related_id), related_name
                                        )
                                        remaining_ids.discard(related_id)

                        # 缓存仍未找到的 ID（跨类型查询后）
                        if remaining_ids:
                            logger.debug(
                                "Still not found after cross-type search: %s",
                                remaining_ids,
                            )
                            for remaining_id in remaining_ids:
                                self._work_item_cache.set(
                                    str(remaining_id), self._NOT_FOUND_MARKER
                                )

                except Exception as e:
                    logger.warning(
                        "Failed to fetch related items from other types: %s", e
                    )

        # 第二遍遍历: 构建可读字段
        readable_fields = {}

        # 处理 fields 列表
        for field in fields:
            f_key = field.get("field_key")
            f_val = field.get("field_value")
            f_type = field.get("field_type_key", "")
            f_alias = field.get("field_alias")

            if f_key is None:
                continue

            # 确定字段名称 (优先用别名，其次查定义，最后用 key)
            field_name = f_alias
            if not field_name:
                field_name = key_to_name.get(f_key, f_key)

            # 确保是字符串
            if field_name is None:
                field_name = str(f_key) if f_key else "unknown"

            readable_val = f_val

            # 用户字段处理（根据类型或字段键判断）
            user_field_keys = [
                "owner",
                "creator",
                "modifier",
                "assignee",
                "created_by",
                "updated_by",
            ]
            is_user_field = f_type in ["user", "owner", "creator", "modifier"] or (
                f_type == "unknown" and f_key in user_field_keys
            )

            # 转换值
            if f_val is not None:
                if is_user_field:
                    if isinstance(f_val, str):
                        readable_val = user_map.get(f_val, f_val)
                    else:
                        # 使用提取方法处理非字符串值（如字典或列表）
                        readable_val = self._extract_readable_field_value(f_val)
                elif f_type == "multi_user":
                    if isinstance(f_val, list):
                        new_list = []
                        for u in f_val:
                            if isinstance(u, str):
                                new_list.append(user_map.get(u, u))
                            else:
                                new_list.append(self._extract_readable_field_value(u))
                        readable_val = new_list
                elif f_type == "role_owners":
                    # Parse role_owners structure: [{"role": "role_key", "owners": ["user_key"]}]
                    if isinstance(f_val, list):
                        readable_roles = []
                        for role_item in f_val:
                            if not isinstance(role_item, dict):
                                continue

                            role_key = role_item.get("role")
                            owners = role_item.get("owners")

                            # 防御性检查
                            if not role_key:
                                continue

                            if not isinstance(owners, list):
                                owners = []

                            # Resolve Role Name
                            role_name = role_key
                            try:
                                name = await self.meta.get_role_name(
                                    project_key, type_key, role_key
                                )
                                if name:
                                    role_name = name
                            except Exception as e:
                                logger.debug(
                                    f"Failed to resolve role name for key '{role_key}': {e}"
                                )

                            # Resolve Owner Names
                            owner_names = []
                            for u in owners:
                                owner_names.append(user_map.get(u, u))

                            readable_roles.append(
                                {"role": role_name, "owners": owner_names}
                            )
                        readable_val = readable_roles
                # 关联工作项
                elif f_type in [
                    "work_item_related_select",
                    "work_item_related_multi_select",
                ]:
                    if isinstance(f_val, list):
                        new_list = []
                        for wid in f_val:
                            if isinstance(wid, (int, str)) and str(wid).isdigit():
                                new_list.append(work_item_map.get(int(wid), wid))
                            else:
                                new_list.append(wid)
                        readable_val = new_list
                    elif isinstance(f_val, (int, str)) and str(f_val).isdigit():
                        readable_val = work_item_map.get(int(f_val), f_val)
                # 选项 (Select / MultiSelect)
                elif isinstance(f_val, dict) and ("label" in f_val or "name" in f_val):
                    readable_val = f_val.get("label") or f_val.get("name")
                elif isinstance(f_val, list) and f_val and isinstance(f_val[0], dict):
                    # MultiSelect 通常返回包含 label/value 的字典列表
                    # 如果是用户字段（已在上面处理过），跳过此处理
                    if not is_user_field:
                        new_list = []
                        for item in f_val:
                            if isinstance(item, dict):
                                new_list.append(
                                    item.get("label") or item.get("name") or item
                                )
                            else:
                                new_list.append(item)
                        readable_val = new_list

            readable_fields[field_name] = readable_val

        # 处理根目录特殊字段
        for key in ["owner", "created_by", "updated_by"]:
            val = item.get(key)
            if val and isinstance(val, str):
                readable_fields[key] = user_map.get(val, val)

        enhanced["readable_fields"] = readable_fields

        # 为常用字段添加顶级可读别名
        common_fields = ["owner", "creator", "updater", "assignee"]
        for field in common_fields:
            if field in readable_fields:
                enhanced[f"readable_{field}"] = readable_fields[field]

        return enhanced

    def _extract_readable_field_value(self, field_value: Any) -> Any:
        """
        提取可读的字段值，特别处理用户相关字段

        Args:
            field_value: 原始字段值

        Returns:
            可读的字段值，如果无法提取则返回原始值
        """
        if field_value is None:
            return None

        # 如果是字典且包含 label 或 name 字段，优先返回这些
        if isinstance(field_value, dict):
            if "label" in field_value:
                return field_value["label"]
            if "name" in field_value:
                return field_value["name"]
            if "name_cn" in field_value:
                return field_value["name_cn"]
            # 如果字典中没有可读字段，返回整个字典（可能是复杂对象）
            return field_value

        # 如果是列表，处理每个元素
        if isinstance(field_value, list):
            # 空列表返回空列表
            if not field_value:
                return field_value

            # 单元素列表且元素是字典：尝试提取可读值
            if len(field_value) == 1 and isinstance(field_value[0], dict):
                single_item = field_value[0]
                # 尝试提取 name, name_cn, label
                for key in ["name", "name_cn", "label"]:
                    if key in single_item:
                        return single_item[key]
                # 如果没有可读键，返回整个字典
                return single_item

            # 多元素列表：处理每个元素
            readable_items = []
            for item in field_value:
                readable_item = self._extract_readable_field_value(item)
                if readable_item is not None:
                    readable_items.append(readable_item)
            return readable_items if readable_items else field_value

        # 其他类型直接返回
        return field_value

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
            logger.info("Updated Issue %d with %d fields", issue_id, len(update_fields))

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
                        logger.warning("Failed to resolve status '%s': %s", s, e)
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
                        logger.warning("Failed to resolve priority '%s': %s", p, e)
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
                    "Failed to resolve owner '%s': %s, skipping owner filter",
                    owner,
                    e,
                )

        # 构建 search_group
        search_group = {
            "conjunction": "AND",
            "search_params": conditions,
            "search_groups": [],
        }

        logger.info("Filtering issues with conditions: %s", conditions)
        logger.debug("filter_issues: Built search_group: %s", search_group)

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

        # 特殊处理：当只有 related_to 参数时，需要获取工作项进行客户端过滤
        # 因为关联字段不支持 API 级别的过滤
        # 优化：增量加载，达到结果数量限制后停止，避免全量扫描
        if (
            related_to
            and not name_keyword
            and not status
            and not priority
            and not owner
        ):
            logger.info("Getting items for related_to filtering: %s", related_to)

            # 配置限制：扫描足够的数据以确保找到所有关联项
            # 注意：related_to 过滤只能在客户端进行，需要扫描较多数据
            MAX_TOTAL_ITEMS = 2000  # 最多扫描 2000 条记录
            MAX_PAGES = 40  # 最多 40 页
            BATCH_SIZE = 50  # 每批 50 条，减少内存占用
            CONCURRENT_PAGES = 5  # 每次并发请求的页数

            found_items = []
            total_fetched = 0
            current_page = 1

            while total_fetched < MAX_TOTAL_ITEMS and current_page <= MAX_PAGES:
                # 确定本次并发请求的页码范围
                end_page = min(current_page + CONCURRENT_PAGES, MAX_PAGES + 1)
                page_range = range(current_page, end_page)

                tasks = []
                for p in page_range:
                    tasks.append(
                        self.api.filter(
                            project_key=project_key,
                            work_item_type_keys=[type_key],
                            page_num=p,
                            page_size=BATCH_SIZE,
                        )
                    )

                logger.info(
                    "Fetching pages %d to %d concurrently...",
                    current_page,
                    end_page - 1,
                )

                # 并发执行请求
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # 处理结果
                batch_items_count = 0
                should_stop = False

                for i, result in enumerate(results):
                    page_num = current_page + i

                    if isinstance(result, Exception):
                        logger.error("Failed to fetch page %d: %s", page_num, result)
                        continue

                    # 标准化返回结果
                    if isinstance(result, list):
                        items = result
                    elif isinstance(result, dict):
                        items = result.get("work_items", [])
                    else:
                        items = []

                    if not items:
                        should_stop = True
                        # 不break，继续处理其他成功页面的结果

                    batch_items_count += len(items)
                    total_fetched += len(items)

                    # 过滤关联工作项
                    for item in items:
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
                            found_items.append(item)

                    # 如果某一页的数据少于 BATCH_SIZE，说明已经是最后一页
                    if len(items) < BATCH_SIZE:
                        should_stop = True

                logger.debug(
                    "Fetched pages %d-%d: %d items, found %d related items so far",
                    current_page,
                    end_page - 1,
                    batch_items_count,
                    len(found_items),
                )

                if should_stop:
                    break

                current_page += CONCURRENT_PAGES

            logger.info(
                "Fetched %d items, found %d items related to %s",
                total_fetched,
                len(found_items),
                related_to,
            )

            # 如果获取了大量数据但找到的关联项很少，记录警告
            if total_fetched > 200 and len(found_items) < 5:
                logger.warning(
                    "Low efficiency: fetched %d items but only found %d related items. "
                    "Consider using name_keyword to narrow search.",
                    total_fetched,
                    len(found_items),
                )

            return {
                "items": found_items,
                "total": len(found_items),
                "page_num": 1,
                "page_size": len(found_items),
                "hint": f"Found {len(found_items)} items related to {related_to} (searched {total_fetched} items)",
            }

        # 如果提供了 name_keyword，优先使用 filter API（更高效）
        # filter API 支持 work_item_name 和 work_item_status，但不支持 priority/owner/related_to
        if name_keyword:
            logger.info("Using filter API for name keyword search: '%s'", name_keyword)

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
                            logger.warning("Failed to resolve status '%s': %s", s, e)
                    if resolved_statuses:
                        filter_kwargs["work_item_status"] = resolved_statuses
                        logger.info(
                            "Added status filter to filter API: %s", resolved_statuses
                        )
                except Exception as e:
                    logger.warning("Status field not available for filter API: %s", e)

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
                logger.warning(
                    f"Unexpected result type: {type(result)}, value: {result}"
                )
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
                            logger.debug("Failed to filter by owner '%s': %s", owner, e)
                            # 如果无法解析 owner，跳过该过滤条件

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
                        logger.warning("Failed to resolve status '%s': %s", s, e)
                        resolved_values.append(s)

                conditions.append(
                    {
                        "field_key": field_key,
                        "operator": "IN",
                        "value": resolved_values,
                    }
                )
                logger.info("Added status filter: %s", status)
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
                        logger.warning("Failed to resolve priority '%s': %s", p, e)
                        resolved_values.append(p)

                conditions.append(
                    {
                        "field_key": field_key,
                        "operator": "IN",
                        "value": resolved_values,
                    }
                )
                logger.info("Added priority filter: %s", priority)
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
                logger.info("Added owner filter: %s", owner)
            except Exception as e:
                logger.warning(
                    "Failed to resolve owner '%s': %s, skipping owner filter", owner, e
                )

        # 构建 search_group
        search_group = {
            "conjunction": "AND",
            "search_params": conditions,
            "search_groups": [],
        }

        logger.info(
            f"Querying tasks with {len(conditions)} conditions, page_num={page_num}, page_size={page_size}"
        )
        logger.debug("get_tasks: Built search_group: %s", search_group)

        # 构建需要返回的字段列表
        fields_to_fetch = []
        if status or priority or owner or related_to:
            # 我们需要这些字段进行客户端过滤或显示
            needed_fields = ["priority", "status", "owner"]
            for field_name in needed_fields:
                try:
                    field_key = await self.meta.get_field_key(
                        project_key, type_key, field_name
                    )
                    fields_to_fetch.append(field_key)
                except Exception as e:
                    logger.debug("Failed to get field key for '%s': %s", field_name, e)

        # 调用 API
        result = await self.api.search_params(
            project_key=project_key,
            work_item_type_key=type_key,
            search_group=search_group,
            page_num=page_num,
            page_size=page_size,
            fields=fields_to_fetch if fields_to_fetch else None,
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
            "Retrieved %d items (total: %d)", len(items), pagination.get("total", 0)
        )

        # 如果指定了 related_to，进行客户端过滤
        # search_params API 不支持关联字段过滤
        if related_to:
            logger.info("Applying client-side related_to filter: %s", related_to)
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

    def clear_user_cache(self) -> None:
        """
        清理用户缓存

        当用户信息发生变化时调用此方法
        """
        self._user_cache.clear()
        logger.info("Cleared user cache")

    def clear_work_item_cache(self) -> None:
        """
        清理工作项缓存

        当工作项信息发生变化时调用此方法
        """
        self._work_item_cache.clear()
        logger.info("Cleared work item cache")

    def clear_all_caches(self) -> None:
        """
        清理所有缓存
        """
        self._user_cache.clear()
        self._work_item_cache.clear()
        logger.info("Cleared all caches (user + work_item)")

    def invalidate_work_item_cache(self, work_item_id: int) -> None:
        """
        使特定工作项的缓存失效

        当工作项更新时调用此方法

        Args:
            work_item_id: 工作项 ID
        """
        key = str(work_item_id)
        if self._work_item_cache.delete(key):
            logger.info("Invalidated work item cache for ID: %d", work_item_id)
        else:
            logger.debug("Work item cache not found for ID: %d", work_item_id)

    def invalidate_user_cache(self, user_key: str) -> None:
        """
        使特定用户的缓存失效

        当用户信息更新时调用此方法

        Args:
            user_key: 用户 Key
        """
        if self._user_cache.delete(user_key):
            logger.info("Invalidated user cache for key: %s", user_key)
        else:
            logger.debug("User cache not found for key: %s", user_key)
