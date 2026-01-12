# 第一阶段概览

## 1. 开发环境与核心库 (The Tech Stack)

| 类别 | 推荐组件 | 说明 |
| --- | --- | --- |
| **基础运行环境** | **Python 3.11.x** | 兼顾性能与 `asyncio` 稳定性。 |
| **依赖管理工具** | **uv** | 替代 pip，管理虚拟环境并锁定 `uv.lock` 以保证 Docker 构建一致性。 |
| **飞书底层通信** | **`lark-oapi`** + **`httpx`** | 官方 SDK 用于通讯录/IM；**飞书项目** API 采用 `httpx` 实现自定义异步调用。 |
| **MCP 实现框架** | **`FastMCP` (python-mcp)** | 类似 FastAPI 的装饰器风格，极大简化工具注册过程。 |
| **配置与校验** | **`pydantic-settings`** | 基于 Pydantic v2，严格校验 `.env` 环境变量中的 AppID/Secret。 |

---

## 2. 方法库（Modules）逻辑划分

按照你的需求，我们将方法库分为三级，确保“飞书通用”与“飞书项目”解耦。

#### **A. 基础支持库 (Core Methods)**

* **`AuthManager` (单例)**：统一管理 Token。对于飞书项目，需特别维护 `X-PLUGIN-TOKEN` 和 `X-USER-KEY` 的生命周期。
* **`AsyncHttpClient`**：
    * 针对通用飞书能力：复用 `lark-oapi` 的异步机制。
    * 针对飞书项目：基于 `httpx` 封装 RESTful 请求，处理特殊的 Header 注入和 JSON 结构。

#### **B. 通用方法库 (Common Library - `tools/common`)**

这些是 Agent 未来的“手脚”，负责跨项目的通用操作：

* **`IMProvider`**：发送富文本消息、卡片消息、上传文件。
* **`BaseProvider`**：对多维表格进行 CRUD 操作（未来扩展用）。

#### **C. 飞书项目专用库 (Project Library - `tools/project`)**

这是你当前的核心，建议按功能逻辑细分为以下方法集：

* **`WorkItemProvider`**：工作项（任务、需求、缺陷）的查询、创建、修改。
* **`GanttProvider`**：处理排期数据、里程碑信息。
* **`FieldMapping`**：专门处理“自定义字段”的映射（飞书项目大量使用 `field_123` 这种 ID，需要一个方法将其映射为“负责人”或“优先级”）。

---

## 3. 第一阶段目录结构（实战版）

```text
lark_mcp_stage1/
├── .env                # 存放 LARK_APP_ID, LARK_APP_SECRET
├── .python-version     # uv 自动识别版本 (3.11)
├── pyproject.toml      # 项目元数据与依赖
├── main.py             # MCP Server 入口 (FastMCP)
├── src/
│   ├── core/
│   │   ├── client.py   # 异步 LarkClient 封装
│   │   ├── project_client.py # 异步 ProjectClient 封装
│   │   └── config.py   # Pydantic Settings
│   ├── providers/      # 能力者目录
│   │   ├── base.py     # 抽象基类 (Abstract Base Class)
│   │   ├── common_im.py# 通用消息库
│   │   └── project/    # 飞书项目方法库
│   │       ├── items.py# 工作项操作
│   │       └── utils.py# 字段映射工具
│   └── schemas/        # 定义 Agent 返回的简洁数据格式

```

---

## 4. 关键代码模式示例 (Future/Promise 风格)

在 `src/providers/project/items.py` 中，我们会这样组织方法：

```python
from typing import List, Dict
import httpx
from src.core.project_client import get_project_client

class ProjectItemProvider:
    def __init__(self, project_key: str):
        self.project_key = project_key
        self.client = get_project_client()  # 自定义的 httpx 客户端

    async def fetch_active_tasks(self) -> List[Dict]:
        """
        [Future 模式] 异步获取所有进行中的任务
        """
        # 1. 构造请求参数 (RESTful)
        url = f"/open_api/{self.project_key}/work_item/filter"
        payload = {
            "work_item_status": ["in_progress"],
            "page_size": 50
        }

        # 2. 发起异步调用 (httpx)
        # client.post 会自动注入 X-PLUGIN-TOKEN 等 headers
        response = await self.client.post(url, json=payload)
        data = response.json()

        # 3. 数据清洗：只给 Agent 返回它关心的字段，减少 Token 消耗
        return [{"id": i["id"], "name": i["name"]} for i in data.get("data", [])]
```

---

## 5. Docker 基础镜像选择

我们将使用基于 **Debian Bookworm** 的 Python 3.11 镜像，因为它对各种 C 扩展（如果未来需要向量库）支持更好：

```dockerfile
FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
# 后续安装与运行指令...

```
---