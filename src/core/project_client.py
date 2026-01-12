import httpx
from typing import Optional, AsyncGenerator
from src.core.config import settings
from src.core.auth import auth_manager

_project_client = None


class ProjectAuth(httpx.Auth):
    """
    Custom Auth for Feishu Project API.
    Handles dynamic injection of X-PLUGIN-TOKEN and X-USER-KEY.
    """

    async def async_auth_flow(self, request: httpx.Request):
        token = await auth_manager.get_plugin_token()
        if token:
            request.headers["X-PLUGIN-TOKEN"] = token

        user_key = settings.FEISHU_PROJECT_USER_KEY
        if user_key:
            request.headers["X-USER-KEY"] = user_key

        yield request


class ProjectClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.FEISHU_PROJECT_BASE_URL
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Content-Type": "application/json"},
            auth=ProjectAuth(),
        )

    async def post(self, path: str, json: Optional[dict] = None):
        return await self.client.post(path, json=json)

    async def get(self, path: str, params: Optional[dict] = None):
        return await self.client.get(path, params=params)


def get_project_client():
    global _project_client
    if not _project_client:
        _project_client = ProjectClient()
    return _project_client
