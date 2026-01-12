import logging
import time
import httpx
from typing import Optional
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

                if data.get("code") != 0:
                    logger.error(
                        f"Auth failed: {data.get('msg')} (code {data.get('code')})"
                    )
                    return None

                # The response structure based on common Lark patterns:
                # { "code": 0, "data": { "plugin_token": "...", "expire": 7200 } }
                auth_data = data.get("data", {})
                self._plugin_token = auth_data.get("plugin_token")
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
