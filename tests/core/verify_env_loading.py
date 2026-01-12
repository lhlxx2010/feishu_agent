import os
from src.core.config import Settings


def test_settings_load_from_env_file(tmp_path):
    """Verify that FEISHU_PROJECT_BASE_URL can be loaded from a .env file."""
    # Create a temporary .env file
    env_file = tmp_path / ".env.test"
    content = """
LARK_APP_ID=test_id
LARK_APP_SECRET=test_secret
FEISHU_PROJECT_BASE_URL=https://custom.domain.com
"""
    env_file.write_text(content, encoding="utf-8")

    # Load settings pointing to this file
    # Note: pydantic-settings caches settings, but since we instantiate a new object
    # and pass _env_file explicitly (or rely on the class config if we monkeypatch), it should work.
    # However, SettingsConfigDict is defined in the class.
    # The safest way to test strict file loading is to instantiate with _env_file argument if supported,
    # or subclass for the test.

    class TestSettings(Settings):
        model_config = {"env_file": str(env_file), "env_file_encoding": "utf-8"}

    settings = TestSettings()

    assert settings.FEISHU_PROJECT_BASE_URL == "https://custom.domain.com"
    print("Verification Successful: FEISHU_PROJECT_BASE_URL loaded from .env file")


if __name__ == "__main__":
    import pytest
    import sys

    sys.exit(pytest.main(["-v", __file__]))
