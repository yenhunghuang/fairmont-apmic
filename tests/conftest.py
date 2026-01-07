"""pytest fixtures"""

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.models.database import get_connection, init_database


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """設定測試環境變數"""
    # 使用測試資料庫
    test_db = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_PATH"] = test_db
    os.environ["USE_SQLITE_PIPELINE"] = "true"
    os.environ["OPENAI_API_KEY"] = "test_key"

    yield

    # 清理測試資料庫
    if os.path.exists(test_db):
        os.remove(test_db)


@pytest.fixture
def test_db_path(tmp_path: Path) -> Generator[Path, None, None]:
    """建立臨時測試資料庫"""
    db_path = tmp_path / "test.db"
    os.environ["DATABASE_PATH"] = str(db_path)
    init_database(db_path)
    yield db_path

    # 清理
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def test_client(test_db_path: Path) -> Generator[TestClient, None, None]:
    """建立測試用 HTTP client"""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def sample_pdf_path() -> Path:
    """取得測試用 PDF 路徑"""
    docs_dir = Path("docs")
    if docs_dir.exists():
        pdfs = list(docs_dir.glob("*.pdf"))
        if pdfs:
            return pdfs[0]
    # 如果沒有實際 PDF，返回 None
    return None


@pytest.fixture
def sample_pdf_bytes(sample_pdf_path: Path | None) -> bytes | None:
    """讀取測試用 PDF 內容"""
    if sample_pdf_path and sample_pdf_path.exists():
        return sample_pdf_path.read_bytes()
    return None


@pytest.fixture
def mock_batch_uuid() -> str:
    """測試用批次 UUID"""
    return "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def db_connection(test_db_path: Path):
    """取得測試資料庫連線"""
    with get_connection(test_db_path) as conn:
        yield conn
