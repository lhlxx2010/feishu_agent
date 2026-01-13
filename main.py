"""
Feishu Agent MCP Server 入口点

支持两种运行方式：
1. 直接运行: python main.py
2. 通过 uv tool install 安装后: lark-agent
"""

from src.mcp_server import main, mcp

if __name__ == "__main__":
    main()
