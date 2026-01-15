#!/usr/bin/env python3
"""
测试search_group结构
"""

import pytest

from src.providers.project.work_item_provider import WorkItemProvider


@pytest.mark.asyncio
async def test_search_group_structure():
    """测试search_group结构"""
    provider = WorkItemProvider(work_item_type_name="Issue管理")

    # 模拟conditions
    conditions = [{"field_key": "priority", "operator": "IN", "value": ["option_1"]}]

    # 测试两种构建方式
    print("=== 测试search_group结构 ===")

    # 旧方式
    old_structure = {"conjunction": "AND", "conditions": conditions}
    print(f"旧结构: {old_structure}")

    # 新方式
    new_structure = {
        "conjunction": "AND",
        "search_params": conditions,
        "search_groups": [],
    }
    print(f"新结构: {new_structure}")

    # 检查当前代码中的结构
    print("\n=== 检查当前代码 ===")

    # 获取项目和类型key
    project_key = await provider._get_project_key()
    type_key = await provider._get_type_key()

    print(f"项目Key: {project_key[:20]}...")
    print(f"类型Key: {type_key}")

    # 测试构建search_group
    test_conditions = []

    # 解析优先级
    try:
        field_key = await provider.meta.get_field_key(project_key, type_key, "priority")
        option_val = await provider._resolve_field_value(
            project_key, type_key, field_key, "P0"
        )

        test_conditions.append(
            {"field_key": field_key, "operator": "IN", "value": [option_val]}
        )

        # 当前代码构建的search_group
        current_search_group = {
            "conjunction": "AND",
            "search_params": test_conditions,
            "search_groups": [],
        }

        print(f"\n当前代码构建的search_group: {current_search_group}")

        # 直接调用API测试
        print("\n=== 直接API调用测试 ===")
        result = await provider.api.search_params(
            project_key=project_key,
            work_item_type_key=type_key,
            search_group=current_search_group,
            page_num=1,
            page_size=2,
        )

        print(f"API响应类型: {type(result)}")
        if isinstance(result, dict):
            items = result.get("work_items", [])
            print(f"返回工作项数量: {len(items)}")
            if items:
                print(f"第一个工作项keys: {list(items[0].keys())}")

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback

        traceback.print_exc()
