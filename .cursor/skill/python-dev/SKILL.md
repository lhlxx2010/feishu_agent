---
name: python-dev
description: Python 编码规则和最佳实践，包括 PEP 8 风格、类型注解、虚拟环境、测试和文档规范
metadata:
  audience: maintainers
  workflow: github
---

# Python 开发规范

## 何时使用
当你编写或审查 Python 代码（`*.py` 文件）时使用此 skill。

## 代码规范

- 遵循 PEP 8 风格指南和命名约定
- 使用类型注解增强代码可读性和类型安全性
- 使用虚拟环境管理依赖：
  - 优先使用 `venv` 或 `poetry` 进行环境隔离
  - 使用 `requirements.txt` 或 `pyproject.toml` 记录依赖
- 使用上下文管理器处理资源（如文件操作）
- 优先使用列表推导式、生成器表达式和字典推导式
- 使用 `pytest` 进行测试，保持高测试覆盖率
- 使用文档字符串（docstrings）记录函数、类和模块
- 遵循面向对象设计原则（SOLID）
- 使用异常处理保证程序健壮性
- 使用 `dataclasses` 或 `pydantic` 模型表示数据
