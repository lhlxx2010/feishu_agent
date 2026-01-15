"""
Author: liangyz liangyz@seirobotics.net
Date: 2026-01-12 15:48:26
LastEditors: liangyz liangyz@seirobotics.net
LastEditTime: 2026-01-13 23:56:50
FilePath: /feishu_agent/src/core/config.py
"""

import logging

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    LARK_APP_ID: str | None = None  # 可选：仅在使用 IM 功能时需要
    LARK_APP_SECRET: str | None = None  # 可选：仅在使用 IM 功能时需要
    LARK_ENCRYPT_KEY: str | None = None
    LARK_VERIFICATION_TOKEN: str | None = None

    # Project specific
    FEISHU_PROJECT_BASE_URL: str = "https://project.feishu.cn"
    FEISHU_PROJECT_USER_TOKEN: str | None = (
        None  # X-PLUGIN-TOKEN (Optional if using plugin_id)
    )
    FEISHU_PROJECT_USER_KEY: str | None = None  # X-USER-KEY

    # 默认项目 Key
    FEISHU_PROJECT_KEY: str | None = None  # 生产/默认项目
    FEISHU_TEST_PROJECT_KEY: str | None = None  # CI/测试专用项目

    # Plugin Auth (Preferred)
    FEISHU_PROJECT_PLUGIN_ID: str | None = None
    FEISHU_PROJECT_PLUGIN_SECRET: str | None = None

    # Logging
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    def get_log_level(self) -> int:
        """Convert string log level to logging constant."""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return level_map.get(self.LOG_LEVEL.upper(), logging.INFO)


settings = Settings()
