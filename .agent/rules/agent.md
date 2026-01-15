---
trigger: always_on
---

# AGENTS.md: 飞书 Agent 生态开发指南

## 1. 通用规则 (General Rules)

- 始终使用中文回复用户，但技术专有名词可保留英文（如 API、Python、DTO 等）
- 使用项目既有风格，不引入新风格，包括代码、文档或交互，默认延用项目中已有的格式、缩进、命名习惯
- 尽可能少地输出内容，仅提供高信息密度回复，禁止无效寒暄、过度铺垫，只输出对当前任务有直接帮助的信息

---

## 2. 项目愿景 (Project Vision)

构建一个从 **飞书项目 (Lark Project)** 起步，逐步演进为具备 **Workflow 编排** 与 **自主推理能力 (Agent)** 的企业级 AI 助手生态。

---

## 3. 核心技术栈 (Technical Stack)

- **语言**: Python 3.11+ (严格使用类型注解 Type Hints)
- **依赖管理**: `uv` (使用 `pyproject.toml` 和 `uv.lock`)
- **飞书 SDK**: `lark-oapi` (v3.x, 优先使用异步接口 `a` 开头方法)
- **协议层**: MCP (Model Context Protocol) 使用 `FastMCP` 框架
- **环境**: Docker (基于 `python:3.11-slim-bookworm`)
- **异步模型**: 基于 `asyncio` 的 Future/Promise 模式
- **严格文档规范**: 所有开发计划都需要更新到doc目录中，并严格按照doc目录中的要求进行实际开发
- **严格test case**:  全部的开发接口都需要在test目录下有对应的test case只有测试通过才能提交代码。

---

## 4. 项目结构规范 (Project Structure)

### 4.1 目录组织

```text
src/
├── core/           # 单例 Client, 配置中心 (pydantic-settings)
├── providers/      # 核心层: 能力者模式实现
│   ├── base.py     # 抽象基类 (Protocol/ABC)
│   ├── common/     # 通用能力 (IM, Base, Drive)
│   └── project/    # 飞书项目专用能力 (Items, Fields, Gantt)
├── schemas/        # 数据模型 (Pydantic), 用于精简 API 返回值
└── mcp_server.py   # MCP 接口层: 注册 Tool 与 Resource
```

### 4.2 结构原则

- **分层组织**：按功能或领域划分目录，遵循"关注点分离"原则
- **命名一致**：使用一致且描述性的目录和文件命名，反映其用途和内容
- **模块化**：相关功能放在同一模块，减少跨模块依赖
- **适当嵌套**：避免过深的目录嵌套，一般不超过 3-4 层
- **资源分类**：区分代码、资源、配置和测试文件
- **依赖管理**：集中管理依赖，避免多处声明
- **约定优先**：遵循语言或框架的标准项目结构约定

### 4.3 OOP 与 Provider 模式

- **封装**: 所有飞书接口调用必须封装在 `Provider` 类中
- **解耦**: 使用 **Provider 模式**。`mcp_server.py` 只与 `Provider` 抽象接口交互，不直接操作底层 SDK
- **精简**: Provider 必须对飞书原始 JSON 进行数据清洗，仅向 Agent 返回核心业务字段，以节省 Token

---

## 5. 通用开发原则 (Development Principles)

- **可测试性**：编写可测试的代码，组件应保持单一职责
- **DRY 原则**：避免重复代码，提取共用逻辑到单独的函数或类
- **代码简洁**：保持代码简洁明了，遵循 KISS 原则（保持简单直接）
- **命名规范**：使用描述性的变量、函数和类名，反映其用途和含义
- **注释文档**：为复杂逻辑添加注释，编写清晰的文档说明功能和用法
- **风格一致**：遵循项目或语言的官方风格指南和代码约定
- **利用生态**：优先使用成熟的库和工具，避免不必要的自定义实现
- **架构设计**：考虑代码的可维护性、可扩展性和性能需求
- **版本控制**：编写有意义的提交信息，保持逻辑相关的更改在同一提交中
- **异常处理**：正确处理边缘情况和错误，提供有用的错误信息
- **实际调用原则**：如果涉及api调用接口开发可以在scripts目录中实现简单测试脚本，确保接口调用正确
- **文档依据原因**：必须依据doc目录中的文档进行开发
- **自测试原则**：必须保证uv pytest run完全通过，如果遇到问题应该先分为是否是代码问题，再检查测试用例

---

## 6. 开发守则 (Development Rules)

### 6.1 异步优先 (Async First)

- 所有的 API 请求必须使用异步方法
- 示例: 使用 `client.im.v1.message.acreate()` 而不是 `create()`
- 处理多个并发请求时，使用 `asyncio.gather()`

### 6.2 错误处理

- 不允许直接抛出飞书 SDK 的原始异常
- 必须在 Provider 层捕获异常，并返回人类/Agent 可读的中文错误提示

### 6.3 文档注释 (Docstrings)

- 每个 `mcp.tool()` 必须包含极其详尽的 Docstring
- **Docstring 必须描述**: 1. 工具的功能；2. 参数的业务含义；3. 预期返回的结果

---

## 7. 演进路线图 (Roadmap)

1. **Stage 1 (Current)**: 飞书项目 MCP 落地，实现工作项 CRUD 自动化
2. **Stage 2**: 引入 LangGraph 进行逻辑编排 (Workflow)
3. **Stage 3**: 完整 Agent 化，支持自然语言决策

---

## 8. 开发指令速查 (Quick Reference)

> 当开发新功能时，请确保：
>
> 1. 检查 `src/core/client.py` 确保单例调用
> 2. 在 `src/providers/` 下按类别创建新的类
> 3. 在 `main.py` 中使用 `FastMCP` 注册工具
> 4. 保持代码符合 Python 3.11 的异步高性能标准

---

## 9. 可用 Skills

本项目配置了以下按需加载的 Skills（位于 `.opencode/skill/`）：

| Skill | 描述 |
|-------|------|
| `python-dev` | Python 编码规则和最佳实践 |
| `typescript-dev` | TypeScript 编码规则和最佳实践 |
| `cpp-dev` | 现代 C++ (C++17/20) 编码规则 |
| `git-commit` | Git 提交规范和分支管理 |
| `gitflow` | Gitflow 工作流规则 |
| `document` | Markdown 文档编写规范 |
| `riper-5` | RIPER-5 严格模式协议 |
