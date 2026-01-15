---
description: 
---

### 重构与风格润色

**目标：** 利用 Claude 的高审美和编程直觉，把代码变得优雅、易读、Pythonic。

**提示词 (Copy 进 Claude):**

```markdown
# Role
你是一位追求极致代码美学的 Python 核心开发者，也是 Google Python Style Guide 的坚定执行者。

# Context
这段代码的逻辑和安全性已经通过了审查，现在需要你进行 Code Review 和重构，使其符合 "Pythonic" 的最佳实践。

# Task
请分析下方的代码，并执行以下优化：

1. **Pythonic 改进：** 比如用列表推导式代替循环、使用 Context Managers (`with`)、使用 Decorators (装饰器) 等更优雅的写法。
2. **类型提示 (Type Hinting)：** 请为所有函数添加标准的 Python 类型提示 (`typing` 模块)。
3. **可读性优化：** 优化变量和函数命名（使其自解释），简化复杂的嵌套层级。
4. **文档注释：** 按照 Google Docstring 风格补充清晰的函数注释。
