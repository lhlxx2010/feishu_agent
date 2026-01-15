"""
MetadataManager - 级联缓存管理器

实现零硬编码原则，提供 Name -> Key 的多级映射能力。

缓存层级:
- L1: Project Name -> Project Key
- L2: Work Item Type Name -> Type Key
- L3: Field Name/Alias -> Field Key
- L4: Option Label -> Option Value
- L-User: User Name/Email -> User Key

使用示例:
    manager = MetadataManager.get_instance()

    # 获取项目 Key
    project_key = await manager.get_project_key("Project Management")

    # 获取工作项类型 Key
    type_key = await manager.get_type_key(project_key, "Issue")

    # 获取字段 Key
    field_key = await manager.get_field_key(project_key, type_key, "优先级")

    # 获取选项 Value
    option_value = await manager.get_option_value(project_key, type_key, field_key, "P0")
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any

from src.providers.project.api import ProjectAPI, MetadataAPI, FieldAPI, UserAPI

logger = logging.getLogger(__name__)


class MetadataManager:
    """
    级联缓存管理器 (Manager Layer)

    核心职责:
    1. 动态解析: Name/Label -> Key/Value
    2. 级联缓存: 多级缓存避免重复 API 调用
    3. 解耦: 上层业务无需关心 UUID 细节

    设计原则:
    - 基于原子 API 类，不直接调用 HTTP 接口
    - 支持单例模式，全局共享缓存
    - 异步优先，所有方法均为 async
    """

    _instance: Optional["MetadataManager"] = None

    # 缓存过期时间（秒）
    PROJECT_TTL = 3600  # 1小时
    TYPE_TTL = 1800  # 30分钟
    FIELD_TTL = 1800  # 30分钟
    USER_TTL = 1800  # 30分钟

    def __init__(
        self,
        project_api: Optional[ProjectAPI] = None,
        metadata_api: Optional[MetadataAPI] = None,
        field_api: Optional[FieldAPI] = None,
        user_api: Optional[UserAPI] = None,
    ):
        """
        初始化 MetadataManager

        Args:
            project_api: ProjectAPI 实例（可选，默认自动创建）
            metadata_api: MetadataAPI 实例（可选，默认自动创建）
            field_api: FieldAPI 实例（可选，默认自动创建）
            user_api: UserAPI 实例（可选，默认自动创建）
        """
        self.project_api = project_api or ProjectAPI()
        self.metadata_api = metadata_api or MetadataAPI()
        self.field_api = field_api or FieldAPI()
        self.user_api = user_api or UserAPI()

        # 缓存并发控制锁
        self._cache_lock = asyncio.Lock()  # 用于 field 和 option 缓存
        self._project_lock = asyncio.Lock()  # 用于 project 缓存
        self._type_lock = asyncio.Lock()  # 用于 type 缓存
        self._user_lock = asyncio.Lock()  # 用于 user 缓存

        # 缓存大小限制
        self._max_project_cache_size = 50
        self._max_type_cache_size = 100
        self._max_field_cache_size = 200
        self._max_option_cache_size = 500
        self._max_user_cache_size = 200

        # L1: Project Name -> Project Key
        self._project_cache: Dict[str, str] = {}

        # L2: project_key -> {type_name -> type_key}
        self._type_cache: Dict[str, Dict[str, str]] = {}

        # L3: project_key -> type_key -> {field_name -> field_key}
        self._field_cache: Dict[str, Dict[str, Dict[str, str]]] = {}

        # L4: project_key -> type_key -> field_key -> {label -> value}
        self._option_cache: Dict[str, Dict[str, Dict[str, Dict[str, str]]]] = {}

        # L5: project_key -> type_key -> {role_name -> role_key} (角色名称映射)
        # 例如: {"67dc...": {"670f...": {"报告人": "role_cc5cef", "经办人": "role_a06e00"}}}
        self._role_cache: Dict[str, Dict[str, Dict[str, str]]] = {}

        # L-User: identifier (name/email) -> user_key
        self._user_cache: Dict[str, str] = {}

        # 缓存最后加载时间戳
        self._project_last_loaded: Optional[float] = None
        self._type_last_loaded: Dict[str, float] = {}
        self._field_last_loaded: Dict[str, Dict[str, float]] = {}
        self._user_last_loaded: Optional[float] = None

    @classmethod
    def get_instance(cls) -> "MetadataManager":
        """获取全局单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（主要用于测试）"""
        cls._instance = None

    def clear_cache(self) -> None:
        """清空所有缓存"""
        self._project_cache.clear()
        self._type_cache.clear()
        self._field_cache.clear()
        self._option_cache.clear()
        self._role_cache.clear()
        self._user_cache.clear()
        self._project_last_loaded = None
        self._type_last_loaded.clear()
        self._field_last_loaded.clear()
        self._user_last_loaded = None
        logger.debug("MetadataManager cache cleared")

    def _is_cache_expired(self, last_loaded: Optional[float], ttl: int) -> bool:
        """
        检查缓存是否过期

        Args:
            last_loaded: 最后加载时间戳（秒），None 表示未加载
            ttl: 缓存有效期（秒）

        Returns:
            True 表示过期或未加载
        """
        if last_loaded is None:
            return True
        import time

        return time.time() - last_loaded > ttl

    # ========== L1: Project ==========

    async def get_project_key(self, project_name: str) -> str:
        """
        根据项目名称获取 Project Key

        Args:
            project_name: 项目空间名称（如 "Project Management"）

        Returns:
            项目空间 Key

        Raises:
            Exception: 项目未找到时抛出异常
        """
        import time

        # 第一重检查 (无锁，快速路径)
        if project_name in self._project_cache:
            # 检查缓存是否过期
            if not self._is_cache_expired(self._project_last_loaded, self.PROJECT_TTL):
                logger.debug(f"Cache hit: project_name='{project_name}'")
                return self._project_cache[project_name]
            # 缓存过期，继续执行加载逻辑

        # 第二重检查 (加锁，防止竞态条件)
        async with self._project_lock:
            # 检查缓存过期，如果过期则清空缓存
            if self._is_cache_expired(self._project_last_loaded, self.PROJECT_TTL):
                self._project_cache.clear()
                self._project_last_loaded = None

            # 在锁内再次检查，避免重复加载
            if project_name in self._project_cache:
                return self._project_cache[project_name]

            # 调用 API 获取项目列表
            project_keys = await self.project_api.list_projects()
            if not project_keys:
                raise Exception("未找到任何项目空间")

            # 获取项目详情
            projects = await self.project_api.get_project_details(project_keys)

            # 验证返回类型，防止 List/Dict 不匹配
            if not isinstance(projects, dict):
                logger.warning(f"Unexpected project details format: {type(projects)}")
                if isinstance(projects, list):
                    # 尝试做一下兼容转换，假设 List 元素包含 Key
                    temp_map = {}
                    for p in projects:
                        if isinstance(p, dict) and "project_key" in p:
                            temp_map[p["project_key"]] = p
                    projects = temp_map
                else:
                    projects = {}

            # 填充缓存前检查大小，如果超过限制则清理最旧的条目
            if len(self._project_cache) >= self._max_project_cache_size:
                # 移除第一个条目（近似LRU）
                keys = list(self._project_cache.keys())
                if keys:
                    oldest_key = keys[0]
                    del self._project_cache[oldest_key]
                    logger.debug(
                        f"Project cache size limit reached, removed oldest entry: {oldest_key}"
                    )

            # 填充缓存
            for key, info in projects.items():
                if isinstance(info, dict):
                    name = info.get("name")
                    if name:
                        self._project_cache[name] = key
                        logger.debug(
                            f"Cache set: project_name='{name}' -> project_key='{key}'"
                        )

            # 更新最后加载时间戳
            self._project_last_loaded = time.time()

            # 返回目标项目
            if project_name in self._project_cache:
                return self._project_cache[project_name]

            raise Exception(f"项目空间 '{project_name}' 未找到")

    async def list_projects(self) -> Dict[str, str]:
        """
        获取所有项目的 Name -> Key 映射

        Returns:
            {project_name: project_key} 字典
        """
        import time

        # 如果缓存已有数据，检查是否过期
        if self._project_cache:
            if not self._is_cache_expired(self._project_last_loaded, self.PROJECT_TTL):
                logger.debug("Cache hit: project_cache already populated")
                return self._project_cache.copy()
            # 缓存过期，继续执行加载逻辑

        async with self._project_lock:
            # 检查缓存过期，如果过期则清空缓存
            if self._is_cache_expired(self._project_last_loaded, self.PROJECT_TTL):
                self._project_cache.clear()
                self._project_last_loaded = None

            # 在锁内再次检查，避免重复加载
            if self._project_cache:
                return self._project_cache.copy()

            project_keys = await self.project_api.list_projects()
            if not project_keys:
                return {}

            projects = await self.project_api.get_project_details(project_keys)

            if not isinstance(projects, dict):
                # 简单防卫，不尝试复杂转换
                logger.warning(
                    f"Unexpected project details format in list_projects: {type(projects)}"
                )
                return {}

            for key, info in projects.items():
                if isinstance(info, dict):
                    name = info.get("name")
                    if name:
                        self._project_cache[name] = key

            # 更新最后加载时间戳
            self._project_last_loaded = time.time()

            return self._project_cache.copy()

    # ========== L2: Work Item Type ==========

    async def get_type_key(self, project_key: str, type_name: str) -> str:
        """
        根据类型名称获取 Work Item Type Key

        Args:
            project_key: 项目空间 Key
            type_name: 工作项类型名称（如 "Issue", "需求", "任务"）

        Returns:
            工作项类型 Key

        Raises:
            Exception: 类型未找到时抛出异常
        """
        import time

        # 第一重检查 (无锁，快速路径)
        if (
            project_key in self._type_cache
            and type_name in self._type_cache[project_key]
        ):
            # 检查缓存是否过期
            last_loaded = self._type_last_loaded.get(project_key)
            if not self._is_cache_expired(last_loaded, self.TYPE_TTL):
                logger.debug(f"Cache hit: type_name='{type_name}'")
                return self._type_cache[project_key][type_name]
            # 缓存过期，继续执行加载逻辑

        # 第二重检查 (加锁，防止竞态条件)
        async with self._type_lock:
            # 检查缓存过期，如果过期则清空该项目的类型缓存
            last_loaded = self._type_last_loaded.get(project_key)
            if self._is_cache_expired(last_loaded, self.TYPE_TTL):
                if project_key in self._type_cache:
                    self._type_cache[project_key].clear()
                self._type_last_loaded.pop(project_key, None)

            # 初始化缓存结构
            if project_key not in self._type_cache:
                self._type_cache[project_key] = {}

            # 在锁内再次检查，避免重复加载
            if type_name in self._type_cache[project_key]:
                return self._type_cache[project_key][type_name]

            # 调用 API 获取类型列表
            types = await self.metadata_api.get_work_item_types(project_key)

            # 填充缓存
            for t in types:
                t_name = t.get("name")
                t_key = t.get("type_key")
                if t_name and t_key:
                    self._type_cache[project_key][t_name] = t_key
                    logger.debug(
                        f"Cache set: type_name='{t_name}' -> type_key='{t_key}'"
                    )

            # 更新最后加载时间戳
            self._type_last_loaded[project_key] = time.time()

            # 返回目标类型
            if type_name in self._type_cache[project_key]:
                return self._type_cache[project_key][type_name]

            available_types = list(self._type_cache[project_key].keys())
            raise Exception(
                f"工作项类型 '{type_name}' 未找到。可用类型: {available_types}"
            )

    async def list_types(self, project_key: str) -> Dict[str, str]:
        """
        获取项目下所有工作项类型的 Name -> Key 映射

        Args:
            project_key: 项目空间 Key

        Returns:
            {type_name: type_key} 字典
        """
        import time

        # 快速路径：缓存已存在数据
        if project_key in self._type_cache and self._type_cache[project_key]:
            # 检查缓存是否过期
            last_loaded = self._type_last_loaded.get(project_key)
            if not self._is_cache_expired(last_loaded, self.TYPE_TTL):
                logger.debug(
                    f"Cache hit: type_cache already populated for project {project_key}"
                )
                return self._type_cache[project_key].copy()
            # 缓存过期，继续执行加载逻辑

        async with self._type_lock:
            # 检查缓存过期，如果过期则清空该项目的类型缓存
            last_loaded = self._type_last_loaded.get(project_key)
            if self._is_cache_expired(last_loaded, self.TYPE_TTL):
                if project_key in self._type_cache:
                    self._type_cache[project_key].clear()
                self._type_last_loaded.pop(project_key, None)

            # 初始化缓存结构
            if project_key not in self._type_cache:
                self._type_cache[project_key] = {}

            # 在锁内再次检查，避免重复加载
            if self._type_cache[project_key]:
                return self._type_cache[project_key].copy()

            types = await self.metadata_api.get_work_item_types(project_key)

            for t in types:
                t_name = t.get("name")
                t_key = t.get("type_key")
                if t_name and t_key:
                    self._type_cache[project_key][t_name] = t_key

            # 更新最后加载时间戳
            self._type_last_loaded[project_key] = time.time()

            return self._type_cache[project_key].copy()

    # ========== L3: Field ==========

    async def _ensure_field_cache(self, project_key: str, type_key: str) -> None:
        """
        确保字段和选项缓存已加载

        Args:
            project_key: 项目空间 Key
            type_key: 工作项类型 Key
        """
        import time

        # 第一重检查 (无锁，快速路径)
        if (
            project_key in self._field_cache
            and type_key in self._field_cache[project_key]
        ):
            # 检查缓存是否过期
            last_loaded = self._field_last_loaded.get(project_key, {}).get(type_key)
            if not self._is_cache_expired(last_loaded, self.FIELD_TTL):
                return
            # 缓存过期，继续执行加载逻辑

        # 第二重检查 (加锁，防止竞态条件)
        async with self._cache_lock:
            # 检查缓存过期，如果过期则清空该项目的字段缓存
            last_loaded = self._field_last_loaded.get(project_key, {}).get(type_key)
            if self._is_cache_expired(last_loaded, self.FIELD_TTL):
                if (
                    project_key in self._field_cache
                    and type_key in self._field_cache[project_key]
                ):
                    del self._field_cache[project_key][type_key]
                if (
                    project_key in self._option_cache
                    and type_key in self._option_cache[project_key]
                ):
                    del self._option_cache[project_key][type_key]
                if (
                    project_key in self._field_last_loaded
                    and type_key in self._field_last_loaded[project_key]
                ):
                    del self._field_last_loaded[project_key][type_key]

            # 在锁内再次检查，避免重复加载
            if project_key not in self._field_cache:
                self._field_cache[project_key] = {}
                self._option_cache[project_key] = {}

            if type_key in self._field_cache[project_key]:
                return

            # 准备临时字典
            temp_field_map = {}
            temp_option_map = {}
            temp_role_map = {}

            # 调用 API 获取字段列表
            fields = await self.field_api.get_all_fields(project_key, type_key)

            for f in fields:
                f_name = f.get("field_name")
                f_key = f.get("field_key")
                f_alias = f.get("field_alias")

                if f_name and f_key:
                    # 存储 field_name -> field_key
                    temp_field_map[f_name] = f_key

                    # 也存储 alias -> field_key
                    if f_alias:
                        temp_field_map[f_alias] = f_key

                    logger.debug(
                        f"Cache set: field_name='{f_name}' -> field_key='{f_key}'"
                    )

                # 缓存选项
                options = f.get("options", [])
                if options and f_key:
                    temp_option_map[f_key] = {}
                    for opt in options:
                        label = opt.get("label")
                        value = opt.get("value")
                        if label and value:
                            temp_option_map[f_key][label] = value

                # 解析角色缓存: 从 current_status_operator_role 字段的 options 中提取
                # options 格式: [{"label": "经办人", "value": "role_xxx_role_a06e00"}, ...]
                if f_key == "current_status_operator_role" and options:
                    for opt in options:
                        label = opt.get("label")  # 如 "经办人", "报告人"
                        value = opt.get("value")  # 如 "role_xxx_670f_role_a06e00"
                        if label and value:
                            # 提取短 role_key
                            # "role_67dc..._670f..._role_a06e00" -> "role_a06e00"
                            parts = value.split("_")
                            if len(parts) >= 2 and parts[-2] == "role":
                                short_role_key = f"role_{parts[-1]}"
                            elif value.startswith("role_"):
                                short_role_key = value
                            else:
                                # 兜底: 使用完整的后缀部分
                                short_role_key = value.split("_")[-1]
                                if not short_role_key.startswith("role"):
                                    short_role_key = "role_" + short_role_key

                            temp_role_map[label] = short_role_key
                            logger.debug(
                                f"Cache set: role_name='{label}' -> role_key='{short_role_key}'"
                            )

            # 原子性更新缓存
            self._field_cache[project_key][type_key] = temp_field_map
            self._option_cache[project_key][type_key] = temp_option_map

            # 更新角色缓存
            if project_key not in self._role_cache:
                self._role_cache[project_key] = {}
            self._role_cache[project_key][type_key] = temp_role_map

            # 更新最后加载时间戳
            if project_key not in self._field_last_loaded:
                self._field_last_loaded[project_key] = {}
            self._field_last_loaded[project_key][type_key] = time.time()

    async def get_field_key(
        self, project_key: str, type_key: str, field_name: str
    ) -> str:
        """
        根据字段名称获取 Field Key

        Args:
            project_key: 项目空间 Key
            type_key: 工作项类型 Key
            field_name: 字段名称或别名（如 "优先级", "priority"）

        Returns:
            字段 Key

        Raises:
            Exception: 字段未找到时抛出异常
        """
        await self._ensure_field_cache(project_key, type_key)

        field_map = self._field_cache[project_key].get(type_key, {})

        # 1. 精确匹配名称或别名
        if field_name in field_map:
            logger.debug(f"Cache hit: field_name='{field_name}'")
            return field_map[field_name]

        # 2. 检查是否本身就是 Key
        if field_name in field_map.values():
            return field_name

        available_fields = list(field_map.keys())[:10]
        raise Exception(
            f"字段 '{field_name}' 未找到。可用字段 (前10个): {available_fields}"
        )

    async def list_fields(self, project_key: str, type_key: str) -> Dict[str, str]:
        """
        获取工作项类型下所有字段的 Name -> Key 映射

        Args:
            project_key: 项目空间 Key
            type_key: 工作项类型 Key

        Returns:
            {field_name: field_key} 字典
        """
        await self._ensure_field_cache(project_key, type_key)
        return self._field_cache[project_key].get(type_key, {}).copy()

    # ========== L4: Option ==========

    async def get_option_value(
        self, project_key: str, type_key: str, field_key: str, option_label: str
    ) -> str:
        """
        根据选项标签获取 Option Value

        Args:
            project_key: 项目空间 Key
            type_key: 工作项类型 Key
            field_key: 字段 Key
            option_label: 选项标签（如 "P0", "高优先级"）

        Returns:
            选项 Value

        Raises:
            Exception: 选项未找到时抛出异常
        """
        await self._ensure_field_cache(project_key, type_key)

        option_map = (
            self._option_cache.get(project_key, {}).get(type_key, {}).get(field_key, {})
        )

        # 1. 精确匹配标签
        if option_label in option_map:
            logger.debug(f"Cache hit: option_label='{option_label}'")
            return option_map[option_label]

        # 2. 检查是否本身就是 Value
        if option_label in option_map.values():
            return option_label

        available_options = list(option_map.keys())
        raise Exception(f"选项 '{option_label}' 未找到。可用选项: {available_options}")

    async def list_options(
        self, project_key: str, type_key: str, field_key: str
    ) -> Dict[str, str]:
        """
        获取字段下所有选项的 Label -> Value 映射

        Args:
            project_key: 项目空间 Key
            type_key: 工作项类型 Key
            field_key: 字段 Key

        Returns:
            {option_label: option_value} 字典
        """
        await self._ensure_field_cache(project_key, type_key)
        return (
            self._option_cache.get(project_key, {})
            .get(type_key, {})
            .get(field_key, {})
            .copy()
        )

    # ========== L5: Role ==========

    async def get_role_key(
        self, project_key: str, type_key: str, role_name: str
    ) -> str:
        """
        根据角色名称获取 Role Key

        Args:
            project_key: 项目空间 Key
            type_key: 工作项类型 Key
            role_name: 角色名称（如 "经办人", "报告人"）

        Returns:
            Role Key (如 "role_a06e00")

        Raises:
            Exception: 角色未找到时抛出异常
        """
        await self._ensure_field_cache(project_key, type_key)

        role_map = self._role_cache.get(project_key, {}).get(type_key, {})

        # 1. 精确匹配名称
        if role_name in role_map:
            logger.debug(f"Cache hit: role_name='{role_name}'")
            return role_map[role_name]

        # 2. 检查是否本身就是 Key
        if role_name in role_map.values():
            return role_name

        available_roles = list(role_map.keys())
        raise Exception(f"角色 '{role_name}' 未找到。可用角色: {available_roles}")

    async def get_role_name(
        self, project_key: str, type_key: str, role_key: str
    ) -> Optional[str]:
        """
        根据 Role Key 获取角色名称（反向查找）

        Args:
            project_key: 项目空间 Key
            type_key: 工作项类型 Key
            role_key: Role Key

        Returns:
            角色名称，未找到返回 None
        """
        await self._ensure_field_cache(project_key, type_key)

        role_map = self._role_cache.get(project_key, {}).get(type_key, {})

        # 1. 精确匹配优先
        for name, key in role_map.items():
            if key == role_key:
                return name

        # 2. 部分匹配 (作为备选)
        for name, key in role_map.items():
            if role_key and key in role_key:
                return name

        return None

    # ========== L-User: User ==========

    def _looks_like_user_key(self, identifier: str) -> bool:
        """
        判断标识符是否已经是 User Key 格式

        启发式规则:
        1. 以常见的前缀开头: "user_", "ou_", "usr_", "u_"
        2. 不包含空格和中文
        3. 长度适中 (5-100个字符)

        注意: 这不是精确验证，仅用于避免不必要的 API 调用
        """
        if not identifier or not isinstance(identifier, str):
            return False

        # 常见 user_key 前缀
        common_prefixes = {"user_", "ou_", "usr_", "u_"}
        if any(identifier.startswith(prefix) for prefix in common_prefixes):
            return True

        # 检查是否包含空格或中文字符
        if any(c.isspace() for c in identifier):
            return False

        # 检查是否包含中文字符（CJK统一表意文字）
        if any("\u4e00" <= c <= "\u9fff" for c in identifier):
            return False

        # 简单长度检查
        if 5 <= len(identifier) <= 100:
            # 假设 user_key 通常只包含字母、数字、下划线、连字符
            if all(c.isalnum() or c in "_-" for c in identifier):
                return True

        return False

    async def get_user_key(
        self, identifier: str, project_key: Optional[str] = None
    ) -> str:
        """
        根据用户标识获取 User Key

        Args:
            identifier: 用户标识（名称、邮箱等）
            project_key: 项目空间 Key（可选，用于限定搜索范围）

        Returns:
            用户 Key

        Raises:
            Exception: 用户未找到时抛出异常
        """
        import time

        # 第一重检查 (无锁，快速路径)
        if identifier in self._user_cache:
            # 检查缓存是否过期
            if not self._is_cache_expired(self._user_last_loaded, self.USER_TTL):
                logger.debug(f"Cache hit: user_identifier='{identifier}'")
                return self._user_cache[identifier]
            # 缓存过期，继续执行加载逻辑

        # 第二重检查 (加锁，防止竞态条件)
        async with self._user_lock:
            # 检查缓存过期，如果过期则清空用户缓存
            if self._is_cache_expired(self._user_last_loaded, self.USER_TTL):
                self._user_cache.clear()
                self._user_last_loaded = None

            # 在锁内再次检查，避免重复加载
            if identifier in self._user_cache:
                return self._user_cache[identifier]

            # 检查标识符是否已经是 User Key 格式
            if self._looks_like_user_key(identifier):
                logger.debug(
                    f"Identifier '{identifier}' appears to be a user_key, using directly"
                )
                self._user_cache[identifier] = identifier  # 自映射，便于后续快速查找
                return identifier

            # 调用 API 搜索用户
            users = await self.user_api.search_users(identifier, project_key)

            if not users:
                raise Exception(f"用户 '{identifier}' 未找到")

            # 填充缓存并返回第一个匹配
            for user in users:
                user_key = user.get("user_key")
                name = user.get("name_cn") or user.get("name_en")
                email = user.get("email")

                if user_key:
                    if name:
                        self._user_cache[name] = user_key
                    if email:
                        self._user_cache[email] = user_key

                    logger.debug(
                        f"Cache set: user='{name or email}' -> user_key='{user_key}'"
                    )

            # 更新最后加载时间戳
            self._user_last_loaded = time.time()

            # 检查是否找到目标用户
            if identifier in self._user_cache:
                return self._user_cache[identifier]

            # 返回第一个结果
            first_user = users[0]
            user_key = first_user.get("user_key")
            if user_key:
                self._user_cache[identifier] = user_key
                return user_key

            raise Exception(f"用户 '{identifier}' 未找到有效的 user_key")

    async def get_user_name(self, user_key: str) -> Optional[str]:
        """
        根据 User Key 获取用户名称（反向查找）

        Args:
            user_key: 用户 Key（如 "7446873861590728705"）

        Returns:
            用户名称（中文名优先），未找到时返回 None
        """
        if not user_key:
            return None

        # 检查反向缓存
        # 遍历 _user_cache 查找是否已有该 user_key 的名称
        for name, cached_key in self._user_cache.items():
            if cached_key == user_key:
                logger.debug(
                    f"Cache hit (reverse): user_key='{user_key}' -> name='{name}'"
                )
                return name

        # 调用 API 查询用户详情
        try:
            users = await self.user_api.query_users(user_keys=[user_key])
            if users:
                user = users[0]
                name = user.get("name_cn") or user.get("name_en") or user.get("name")
                if name:
                    # 缓存正向和反向映射
                    self._user_cache[name] = user_key
                    logger.debug(
                        f"Cache set (reverse): user_key='{user_key}' -> name='{name}'"
                    )
                    return name
        except Exception as e:
            logger.warning(f"Failed to get user name for key '{user_key}': {e}")

        return None

    async def batch_get_user_names(self, user_keys: List[str]) -> Dict[str, str]:
        """
        批量获取用户名称

        Args:
            user_keys: 用户 Key 列表

        Returns:
            {user_key: user_name} 字典，未找到的 key 不包含在结果中
        """
        result = {}
        keys_to_query = []

        # 先检查缓存
        for key in user_keys:
            if not key:
                continue
            found = False
            for name, cached_key in self._user_cache.items():
                if cached_key == key:
                    result[key] = name
                    found = True
                    break
            if not found:
                keys_to_query.append(key)

        # 批量查询未缓存的
        if keys_to_query:
            try:
                users = await self.user_api.query_users(user_keys=keys_to_query)
                for user in users:
                    key = user.get("user_key")
                    name = (
                        user.get("name_cn") or user.get("name_en") or user.get("name")
                    )
                    if key and name:
                        result[key] = name
                        self._user_cache[name] = key
                        logger.debug(
                            f"Cache set (batch): user_key='{key}' -> name='{name}'"
                        )
            except Exception as e:
                logger.warning(f"Failed to batch get user names: {e}")

        return result

    # ========== 高级方法: 级联解析 ==========

    async def resolve_field_value(
        self,
        project_name: str,
        type_name: str,
        field_name: str,
        value_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        级联解析字段值（便捷方法）

        从人类可读的名称一步到位解析为 API 所需的 Key/Value。

        Args:
            project_name: 项目空间名称
            type_name: 工作项类型名称
            field_name: 字段名称
            value_label: 选项标签（可选，仅对选项类型字段有效）

        Returns:
            {
                "project_key": "xxx",
                "type_key": "xxx",
                "field_key": "xxx",
                "option_value": "xxx"  # 仅当 value_label 提供时
            }

        示例:
            result = await manager.resolve_field_value(
                project_name="Project Management",
                type_name="Issue",
                field_name="优先级",
                value_label="P0"
            )
            # result = {
            #     "project_key": "project_xxx",
            #     "type_key": "670f3cdaddd89a6fa8f18e65",
            #     "field_key": "priority",
            #     "option_value": "option_1"
            # }
        """
        project_key = await self.get_project_key(project_name)
        type_key = await self.get_type_key(project_key, type_name)
        field_key = await self.get_field_key(project_key, type_key, field_name)

        result = {
            "project_key": project_key,
            "type_key": type_key,
            "field_key": field_key,
        }

        if value_label:
            option_value = await self.get_option_value(
                project_key, type_key, field_key, value_label
            )
            result["option_value"] = option_value

        return result
