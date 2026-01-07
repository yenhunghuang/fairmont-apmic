"""佇列鎖定機制單元測試"""

import asyncio

import pytest

from src.services.queue import BatchQueueLock, get_queue_lock


class TestBatchQueueLock:
    """BatchQueueLock 測試"""

    @pytest.fixture
    def queue_lock(self) -> BatchQueueLock:
        """建立新的佇列鎖定實例"""
        return BatchQueueLock()

    @pytest.mark.asyncio
    async def test_acquire_single_batch(self, queue_lock: BatchQueueLock):
        """測試單一批次可以成功取得鎖定"""
        batch_uuid = "batch-001"

        async with queue_lock.acquire(batch_uuid) as acquired:
            assert acquired is True
            assert queue_lock.is_locked()
            assert queue_lock.get_current_batch() == batch_uuid

        # 釋放後應該不再鎖定
        assert not queue_lock.is_locked()
        assert queue_lock.get_current_batch() is None

    @pytest.mark.asyncio
    async def test_concurrent_batch_rejection(self, queue_lock: BatchQueueLock):
        """測試併發批次被拒絕"""
        batch_uuid_1 = "batch-001"
        batch_uuid_2 = "batch-002"
        results = []

        async def process_batch(batch_uuid: str, delay: float):
            async with queue_lock.acquire(batch_uuid) as acquired:
                results.append((batch_uuid, acquired))
                if acquired:
                    await asyncio.sleep(delay)  # 模擬處理時間

        # 同時啟動兩個批次
        await asyncio.gather(
            process_batch(batch_uuid_1, 0.1),
            process_batch(batch_uuid_2, 0.1),
        )

        # 應該只有一個成功
        successful = [r for r in results if r[1] is True]
        rejected = [r for r in results if r[1] is False]

        assert len(successful) == 1
        assert len(rejected) == 1

    @pytest.mark.asyncio
    async def test_lock_release_on_completion(self, queue_lock: BatchQueueLock):
        """測試完成後鎖定正確釋放"""
        batch_uuid = "batch-001"

        # 第一個批次
        async with queue_lock.acquire(batch_uuid) as acquired:
            assert acquired is True

        # 第二個批次應該可以取得鎖定
        async with queue_lock.acquire("batch-002") as acquired:
            assert acquired is True

    @pytest.mark.asyncio
    async def test_lock_release_on_failure(self, queue_lock: BatchQueueLock):
        """測試失敗後鎖定正確釋放"""
        batch_uuid = "batch-001"

        try:
            async with queue_lock.acquire(batch_uuid) as acquired:
                assert acquired is True
                raise RuntimeError("模擬失敗")
        except RuntimeError:
            pass

        # 失敗後應該釋放鎖定
        assert not queue_lock.is_locked()

        # 下一個批次應該可以取得鎖定
        async with queue_lock.acquire("batch-002") as acquired:
            assert acquired is True

    @pytest.mark.asyncio
    async def test_is_locked_status(self, queue_lock: BatchQueueLock):
        """測試 is_locked 狀態"""
        assert not queue_lock.is_locked()

        async with queue_lock.acquire("batch-001") as acquired:
            assert acquired is True
            assert queue_lock.is_locked()

        assert not queue_lock.is_locked()

    @pytest.mark.asyncio
    async def test_get_current_batch(self, queue_lock: BatchQueueLock):
        """測試取得目前批次"""
        assert queue_lock.get_current_batch() is None

        async with queue_lock.acquire("batch-001") as acquired:
            assert acquired is True
            assert queue_lock.get_current_batch() == "batch-001"

        assert queue_lock.get_current_batch() is None


class TestGetQueueLock:
    """get_queue_lock 單例測試"""

    def test_singleton(self):
        """測試單例模式"""
        lock1 = get_queue_lock()
        lock2 = get_queue_lock()
        assert lock1 is lock2
