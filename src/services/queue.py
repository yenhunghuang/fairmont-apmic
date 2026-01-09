"""批次佇列鎖定機制 (FR-013: 單一批次執行)"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from src.models.database import get_connection
from src.models.entities import BatchStatus


class BatchQueueLock:
    """批次處理佇列鎖定

    確保同一時間只有一個批次在執行 (FR-013)
    使用 asyncio.Lock 配合 DB 狀態檢查
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._current_batch_uuid: str | None = None

    def is_locked(self) -> bool:
        """檢查是否有批次正在執行"""
        return self._lock.locked()

    def get_current_batch(self) -> str | None:
        """取得目前執行中的批次 UUID"""
        return self._current_batch_uuid

    @asynccontextmanager
    async def acquire(self, batch_uuid: str) -> AsyncGenerator[bool, None]:
        """取得佇列鎖定

        Args:
            batch_uuid: 批次 UUID

        Yields:
            bool: True 表示成功取得鎖定，False 表示已有批次在執行

        Example:
            async with queue_lock.acquire(batch_uuid) as acquired:
                if acquired:
                    # 執行處理
                else:
                    # 處理被拒絕
        """
        # 非阻塞式嘗試取得鎖定
        if self._lock.locked():
            yield False
            return

        async with self._lock:
            self._current_batch_uuid = batch_uuid
            try:
                yield True
            finally:
                self._current_batch_uuid = None

    async def check_db_for_running_batch(self) -> str | None:
        """檢查資料庫中是否有 RUNNING 狀態的批次

        Returns:
            正在執行的批次 UUID，若無則返回 None
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT batch_uuid FROM processing_batches WHERE status = ?",
                (BatchStatus.RUNNING.value,),
            )
            row = cursor.fetchone()
            return row["batch_uuid"] if row else None

    async def force_release_stale_batches(self) -> int:
        """強制釋放卡住的批次 (標記為 FAILED)

        用於系統重啟後清理未完成的批次

        Returns:
            已清理的批次數量
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE processing_batches
                SET status = ?, error_message = '系統重啟，批次已終止'
                WHERE status = ?
                """,
                (BatchStatus.FAILED.value, BatchStatus.RUNNING.value),
            )
            conn.commit()
            return cursor.rowcount


# 全域單例
_queue_lock: BatchQueueLock | None = None


def get_queue_lock() -> BatchQueueLock:
    """取得佇列鎖定單例"""
    global _queue_lock
    if _queue_lock is None:
        _queue_lock = BatchQueueLock()
    return _queue_lock
