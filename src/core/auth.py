"""
Author: liangyz liangyz@seirobotics.net
Date: 2026-01-12 17:56:08
LastEditors: liangyz liangyz@seirobotics.net
LastEditTime: 2026-01-12 18:59:27
FilePath: /feishu_agent/src/core/auth.py
"""

import logging
import time
from typing import Optional

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)


class AuthManager:
    def __init__(self):
        self._plugin_token: Optional[str] = None
        self._expiry_time: float = 0
        self.base_url = settings.FEISHU_PROJECT_BASE_URL

    async def get_plugin_token(self) -> Optional[str]:
        """
        Get a valid plugin token.
        Returns the manually configured token if present,
        otherwise fetches and caches a new one using plugin credentials.
        """
        # 1. Check if a static token is provided (backward compatibility)
        if settings.FEISHU_PROJECT_USER_TOKEN:
            return settings.FEISHU_PROJECT_USER_TOKEN

        # 2. Check if plugin credentials are provided
        if (
            not settings.FEISHU_PROJECT_PLUGIN_ID
            or not settings.FEISHU_PROJECT_PLUGIN_SECRET
        ):
            logger.error(
                "No Feishu Project authentication credentials found (Token or Plugin ID/Secret)"
            )
            return None

        # 3. Check cache
        if self._plugin_token and time.time() < self._expiry_time:
            return self._plugin_token

        # 4. Fetch new token from API
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/open_api/authen/plugin_token"
                payload = {
                    "plugin_id": settings.FEISHU_PROJECT_PLUGIN_ID,
                    "plugin_secret": settings.FEISHU_PROJECT_PLUGIN_SECRET,
                }
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

                # 调试：打印实际响应内容
                logger.debug(f"Plugin token API response: {data}")

                # 检查响应格式：可能是 {"code": 0, "data": {...}} 或直接返回 token
                code = data.get("code")
                if code is not None and code != 0:
                    logger.error(
                        f"Auth failed: {data.get('msg', 'Unknown error')} (code {code})"
                    )
                    logger.error(f"Full response data: {data}")
                    return None

                # The response structure based on common Lark patterns:
                # { "code": 0, "data": { "plugin_token": "...", "expire": 7200 } }
                # 或者直接返回: { "plugin_token": "...", "expire": 7200 }
                auth_data = data.get("data", data)
                self._plugin_token = auth_data.get("plugin_token")

                if not self._plugin_token:
                    logger.error(
                        f"Plugin token not found in response. Response structure: {data}"
                    )
                    return None

                # Buffer of 60 seconds
                expires_in = auth_data.get("expire", 7200)
                self._expiry_time = time.time() + expires_in - 60

                logger.info("Successfully refreshed Feishu Project plugin token")
                return self._plugin_token

        except Exception as e:
            logger.error(f"Error fetching plugin token: {e}")
            return None


# Singleton instance
auth_manager = AuthManager()
