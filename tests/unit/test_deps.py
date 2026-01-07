"""依賴注入與配置測試 (T059)"""




class TestFeatureToggle:
    """架構切換功能測試 (FR-012)"""

    def test_default_use_sqlite_pipeline(self):
        """測試預設啟用 SQLite 管線"""
        from src.api.deps import Settings

        settings = Settings()
        assert settings.use_sqlite_pipeline is True

    def test_env_var_parsing_true(self, monkeypatch):
        """測試環境變數解析 (true)"""
        monkeypatch.setenv("USE_SQLITE_PIPELINE", "true")

        # 清除快取
        from src.api.deps import get_settings

        get_settings.cache_clear()

        from src.api.deps import Settings

        settings = Settings()
        assert settings.use_sqlite_pipeline is True

    def test_env_var_parsing_false(self, monkeypatch):
        """測試環境變數解析 (false)"""
        monkeypatch.setenv("USE_SQLITE_PIPELINE", "false")

        from src.api.deps import get_settings

        get_settings.cache_clear()

        from src.api.deps import Settings

        settings = Settings()
        assert settings.use_sqlite_pipeline is False

    def test_is_sqlite_pipeline_enabled(self, monkeypatch):
        """測試 is_sqlite_pipeline_enabled 函數"""
        monkeypatch.setenv("USE_SQLITE_PIPELINE", "true")

        from src.api.deps import get_settings

        get_settings.cache_clear()

        from src.api.deps import is_sqlite_pipeline_enabled

        assert is_sqlite_pipeline_enabled() is True


class TestSettingsValidation:
    """設定驗證測試"""

    def test_default_settings(self, monkeypatch):
        """測試預設設定值"""
        # 清除環境變數以測試預設值
        monkeypatch.delenv("DATABASE_PATH", raising=False)

        from src.api.deps import get_settings

        get_settings.cache_clear()

        from src.api.deps import Settings

        settings = Settings()

        # 只測試不受環境變數影響的設定
        assert settings.cache_ttl_days == 1
        assert settings.max_upload_files == 20
        assert settings.openai_timeout_seconds == 300
        assert settings.openai_max_retries == 2

    def test_db_path_property(self, monkeypatch):
        """測試 db_path 屬性"""
        from pathlib import Path

        monkeypatch.delenv("DATABASE_PATH", raising=False)

        from src.api.deps import get_settings

        get_settings.cache_clear()

        from src.api.deps import Settings

        settings = Settings()
        assert isinstance(settings.db_path, Path)

    def test_settings_singleton(self):
        """測試 get_settings 單例"""
        from src.api.deps import get_settings

        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
