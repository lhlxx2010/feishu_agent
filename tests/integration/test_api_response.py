#!/usr/bin/env python3
"""
测试API响应格式
"""

import json
import pytest

from src.providers.project.work_item_provider import WorkItemProvider
from src.core.project_client import get_project_client


@pytest.mark.asyncio
async def test_api_response():
    """测试API响应格式"""
    provider = WorkItemProvider(work_item_type_name="Issue管理")
    client = get_project_client()

    print("=== 测试API响应格式 ===")

    # 获取项目和类型key
    project_key = await provider._get_project_key()
    type_key = await provider._get_type_key()

    print(f"项目Key: {project_key[:20]}...")
    print(f"类型Key: {type_key}")

    # 构建search_group
    conditions = []

    # 解析优先级
    field_key = await provider.meta.get_field_key(project_key, type_key, "priority")
    option_val = await provider._resolve_field_value(
        project_key, type_key, field_key, "P0"
    )

    conditions.append({"field_key": field_key, "operator": "IN", "value": [option_val]})

    search_group = {
        "conjunction": "AND",
        "search_params": conditions,
        "search_groups": [],
    }

    print(f"\n搜索条件: {search_group}")

    # 测试1: 不带fields参数
    print("\n1. 测试不带fields参数:")
    url = f"/open_api/{project_key}/work_item/{type_key}/search/params"
    payload = {"search_group": search_group, "page_num": 1, "page_size": 2}

    try:
        response = await client.post(url, json=payload)
        print(f"响应状态: {response.status_code}")
        data = response.json()
        print(f"错误码: {data.get('err_code')}")
        print(f"错误信息: {data.get('err_msg')}")

        result = data.get("data", {})
        print(f"结果类型: {type(result)}")

        if isinstance(result, dict):
            items = result.get("work_items", [])
            print(f"工作项数量: {len(items)}")
            if items:
                item = items[0]
                print(f"第一个工作项keys: {list(item.keys())}")
                print(f"是否有'fields': {'fields' in item}")
                print(f"是否有'field_value_pairs': {'field_value_pairs' in item}")

                # 如果有fields，检查内容
                if "fields" in item and item["fields"]:
                    print(f"fields数量: {len(item['fields'])}")
                    # 查找priority字段
                    for field in item["fields"]:
                        if field.get("field_key") == "priority":
                            print(f"找到priority字段: {field}")
                            break
                    else:
                        print("未找到priority字段")
                else:
                    print("fields为空或不存在")
        elif isinstance(result, list):
            print(f"列表长度: {len(result)}")
            if result:
                print(f"第一个元素keys: {list(result[0].keys())}")

    except Exception as e:
        print(f"API调用失败: {e}")
        import traceback

        traceback.print_exc()

    # 测试2: 带fields参数
    print("\n\n2. 测试带fields参数:")
    fields = ["priority", "status", "owner"]
    field_keys = []
    for field_name in fields:
        try:
            f_key = await provider.meta.get_field_key(project_key, type_key, field_name)
            field_keys.append(f_key)
        except Exception as e:
            print(f"获取字段key '{field_name}' 失败: {e}")

    print(f"请求的字段keys: {field_keys}")

    payload_with_fields = {
        "search_group": search_group,
        "page_num": 1,
        "page_size": 2,
        "fields": field_keys,
    }

    try:
        response2 = await client.post(url, json=payload_with_fields)
        print(f"响应状态: {response2.status_code}")
        data2 = response2.json()
        print(f"错误码: {data2.get('err_code')}")
        print(f"错误信息: {data2.get('err_msg')}")

        result2 = data2.get("data", {})
        print(f"结果类型: {type(result2)}")

        if isinstance(result2, dict):
            items2 = result2.get("work_items", [])
            print(f"工作项数量: {len(items2)}")
            if items2:
                item2 = items2[0]
                print(f"第一个工作项keys: {list(item2.keys())}")

                # 检查响应
                print(
                    f"响应内容预览: {json.dumps(item2, ensure_ascii=False, indent=2)[:500]}..."
                )

        elif isinstance(result2, list):
            print(f"列表长度: {len(result2)}")
            if result2:
                print(
                    f"第一个元素预览: {json.dumps(result2[0], ensure_ascii=False, indent=2)[:500]}..."
                )

    except Exception as e:
        print(f"API调用失败: {e}")
        import traceback

        traceback.print_exc()
