"""
Pydantic 数据模型定义

用于:
1. MCP 工具的输入参数验证
2. API 响应的数据解析与清洗
3. 类型安全的数据传递
"""

from typing import List, Optional, Generic, TypeVar, Any, Dict
from pydantic import BaseModel, Field

T = TypeVar("T")


# ==================== 通用模型 ====================


class Pagination(BaseModel):
    """分页信息"""

    total: int = 0
    page_num: int = 1
    page_size: int = 20


class FieldOption(BaseModel):
    """字段选项"""

    label: str
    value: str


class FieldDefinition(BaseModel):
    """字段定义"""

    field_key: str
    field_name: str
    field_alias: Optional[str] = None
    field_type_key: str
    options: List[FieldOption] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


# ==================== 工作项模型 ====================


class WorkItem(BaseModel):
    """工作项"""

    id: int
    name: str
    project_key: str
    work_item_type_key: str
    template_id: Optional[int] = None
    field_value_pairs: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


class WorkItemListData(BaseModel):
    """工作项列表数据"""

    items: List[WorkItem] = Field(alias="data", default_factory=list)
    pagination: Optional[Pagination] = None


class BaseResponse(BaseModel, Generic[T]):
    """API 响应基类"""

    code: int
    msg: str = ""
    data: Optional[T] = None

    @property
    def is_success(self) -> bool:
        return self.code == 0


# ==================== MCP 工具输入模型 ====================


class CreateWorkItemInput(BaseModel):
    """
    创建工作项的输入参数

    用于 MCP 工具 `create_task` 的参数验证。
    """

    project_key: str = Field(
        ...,
        description="项目空间 Key，如 'project_xxx'",
    )
    name: str = Field(
        ...,
        description="工作项标题",
        min_length=1,
        max_length=500,
    )
    type_key: str = Field(
        default="task",
        description="工作项类型，可选值: task, bug, story",
    )
    priority: str = Field(
        default="P2",
        description="优先级，可选值: P0(最高), P1, P2, P3(最低)",
    )
    description: str = Field(
        default="",
        description="工作项描述",
    )
    assignee: Optional[str] = Field(
        default=None,
        description="负责人（姓名或邮箱）",
    )


class FilterWorkItemInput(BaseModel):
    """
    过滤工作项的输入参数

    用于 MCP 工具 `filter_tasks` 的参数验证。
    """

    project_key: str = Field(
        ...,
        description="项目空间 Key",
    )
    status: Optional[List[str]] = Field(
        default=None,
        description="状态列表，如 ['待处理', '进行中']",
    )
    priority: Optional[List[str]] = Field(
        default=None,
        description="优先级列表，如 ['P0', 'P1']",
    )
    owner: Optional[str] = Field(
        default=None,
        description="负责人（姓名或邮箱）",
    )
    page_num: int = Field(
        default=1,
        description="页码（从 1 开始）",
        ge=1,
    )
    page_size: int = Field(
        default=20,
        description="每页数量",
        ge=1,
        le=100,
    )


class UpdateWorkItemInput(BaseModel):
    """
    更新工作项的输入参数

    用于 MCP 工具 `update_task` 的参数验证。
    """

    project_key: str = Field(
        ...,
        description="项目空间 Key",
    )
    issue_id: int = Field(
        ...,
        description="工作项 ID",
    )
    name: Optional[str] = Field(
        default=None,
        description="新标题",
    )
    priority: Optional[str] = Field(
        default=None,
        description="新优先级",
    )
    description: Optional[str] = Field(
        default=None,
        description="新描述",
    )
    status: Optional[str] = Field(
        default=None,
        description="新状态",
    )
    assignee: Optional[str] = Field(
        default=None,
        description="新负责人",
    )


# ==================== MCP 工具输出模型 ====================


class WorkItemSummary(BaseModel):
    """
    工作项摘要（精简版）

    用于 MCP 工具返回，减少 Token 消耗。
    """

    id: int = Field(description="工作项 ID")
    name: str = Field(description="标题")
    status: Optional[str] = Field(default=None, description="状态")
    priority: Optional[str] = Field(default=None, description="优先级")
    owner: Optional[str] = Field(default=None, description="负责人")


class FilterResult(BaseModel):
    """
    过滤结果

    用于 MCP 工具返回。
    """

    items: List[WorkItemSummary] = Field(
        default_factory=list,
        description="工作项列表",
    )
    total: int = Field(description="总数")
    page_num: int = Field(description="当前页码")
    page_size: int = Field(description="每页数量")
