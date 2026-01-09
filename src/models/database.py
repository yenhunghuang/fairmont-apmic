"""SQLite 資料庫初始化與連線管理"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

# 預設資料庫路徑
DEFAULT_DB_PATH = Path("data/fairmont.db")

# PRAGMA 設定
PRAGMA_SETTINGS = [
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA cache_size = -64000",  # 64MB cache
]

# Schema DDL
SCHEMA_SQL = """
-- ProcessingBatch (處理批次)
CREATE TABLE IF NOT EXISTS processing_batches (
    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_uuid TEXT UNIQUE NOT NULL,
    supplier_id TEXT DEFAULT 'fairmont',
    status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','COMPLETED','FAILED')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,
    total_files INTEGER DEFAULT 0,
    processed_files INTEGER DEFAULT 0,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_batches_status_created ON processing_batches(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_batches_uuid ON processing_batches(batch_uuid);
CREATE INDEX IF NOT EXISTS idx_batches_supplier ON processing_batches(supplier_id);

-- UploadedFile (上傳檔案)
CREATE TABLE IF NOT EXISTS uploaded_files (
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES processing_batches(batch_id),
    file_hash TEXT UNIQUE NOT NULL,
    original_filename TEXT NOT NULL,
    file_role TEXT NOT NULL CHECK(file_role IN ('QUANTITY_SHEET','SPEC_SHEET','FABRIC_SHEET','INDEX')),
    file_size_bytes INTEGER,
    status TEXT NOT NULL CHECK(status IN ('PENDING','CACHED','COMPLETED','FAILED')),
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    cached_result_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_batch_status ON uploaded_files(batch_id, status);
CREATE INDEX IF NOT EXISTS idx_files_hash ON uploaded_files(file_hash);

-- ProcessingStage (處理階段)
CREATE TABLE IF NOT EXISTS processing_stages (
    stage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES processing_batches(batch_id),
    stage_number INTEGER NOT NULL,
    stage_name TEXT NOT NULL CHECK(stage_name IN ('PDF_PARSING','EXTRACTION','NORMALIZATION','MERGING','FURNITURE','FABRIC_LINKING','EXPORT')),
    status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','COMPLETED','FAILED','RETRYING')),
    progress_percent INTEGER DEFAULT 0 CHECK(progress_percent >= 0 AND progress_percent <= 100),
    started_at DATETIME,
    completed_at DATETIME,
    execution_time_ms INTEGER,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    checkpoint_data TEXT
);
CREATE INDEX IF NOT EXISTS idx_stages_batch_status ON processing_stages(batch_id, status, stage_number);

-- FurnitureItem (家具項目)
CREATE TABLE IF NOT EXISTS furniture_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES processing_batches(batch_id),
    item_no TEXT NOT NULL,
    description TEXT,
    dimensions TEXT,
    qty INTEGER,
    uom TEXT,
    materials TEXT,
    location TEXT,
    photo_path TEXT,
    brand TEXT,
    status TEXT CHECK(status IN ('SUCCESS','FAILED_EXTRACTION','PENDING_REVIEW')),
    related_fabric_ids TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_items_batch_item_no ON furniture_items(batch_id, item_no);
CREATE INDEX IF NOT EXISTS idx_items_status ON furniture_items(status);

-- FabricItem (面料項目)
CREATE TABLE IF NOT EXISTS fabric_items (
    fabric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES processing_batches(batch_id),
    item_no TEXT NOT NULL,
    brand TEXT,
    pattern TEXT,
    color TEXT,
    width REAL,
    content TEXT,
    abrasion TEXT,
    vendor TEXT,
    furniture_com TEXT,
    status TEXT CHECK(status IN ('SUCCESS','PENDING_LINK','ORPHAN')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_fabrics_batch ON fabric_items(batch_id);
CREATE INDEX IF NOT EXISTS idx_fabrics_furniture_com ON fabric_items(furniture_com);

-- CacheRecord (快取記錄)
CREATE TABLE IF NOT EXISTS cache_records (
    cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash TEXT UNIQUE NOT NULL,
    result_path TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    hit_count INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cache_hash ON cache_records(file_hash);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache_records(expires_at);
"""


def get_db_path() -> Path:
    """取得資料庫路徑，優先使用環境變數"""
    import os

    db_path = os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH))
    return Path(db_path)


def init_database(db_path: Path | None = None) -> None:
    """初始化資料庫：建立表格與索引"""
    if db_path is None:
        db_path = get_db_path()

    # 確保目錄存在
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        # 設定 PRAGMA
        for pragma in PRAGMA_SETTINGS:
            cursor.execute(pragma)

        # 執行 schema
        cursor.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_connection(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """取得資料庫連線 (context manager)"""
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()
        for pragma in PRAGMA_SETTINGS:
            cursor.execute(pragma)
        yield conn
    finally:
        conn.close()


def check_database_health(db_path: Path | None = None) -> dict:
    """檢查資料庫健康狀態"""
    if db_path is None:
        db_path = get_db_path()

    if not db_path.exists():
        return {"status": "not_initialized", "message": "資料庫尚未建立"}

    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()

            # 檢查表格是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row[0] for row in cursor.fetchall()]

            expected_tables = [
                "cache_records",
                "fabric_items",
                "furniture_items",
                "processing_batches",
                "processing_stages",
                "uploaded_files",
            ]

            missing = set(expected_tables) - set(tables)
            if missing:
                return {
                    "status": "incomplete",
                    "message": f"缺少表格: {missing}",
                    "tables": tables,
                }

            return {
                "status": "connected",
                "message": "資料庫連線正常",
                "tables": tables,
            }
    except sqlite3.Error as e:
        return {"status": "error", "message": f"資料庫錯誤: {e}"}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "init":
        print("正在初始化資料庫...")
        init_database()
        print(f"資料庫已建立: {get_db_path()}")

        health = check_database_health()
        print(f"健康狀態: {health['status']}")
        print(f"訊息: {health['message']}")
    else:
        print("使用方式: python -m src.models.database init")
