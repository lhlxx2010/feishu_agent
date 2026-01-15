#!/usr/bin/env python3
"""
测试字段提取
"""

import pytest

from src.providers.project.work_item_provider import WorkItemProvider


@pytest.mark.asyncio
async def test_field_extraction():
    """测试字段提取"""
    provider = WorkItemProvider(work_item_type_name="Issue管理")

    print("=== 测试字段提取 ===")

    # 测试数据1: fields数组格式（新格式）
    test_item_new = {
        "id": 12345,
        "name": "测试工作项",
        "fields": [
            {
                "field_key": "priority",
                "field_value": {"label": "P0", "value": "option_1"},
                "field_type_key": "select",
            },
            {"field_key": "owner", "field_value": "user_123", "field_type_key": "user"},
            {
                "field_key": "status",
                "field_value": {"label": "进行中", "value": "option_2"},
                "field_type_key": "select",
            },
        ],
    }

    # 测试数据2: field_value_pairs格式（旧格式）
    test_item_old = {
        "id": 12346,
        "name": "测试工作项2",
        "field_value_pairs": [
            {
                "field_key": "priority",
                "field_value": {"label": "P1", "value": "option_2"},
            },
            {"field_key": "owner", "field_value": "user_456"},
        ],
    }

    # 测试数据3: 实际API响应格式（从详细视图）
    # 基于之前看到的实际数据
    test_item_realistic = {
        "id": 6696527960,
        "name": "测试工作项",
        "fields": [
            {
                "field_type_key": "select",
                "field_alias": "priority",
                "field_key": "priority",
                "field_value": {"label": "P1", "value": "option_2"},
            }
        ],
    }

    print("\n1. 测试新格式字段提取:")
    priority = provider._extract_field_value(test_item_new, "priority")
    owner = provider._extract_field_value(test_item_new, "owner")
    status = provider._extract_field_value(test_item_new, "status")

    print(f"   优先级: {priority} (期望: 'P0')")
    print(f"   负责人: {owner} (期望: 'user_123')")
    print(f"   状态: {status} (期望: '进行中')")

    print("\n2. 测试旧格式字段提取:")
    priority2 = provider._extract_field_value(test_item_old, "priority")
    owner2 = provider._extract_field_value(test_item_old, "owner")

    print(f"   优先级: {priority2} (期望: 'P1')")
    print(f"   负责人: {owner2} (期望: 'user_456')")

    print("\n3. 测试实际API格式字段提取:")
    priority3 = provider._extract_field_value(test_item_realistic, "priority")
    print(f"   优先级: {priority3} (期望: 'P1')")

    # 测试字段不存在的情况
    print("\n4. 测试不存在的字段:")
    nonexistent = provider._extract_field_value(test_item_new, "nonexistent_field")
    print(f"   不存在的字段: {nonexistent} (期望: None)")

    # 测试实际API调用
    print("\n=== 测试实际API调用 ===")
    try:
        # 获取一个已知的工作项详情
        issue_id = 6696527960
        print(f"获取工作项 {issue_id} 的详情...")
        detail = await provider.get_issue_details(issue_id)

        print(f"工作项名称: {detail.get('name')}")
        print(f"字段数量: {len(detail.get('fields', []))}")

        # 提取优先级
        extracted_priority = provider._extract_field_value(detail, "priority")
        print(f"提取的优先级: {extracted_priority}")

        # 查找priority字段
        for field in detail.get("fields", []):
            if field.get("field_key") == "priority":
                print(f"原始优先级字段: {field}")
                break

    except Exception as e:
        print(f"API调用失败: {e}")
        import traceback

        traceback.print_exc()
