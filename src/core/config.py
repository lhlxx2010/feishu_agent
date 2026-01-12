from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    LARK_APP_ID: str
    LARK_APP_SECRET: str
    LARK_ENCRYPT_KEY: str | None = None
    LARK_VERIFICATION_TOKEN: str | None = None

    # Project specific
    FEISHU_PROJECT_BASE_URL: str = "https://project.feishu.cn"
    FEISHU_PROJECT_USER_TOKEN: str | None = (
        None  # X-PLUGIN-TOKEN (Optional if using plugin_id)
    )
    FEISHU_PROJECT_USER_KEY: str | None = None  # X-USER-KEY

    # Plugin Auth (Preferred)
    FEISHU_PROJECT_PLUGIN_ID: str | None = None
    FEISHU_PROJECT_PLUGIN_SECRET: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
