import httpx
import logging
from typing import Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from src.core.config import settings
from src.core.auth import auth_manager

logger = logging.getLogger(__name__)

_project_client = None

# 定义可重试的异常类型
RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.ConnectTimeout,
)


def _should_retry_response(response: httpx.Response) -> bool:
    """检查响应是否需要重试（5xx 服务端错误）"""
    return response.status_code >= 500


class RetryableHTTPError(Exception):
    """可重试的 HTTP 错误"""

    def __init__(self, response: httpx.Response):
        self.response = response
        super().__init__(f"HTTP {response.status_code}: {response.text[:200]}")


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
    """
    飞书项目 API 异步客户端

    特性:
    - 自动注入认证头 (X-PLUGIN-TOKEN, X-USER-KEY)
    - 自动重试机制 (网络错误、超时、5xx 错误)
    - 指数退避策略
    """

    # 重试配置
    MAX_RETRIES = 3
    RETRY_MIN_WAIT = 1  # 最小等待时间（秒）
    RETRY_MAX_WAIT = 10  # 最大等待时间（秒）

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.FEISHU_PROJECT_BASE_URL
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Content-Type": "application/json"},
            auth=ProjectAuth(),
            timeout=httpx.Timeout(30.0),  # 30秒超时
        )

    def _get_retry_decorator(self):
        """获取重试装饰器配置"""
        return retry(
            stop=stop_after_attempt(self.MAX_RETRIES),
            wait=wait_exponential(
                multiplier=1, min=self.RETRY_MIN_WAIT, max=self.RETRY_MAX_WAIT
            ),
            retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS + (RetryableHTTPError,)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> httpx.Response:
        """
        带重试的请求方法

        Args:
            method: HTTP 方法 (GET, POST, PUT, DELETE)
            path: API 路径
            json: 请求体 (可选)
            params: 查询参数 (可选)

        Returns:
            httpx.Response

        Raises:
            RetryableHTTPError: 5xx 错误（会触发重试）
            httpx.HTTPStatusError: 其他 HTTP 错误
        """

        @self._get_retry_decorator()
        async def _do_request():
            if method == "GET":
                response = await self.client.get(path, params=params)
            elif method == "POST":
                response = await self.client.post(path, json=json)
            elif method == "PUT":
                response = await self.client.put(path, json=json)
            elif method == "DELETE":
                response = await self.client.delete(path)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # 5xx 错误触发重试
            if _should_retry_response(response):
                logger.warning(
                    f"Received {response.status_code} from {path}, will retry..."
                )
                raise RetryableHTTPError(response)

            return response

        return await _do_request()

    async def post(self, path: str, json: Optional[dict] = None) -> httpx.Response:
        """POST 请求（带自动重试）"""
        return await self._request_with_retry("POST", path, json=json)

    async def get(self, path: str, params: Optional[dict] = None) -> httpx.Response:
        """GET 请求（带自动重试）"""
        return await self._request_with_retry("GET", path, params=params)

    async def put(self, path: str, json: Optional[dict] = None) -> httpx.Response:
        """PUT 请求（带自动重试）"""
        return await self._request_with_retry("PUT", path, json=json)

    async def delete(self, path: str) -> httpx.Response:
        """DELETE 请求（带自动重试）"""
        return await self._request_with_retry("DELETE", path)

    async def close(self):
        """关闭客户端连接"""
        await self.client.aclose()


def get_project_client() -> ProjectClient:
    """获取全局单例客户端"""
    global _project_client
    if not _project_client:
        _project_client = ProjectClient()
    return _project_client
