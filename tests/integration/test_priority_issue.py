#!/usr/bin/env python3
"""
测试优先级字段提取问题
"""

import logging
import pytest

from src.core.config import settings
from src.providers.project.work_item_provider import WorkItemProvider

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_priority_extraction():
    """测试优先级字段提取"""
    print("=== 测试优先级字段提取 ===")

    # 创建provider
    provider = WorkItemProvider(work_item_type_name="Issue管理")

    print("\n1. 测试优先级为P0的工作项查询...")
    try:
        result = await provider.get_tasks(priority=["P0"], page_size=2)

        print(f"查询结果: {len(result.get('items', []))} 个工作项")
        print(f"总数量: {result.get('total', 0)}")

        for i, item in enumerate(result.get("items", [])):
            print(f"\n工作项 {i + 1}:")
            print(f"  ID: {item.get('id')}")
            print(f"  名称: {item.get('name')}")
            print(f"  优先级: {item.get('priority')}")
            print(f"  状态: {item.get('status')}")
            print(f"  负责人: {item.get('owner')}")

            # 获取原始数据
            if item.get("id"):
                try:
                    detail = await provider.get_issue_details(item["id"])
                    print(
                        f"  原始数据优先级字段: {provider._extract_field_value(detail, 'priority')}"
                    )

                    # 检查fields结构
                    if "fields" in detail:
                        for field in detail["fields"]:
                            if field.get("field_key") == "priority":
                                print(f"  优先级字段详情: {field}")
                except Exception as e:
                    print(f"  获取详情失败: {e}")

    except Exception as e:
        print(f"查询失败: {e}")
        import traceback

        traceback.print_exc()

    print("\n2. 测试_extract_field_value方法...")
    # 模拟一个工作项数据
    test_item = {
        "id": 12345,
        "name": "测试工作项",
        "fields": [
            {
                "field_key": "priority",
                "field_value": {"label": "P0", "value": "option_1"},
                "field_type_key": "select",
            }
        ],
    }

    priority_value = provider._extract_field_value(test_item, "priority")
    print(f"测试提取优先级: {priority_value} (期望: 'P0')")

    # 测试另一个结构
    test_item2 = {
        "id": 12346,
        "name": "测试工作项2",
        "field_value_pairs": [
            {
                "field_key": "priority",
                "field_value": {"label": "P1", "value": "option_2"},
            }
        ],
    }

    priority_value2 = provider._extract_field_value(test_item2, "priority")
    print(f"测试提取优先级(旧格式): {priority_value2} (期望: 'P1')")


@pytest.mark.asyncio
async def test_search_params_structure():
    """测试search_params API调用结构"""
    print("\n=== 测试search_params API结构 ===")

    provider = WorkItemProvider(work_item_type_name="Issue管理")

    # 获取项目和类型key
    project_key = await provider._get_project_key()
    type_key = await provider._get_type_key()

    print(f"项目Key: {project_key}")
    print(f"类型Key: {type_key}")

    # 构建search_group
    conditions = []

    # 解析优先级
    field_key = await provider.meta.get_field_key(project_key, type_key, "priority")
    option_val = await provider._resolve_field_value(
        project_key, type_key, field_key, "P0"
    )

    conditions.append({"field_key": field_key, "operator": "IN", "value": [option_val]})

    # 构建search_group
    search_group = {
        "conjunction": "AND",
        "search_params": conditions,
        "search_groups": [],
    }

    print(f"构建的search_group: {search_group}")

    # 直接调用API
    try:
        result = await provider.api.search_params(
            project_key=project_key,
            work_item_type_key=type_key,
            search_group=search_group,
            page_num=1,
            page_size=2,
            fields=["priority", "status", "owner"],
        )

        print(f"API响应类型: {type(result)}")
        if isinstance(result, dict):
            print(f"工作项数量: {len(result.get('work_items', []))}")
            print(f"总数量: {result.get('total', 0)}")

            if result.get("work_items"):
                item = result["work_items"][0]
                print(f"第一个工作项keys: {list(item.keys())}")
                if "fields" in item:
                    print(f"第一个工作项fields数量: {len(item.get('fields', []))}")
                    for field in item.get("fields", []):
                        if field.get("field_key") == "priority":
                            print(f"优先级字段: {field}")
        else:
            print(f"响应内容: {result}")

    except Exception as e:
        print(f"API调用失败: {e}")
        import traceback

        traceback.print_exc()
