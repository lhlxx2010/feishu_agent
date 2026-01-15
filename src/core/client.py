"""
Author: liangyz liangyz@seirobotics.net
Date: 2026-01-12 15:48:30
LastEditors: liangyz liangyz@seirobotics.net
LastEditTime: 2026-01-15 11:05:32
FilePath: /feishu_agent/src/core/client.py
"""

import logging

import lark_oapi as lark

from src.core.config import settings

logger = logging.getLogger(__name__)

_lark_client = None


def get_lark_client():
    """
    获取 Lark 客户端实例

    注意：需要配置 LARK_APP_ID 和 LARK_APP_SECRET 环境变量才能使用。
    如果未配置，会抛出 ValueError。
    """
    global _lark_client
    if not _lark_client:
        if not settings.LARK_APP_ID or not settings.LARK_APP_SECRET:
            raise ValueError(
                "LARK_APP_ID 和 LARK_APP_SECRET 环境变量未配置。"
                "这些字段在使用 IM 功能时是必需的。"
                "请参考文档配置：https://github.com/Wulnut/feishu_agent/blob/main/doc/安装使用指南.md"
            )
        logger.info("Initializing Lark client with app_id=%s", settings.LARK_APP_ID)
        _lark_client = (
            lark.Client.builder()
            .app_id(settings.LARK_APP_ID)
            .app_secret(settings.LARK_APP_SECRET)
            .log_level(lark.LogLevel.DEBUG)
            .build()
        )
        logger.debug("Lark client initialized successfully")
    else:
        logger.debug("Reusing existing Lark client instance")
    return _lark_client
