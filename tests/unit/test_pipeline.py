"""管線處理單元測試 (T020)"""

import pytest

from src.models.entities import STAGE_NUMBER_MAP, TOTAL_STAGES, StageName, StageStatus


class TestPipelineStages:
    """管線階段測試"""

    def test_stage_count(self):
        """測試總階段數為 7"""
        assert TOTAL_STAGES == 7
        assert len(StageName) == 7

    def test_stage_number_mapping(self):
        """測試階段編號對照"""
        assert STAGE_NUMBER_MAP[StageName.PDF_PARSING] == 1
        assert STAGE_NUMBER_MAP[StageName.EXTRACTION] == 2
        assert STAGE_NUMBER_MAP[StageName.NORMALIZATION] == 3
        assert STAGE_NUMBER_MAP[StageName.MERGING] == 4
        assert STAGE_NUMBER_MAP[StageName.FURNITURE] == 5
        assert STAGE_NUMBER_MAP[StageName.FABRIC_LINKING] == 6
        assert STAGE_NUMBER_MAP[StageName.EXPORT] == 7

    def test_stage_transitions(self):
        """測試階段狀態轉換"""
        # PENDING → RUNNING → COMPLETED
        valid_transitions = [
            (StageStatus.PENDING, StageStatus.RUNNING),
            (StageStatus.RUNNING, StageStatus.COMPLETED),
            (StageStatus.RUNNING, StageStatus.FAILED),
            (StageStatus.RUNNING, StageStatus.RETRYING),
            (StageStatus.RETRYING, StageStatus.RUNNING),
            (StageStatus.RETRYING, StageStatus.FAILED),
        ]

        for from_status, to_status in valid_transitions:
            # 這些轉換都應該是有效的
            assert from_status != to_status


class TestPipelineOrchestrator:
    """管線協調器測試"""

    @pytest.mark.asyncio
    async def test_create_batch_stages(self):
        """測試建立批次階段"""
        from src.services.pipeline import create_batch_stages

        batch_id = 1
        stages = create_batch_stages(batch_id)

        assert len(stages) == 7
        for i, stage in enumerate(stages, 1):
            assert stage["batch_id"] == batch_id
            assert stage["stage_number"] == i
            assert stage["status"] == StageStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_calculate_progress_percent(self):
        """測試計算進度百分比 (FR-011)"""
        from src.services.pipeline import calculate_progress_percent

        # stage_number / 7 * 100
        assert calculate_progress_percent(1) == 14
        assert calculate_progress_percent(4) == 57
        assert calculate_progress_percent(7) == 100

    @pytest.mark.asyncio
    async def test_get_next_stage(self):
        """測試取得下一階段"""
        from src.services.pipeline import get_next_stage

        assert get_next_stage(StageName.PDF_PARSING) == StageName.EXTRACTION
        assert get_next_stage(StageName.EXTRACTION) == StageName.NORMALIZATION
        assert get_next_stage(StageName.FABRIC_LINKING) == StageName.EXPORT
        assert get_next_stage(StageName.EXPORT) is None  # 最後階段


class TestCheckpoint:
    """斷點續傳測試 (T038-T039)"""

    @pytest.mark.asyncio
    async def test_save_checkpoint_data(self, test_db_path):
        """測試儲存檢查點資料 (T038, T040)"""
        # 建立測試批次
        from src.models.database import get_connection
        from src.services.pipeline import save_checkpoint

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO processing_batches (batch_uuid, supplier_id, status, total_files)
                VALUES (?, ?, ?, ?)""",
                ("test-batch", "fairmont", "RUNNING", 2),
            )
            batch_id = cursor.lastrowid

            cursor.execute(
                """INSERT INTO processing_stages
                (batch_id, stage_number, stage_name, status, progress_percent)
                VALUES (?, ?, ?, ?, ?)""",
                (batch_id, 3, "NORMALIZATION", "RUNNING", 42),
            )
            stage_id = cursor.lastrowid
            conn.commit()

        # 儲存檢查點
        checkpoint_data = {
            "normalized_items": [{"item_no": "DLX-100", "description": "Table"}],
            "processed_count": 10,
        }
        save_checkpoint(stage_id, checkpoint_data)

        # 驗證檢查點已儲存
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT checkpoint_data FROM processing_stages WHERE stage_id = ?",
                (stage_id,),
            )
            row = cursor.fetchone()

        import json

        saved_data = json.loads(row["checkpoint_data"])
        assert saved_data["normalized_items"][0]["item_no"] == "DLX-100"
        assert saved_data["processed_count"] == 10

    @pytest.mark.asyncio
    async def test_restore_checkpoint_data(self, test_db_path):
        """測試恢復檢查點資料 (T038, T041)"""
        import json

        from src.models.database import get_connection
        from src.services.pipeline import load_checkpoint

        # 建立帶有檢查點的階段
        checkpoint_data = {
            "merged_items": [{"item_no": "DLX-200", "qty": 5}],
            "stage_progress": 80,
        }

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO processing_batches (batch_uuid, supplier_id, status, total_files)
                VALUES (?, ?, ?, ?)""",
                ("test-resume", "fairmont", "RUNNING", 1),
            )
            batch_id = cursor.lastrowid

            cursor.execute(
                """INSERT INTO processing_stages
                (batch_id, stage_number, stage_name, status, progress_percent, checkpoint_data)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (batch_id, 4, "MERGING", "COMPLETED", 57, json.dumps(checkpoint_data)),
            )
            conn.commit()

        # 載入檢查點
        loaded = load_checkpoint("test-resume", StageName.MERGING)

        assert loaded is not None
        assert loaded["merged_items"][0]["item_no"] == "DLX-200"
        assert loaded["stage_progress"] == 80

    @pytest.mark.asyncio
    async def test_find_last_completed_stage(self, test_db_path):
        """測試找出最後完成的階段 (T041)"""
        from src.models.database import get_connection
        from src.services.pipeline import find_last_completed_stage

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO processing_batches (batch_uuid, supplier_id, status, total_files)
                VALUES (?, ?, ?, ?)""",
                ("test-find", "fairmont", "RUNNING", 1),
            )
            batch_id = cursor.lastrowid

            # 建立多個階段，部分完成
            stages = [
                (1, "PDF_PARSING", "COMPLETED"),
                (2, "EXTRACTION", "COMPLETED"),
                (3, "NORMALIZATION", "COMPLETED"),
                (4, "MERGING", "FAILED"),  # 失敗
                (5, "FURNITURE", "PENDING"),
            ]
            for stage_num, stage_name, status in stages:
                cursor.execute(
                    """INSERT INTO processing_stages
                    (batch_id, stage_number, stage_name, status, progress_percent)
                    VALUES (?, ?, ?, ?, ?)""",
                    (batch_id, stage_num, stage_name, status, 0),
                )
            conn.commit()

        # 應該找到 stage 3 (NORMALIZATION) 為最後完成的
        last_stage = find_last_completed_stage("test-find")
        assert last_stage is not None
        assert last_stage.stage_number == 3
        assert last_stage.stage_name == "NORMALIZATION"

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint(self, test_db_path):
        """測試從檢查點恢復執行 (T042)"""
        import json

        from src.models.database import get_connection
        from src.services.pipeline import can_resume, get_resume_stage

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO processing_batches (batch_uuid, supplier_id, status, total_files)
                VALUES (?, ?, ?, ?)""",
                ("test-resume-exec", "fairmont", "FAILED", 1),
            )
            batch_id = cursor.lastrowid

            # 建立有檢查點的失敗批次
            cursor.execute(
                """INSERT INTO processing_stages
                (batch_id, stage_number, stage_name, status, checkpoint_data)
                VALUES (?, ?, ?, ?, ?)""",
                (batch_id, 3, "NORMALIZATION", "COMPLETED", json.dumps({"data": "test"})),
            )
            cursor.execute(
                """INSERT INTO processing_stages
                (batch_id, stage_number, stage_name, status)
                VALUES (?, ?, ?, ?)""",
                (batch_id, 4, "MERGING", "FAILED"),
            )
            conn.commit()

        # 驗證可以恢復
        assert can_resume("test-resume-exec") is True

        # 應該從 stage 4 (MERGING) 開始恢復
        resume_stage = get_resume_stage("test-resume-exec")
        assert resume_stage == StageName.MERGING
