#!/usr/bin/env python3
"""
测试provider.get_tasks方法
"""

import json
import pytest

from src.providers.project.work_item_provider import WorkItemProvider


@pytest.mark.asyncio
async def test_provider_tasks():
    """测试provider.get_tasks方法"""
    provider = WorkItemProvider(work_item_type_name="Issue管理")

    print("=== 测试provider.get_tasks方法 ===")

    print("\n1. 查询优先级为P0的工作项:")
    try:
        result = await provider.get_tasks(priority=["P0"], page_size=2)

        print(f"结果类型: {type(result)}")
        print(f"总数量: {result.get('total')}")
        print(f"工作项数量: {len(result.get('items', []))}")

        items = result.get("items", [])
        for i, item in enumerate(items):
            print(f"\n工作项 {i + 1}:")
            print(f"  ID: {item.get('id')}")
            print(f"  名称: {item.get('name')}")
            print(f"  优先级: {item.get('priority')}")
            print(f"  状态: {item.get('status')}")
            print(f"  负责人: {item.get('owner')}")

            # 获取原始数据
            if item.get("id"):
                try:
                    # 从provider获取原始数据
                    raw_result = await provider.get_tasks(priority=["P0"], page_size=2)
                    # 但我们需要原始API响应...
                    # 直接调用API来获取
                    project_key = await provider._get_project_key()
                    type_key = await provider._get_type_key()

                    # 构建条件
                    conditions = []
                    field_key = await provider.meta.get_field_key(
                        project_key, type_key, "priority"
                    )
                    option_val = await provider._resolve_field_value(
                        project_key, type_key, field_key, "P0"
                    )

                    conditions.append(
                        {
                            "field_key": field_key,
                            "operator": "IN",
                            "value": [option_val],
                        }
                    )

                    search_group = {
                        "conjunction": "AND",
                        "search_params": conditions,
                        "search_groups": [],
                    }

                    raw_api_result = await provider.api.search_params(
                        project_key=project_key,
                        work_item_type_key=type_key,
                        search_group=search_group,
                        page_num=1,
                        page_size=2,
                        fields=[field_key, "owner"],
                    )

                    print(f"  API原始响应类型: {type(raw_api_result)}")
                    if isinstance(raw_api_result, dict):
                        raw_items = raw_api_result.get("work_items", [])
                    else:
                        raw_items = raw_api_result

                    # 找到对应的工作项
                    for raw_item in raw_items:
                        if raw_item.get("id") == item["id"]:
                            print(
                                f"  原始数据字段数: {len(raw_item.get('fields', []))}"
                            )
                            for field in raw_item.get("fields", []):
                                if field.get("field_key") == "priority":
                                    print(f"  原始优先级字段: {field}")
                                    print(
                                        f"  提取的优先级: {provider._extract_field_value(raw_item, 'priority')}"
                                    )
                            break

                except Exception as e:
                    print(f"  获取原始数据失败: {e}")

    except Exception as e:
        print(f"查询失败: {e}")
        import traceback

        traceback.print_exc()

    print("\n2. 测试简化方法:")
    # 使用从API测试得到的模拟数据
    test_raw_item = {
        "id": 6696527960,
        "name": "测试工作项",
        "fields": [
            {
                "field_key": "priority",
                "field_value": {"value": "option_2", "label": "P1"},
                "field_type_key": "select",
                "field_alias": "priority",
            },
            {
                "field_key": "owner",
                "field_value": "7368514917881757697",
                "field_type_key": "user",
                "field_alias": "owner",
            },
        ],
    }

    simplified = await provider.simplify_work_item(test_raw_item)
    print(f"简化结果: {simplified}")

    # 测试提取
    priority = provider._extract_field_value(test_raw_item, "priority")
    print(f"提取的优先级: {priority}")
