# Feishu Agent (MCP Server)

这是一个基于 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 构建的飞书 (Lark/Feishu) 智能代理服务。它允许 LLM (如 Claude, Cursor) 通过标准协议直接调用飞书项目 (Feishu Project) 和飞书开放平台的能力。

## ✨ 功能特性

*   **MCP 协议支持**: 基于 `FastMCP` 实现，支持标准 MCP 工具调用。
*   **飞书项目集成**:
    *   查询活跃工作项 (Tasks/Bugs)。
    *   创建新的工作项。
*   **架构设计**:
    *   **Async First**: 全异步架构，基于 `asyncio` 和 `httpx`。
    *   **Provider 模式**: 业务逻辑与底层 API 解耦。
    *   **双客户端支持**: 官方 `lark-oapi` (通用能力) + 自定义 `ProjectClient` (飞书项目 RESTful API)。

## 🚀 快速开始 (开发指南)

### 前置要求

*   [uv](https://github.com/astral-sh/uv) (推荐) 或 Python 3.11+
*   Docker (可选，用于容器化开发)

### 1. 环境配置

复制配置模板并填写您的飞书凭证：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入以下信息：
*   `LARK_APP_ID` / `LARK_APP_SECRET`: 飞书自建应用凭证。
*   `FEISHU_PROJECT_USER_TOKEN` / `FEISHU_PROJECT_USER_KEY`: 飞书项目 API 专用凭证 (X-PLUGIN-TOKEN / X-USER-KEY)。
*   `FEISHU_PROJECT_BASE_URL`: (可选) 私有化部署地址，默认为 `https://project.feishu.cn`。

### 2. 安装依赖

本项目使用 `uv` 进行依赖管理：

```bash
uv sync
```

### 3. 启动服务

```bash
uv run main.py
```

服务启动后，将通过 `stdio` (标准输入输出) 进行通信。日志会输出到 `log/agent.log` 文件中。

可以使用 `tail -f log/agent.log` 实时查看运行日志。

## 🧪 测试 (Testing)

本项目严格遵循 **TDD (测试驱动开发)** 流程。

运行所有测试：
```bash
uv run pytest
```

运行特定模块测试：
```bash
uv run pytest tests/providers/project/test_manager.py -v
```

测试环境说明：
*   使用 `pytest-asyncio` 处理异步测试。
*   使用 `respx` 模拟 HTTP 请求，无需真实 Token 即可运行单元测试。

## 🐳 部署 (Deployment)

### 使用 Docker

1. **构建镜像**
   ```bash
   docker compose build
   ```

2. **启动服务**
   ```bash
   docker compose up -d
   ```

或者直接使用 `Dockerfile`:
```bash
docker build -t feishu-agent .
docker run --env-file .env feishu-agent
```

## 📂 项目结构

```text
.
├── src/
│   ├── core/           # 核心组件 (Config, Clients)
│   ├── providers/      # 能力层 (Provider 模式实现)
│   │   ├── project/    # 飞书项目专用逻辑
│   │   └── common_im.py
│   ├── schemas/        # Pydantic 数据模型
│   └── mcp_server.py   # MCP Server 定义
├── tests/              # 测试用例 (对应 src 目录结构)
├── main.py             # 程序入口
├── pyproject.toml      # 依赖配置
└── doc/                # 详细开发文档
```

## 📏 开发规范

在贡献代码前，请务必阅读以下文档：

1.  **[开发协议 (Development Protocol)](doc/First_stage/Development_Protocol.md)**: 规定了 Bottom-Up 开发流程和 TDD 测试规范。
2.  **[API 参考文档](doc/Feishu_project_api/API_Reference.md)**: 飞书项目 API 的详细说明。

### 核心原则
*   **异步优先**: 所有 I/O 操作必须使用 `async/await`。
*   **类型安全**: 严格使用 Python Type Hints。
*   **错误处理**: 在 Provider 层捕获底层 API 异常，返回对 Agent 友好的错误信息。
