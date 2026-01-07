"""快取服務單元測試 (T045-T046)"""

import os
from pathlib import Path

from src.services.cache import (
    compute_batch_hash,
    compute_file_hash,
    load_cached_result,
    save_result_to_cache,
)


class TestFileHash:
    """檔案雜湊計算測試 (FR-009)"""

    def test_compute_sha256_hash(self):
        """測試 SHA256 雜湊計算"""
        content = b"test content"
        hash_value = compute_file_hash(content)

        # SHA256 雜湊應該是 64 個十六進位字元
        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_same_content_same_hash(self):
        """測試相同內容產生相同雜湊"""
        content = b"identical content"
        hash1 = compute_file_hash(content)
        hash2 = compute_file_hash(content)

        assert hash1 == hash2

    def test_different_content_different_hash(self):
        """測試不同內容產生不同雜湊"""
        hash1 = compute_file_hash(b"content A")
        hash2 = compute_file_hash(b"content B")

        assert hash1 != hash2

    def test_empty_content_hash(self):
        """測試空內容雜湊"""
        hash_value = compute_file_hash(b"")

        # 空內容應該產生有效雜湊
        assert len(hash_value) == 64


class TestBatchHash:
    """批次雜湊計算測試"""

    def test_compute_batch_hash(self):
        """測試批次雜湊計算"""
        hashes = ["abc123", "def456", "ghi789"]
        batch_hash = compute_batch_hash(hashes)

        assert len(batch_hash) == 64

    def test_order_independent(self):
        """測試順序無關 (排序後組合)"""
        hashes1 = ["abc", "def", "ghi"]
        hashes2 = ["ghi", "abc", "def"]

        hash1 = compute_batch_hash(hashes1)
        hash2 = compute_batch_hash(hashes2)

        assert hash1 == hash2


class TestCacheStorage:
    """快取儲存測試"""

    def test_save_and_load_result(self, tmp_path: Path):
        """測試儲存與載入快取結果"""
        os.environ["DATABASE_PATH"] = str(tmp_path / "test.db")

        batch_uuid = "test-batch-uuid"
        result = {
            "batch_id": batch_uuid,
            "items": [{"item_no": "DLX-100"}],
        }

        # 儲存
        result_path = save_result_to_cache(batch_uuid, result)
        assert Path(result_path).exists()

        # 載入
        loaded = load_cached_result(result_path)
        assert loaded is not None
        assert loaded["batch_id"] == batch_uuid
        assert len(loaded["items"]) == 1

    def test_load_nonexistent_file(self):
        """測試載入不存在的檔案"""
        result = load_cached_result("/nonexistent/path.json")
        assert result is None
