'''
Author: wulnut carepdime@gmail.com
Date: 2026-01-12 20:38:35
LastEditors: wulnut carepdime@gmail.com
LastEditTime: 2026-01-12 20:42:25
FilePath: /feishu_agent/scripts/project_space/get_projects_details_api.py
Description: get projects from feishu project api
Usage:
    uv run scripts/project_space/get_projects_details_api.py

    This script will get the list of projects from the Feishu Project API.
    It will print the list of projects to the console.

    The script will use the .env file to get the token and user key.
    The script will use the project client to get the list of projects.
    The script will print the list of projects to the console.
'''

import asyncio
import httpx
import json
import logging
import os
import sys

# 将项目根目录添加到 Python 路径，确保能找到 src 目录
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import settings
from src.core.project_client import get_project_client

# 1. 配置日志到控制台，方便你看到授权过程
logging.basicConfig(
    level=settings.get_log_level(),
    format="%(levelname)s: %(message)s",
    stream=sys.stdout,
)


async def main():
    """
    演示如何直接调用飞书项目接口
    """
    # 2. 获取已经封装好的客户端 (单例)
    # 它会自动读取 .env 并处理 Token 续期
    client = get_project_client()

    # 打印配置信息（调试用）
    print(f"FEISHU_PROJECT_USER_KEY 已设置: {bool(settings.FEISHU_PROJECT_USER_KEY)}")
    print(f"FEISHU_PROJECT_PLUGIN_ID 已设置: {bool(settings.FEISHU_PROJECT_PLUGIN_ID)}")

    print("\n--- 正在调用 API ---")

    # 示例 A: 获取“空间详情” (POST /open_api/projects/detail)
    # 这是一个通用的获取项目列表的接口
    projects_url = "/open_api/projects/detail"
    projects_payload = {
        "user_key": settings.FEISHU_PROJECT_USER_KEY,
        "project_keys": [""],
        "simple_names": [""],
    }

    try:
        # 直接发送 POST 请求
        # 注意：路径使用相对路径即可，Base URL 已经配置好了
        response = await client.post(projects_url, json=projects_payload)

        # 检查 HTTP 状态码
        response.raise_for_status()

        # 解析返回的 JSON
        data = response.json()

        print(f"\n[状态码]: {response.status_code}")
        print("[返回结果]:")
        print(json.dumps(data, indent=2, ensure_ascii=False))

    except httpx.HTTPStatusError as e:
        print(f"\n[调用失败]: {e}")
        print(f"[响应体]: {e.response.text}")
    except Exception as e:
        print(f"\n[调用失败]: {e}")


if __name__ == "__main__":
    # 使用 asyncio 运行异步主函数
    asyncio.run(main())