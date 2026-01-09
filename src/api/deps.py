"""依賴注入與配置管理"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """應用程式設定 (從環境變數載入)"""

    # 資料庫設定
    database_path: str = "data/fairmont.db"

    # 架構切換
    use_sqlite_pipeline: bool = True

    # 快取設定
    cache_ttl_days: int = 1

    # 上傳限制
    max_upload_files: int = 20

    # APMIC LLM API
    openai_api_key: str = ""
    openai_api_base: str = "https://api.apmic-ai.com/v1"
    openai_model: str = "gemma-3-12b"
    openai_timeout_seconds: int = 300
    openai_max_retries: int = 2

    # 日誌設定
    log_level: str = "INFO"
    log_file: str = "logs/app.log"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def db_path(self) -> Path:
        """取得資料庫路徑"""
        return Path(self.database_path)


@lru_cache
def get_settings() -> Settings:
    """取得設定單例"""
    return Settings()


def is_sqlite_pipeline_enabled() -> bool:
    """檢查是否啟用 SQLite 管線 (FR-012)"""
    settings = get_settings()
    return settings.use_sqlite_pipeline
