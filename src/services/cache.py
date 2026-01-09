"""快取服務 (FR-009, FR-021)"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from src.api.deps import get_settings
from src.models.database import get_connection
from src.models.entities import CacheRecord


def compute_file_hash(file_content: bytes) -> str:
    """計算檔案 SHA256 雜湊 (FR-009)

    Args:
        file_content: 檔案內容

    Returns:
        SHA256 雜湊 (64 字元)
    """
    return hashlib.sha256(file_content).hexdigest()


def compute_batch_hash(file_hashes: list[str]) -> str:
    """計算批次雜湊

    將多個檔案的 hash 組合成單一 batch hash

    Args:
        file_hashes: 檔案 hash 列表

    Returns:
        批次 SHA256 雜湊
    """
    combined = "".join(sorted(file_hashes))
    return hashlib.sha256(combined.encode()).hexdigest()


def get_cache_record(file_hash: str) -> CacheRecord | None:
    """查詢快取記錄

    Args:
        file_hash: 檔案 SHA256 雜湊

    Returns:
        快取記錄，若無或已過期則返回 None
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM cache_records
            WHERE file_hash = ?
              AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """,
            (file_hash,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        # 更新命中次數
        cursor.execute(
            "UPDATE cache_records SET hit_count = hit_count + 1 WHERE cache_id = ?",
            (row["cache_id"],),
        )
        conn.commit()

        return CacheRecord.from_row(row)


def save_cache_record(file_hash: str, result_path: str, ttl_days: int | None = None) -> int:
    """儲存快取記錄

    Args:
        file_hash: 檔案 SHA256 雜湊
        result_path: 結果 JSON 檔案路徑
        ttl_days: 快取保留天數 (預設從設定讀取)

    Returns:
        cache_id
    """
    settings = get_settings()
    ttl = ttl_days or settings.cache_ttl_days

    expires_at = datetime.now() + timedelta(days=ttl)

    with get_connection() as conn:
        cursor = conn.cursor()

        # 使用 INSERT OR REPLACE 處理重複 hash
        cursor.execute(
            """
            INSERT OR REPLACE INTO cache_records
            (file_hash, result_path, expires_at, hit_count)
            VALUES (?, ?, ?, 0)
            """,
            (file_hash, result_path, expires_at.isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def load_cached_result(result_path: str) -> dict | None:
    """載入快取結果

    Args:
        result_path: 結果 JSON 檔案路徑

    Returns:
        快取的 JSON 資料，若檔案不存在則返回 None
    """
    path = Path(result_path)
    if not path.exists():
        return None

    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_result_to_cache(batch_uuid: str, result: dict) -> str:
    """將結果儲存為快取檔案

    Args:
        batch_uuid: 批次 UUID
        result: 結果資料

    Returns:
        結果檔案路徑
    """
    settings = get_settings()
    cache_dir = Path(settings.database_path).parent / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    result_path = cache_dir / f"{batch_uuid}.json"

    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return str(result_path)


def cleanup_expired_cache() -> int:
    """清理過期快取 (FR-021)

    Returns:
        清理的記錄數
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # 取得即將刪除的記錄 (用於清理檔案)
        cursor.execute(
            """
            SELECT result_path FROM cache_records
            WHERE expires_at < CURRENT_TIMESTAMP
            """,
        )
        expired_paths = [row["result_path"] for row in cursor.fetchall()]

        # 刪除過期記錄
        cursor.execute("DELETE FROM cache_records WHERE expires_at < CURRENT_TIMESTAMP")
        deleted_count = cursor.rowcount
        conn.commit()

        # 刪除對應的快取檔案
        for path in expired_paths:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass  # 忽略刪除失敗

        return deleted_count


class CacheService:
    """快取服務"""

    def check_cache(self, file_contents: list[bytes]) -> tuple[bool, str | None, dict | None]:
        """檢查是否有快取

        Args:
            file_contents: 檔案內容列表

        Returns:
            (是否命中, 快取路徑, 快取結果)
        """
        # 計算批次 hash
        file_hashes = [compute_file_hash(content) for content in file_contents]
        batch_hash = compute_batch_hash(file_hashes)

        # 查詢快取
        record = get_cache_record(batch_hash)
        if record:
            result = load_cached_result(record.result_path)
            if result:
                return True, record.result_path, result

        return False, None, None

    def save_cache(
        self,
        file_contents: list[bytes],
        batch_uuid: str,
        result: dict,
    ) -> str:
        """儲存快取

        Args:
            file_contents: 檔案內容列表
            batch_uuid: 批次 UUID
            result: 處理結果

        Returns:
            快取檔案路徑
        """
        # 計算批次 hash
        file_hashes = [compute_file_hash(content) for content in file_contents]
        batch_hash = compute_batch_hash(file_hashes)

        # 儲存結果檔案
        result_path = save_result_to_cache(batch_uuid, result)

        # 儲存快取記錄
        save_cache_record(batch_hash, result_path)

        return result_path


# 全域單例
_cache_service: CacheService | None = None


def get_cache_service() -> CacheService:
    """取得快取服務單例"""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
