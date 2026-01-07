"""報價單處理 API 端點"""

import time
import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from src.api.deps import get_settings, is_sqlite_pipeline_enabled
from src.models.database import check_database_health, get_connection
from src.models.entities import STAGE_DISPLAY_NAME, TOTAL_STAGES, StageName
from src.models.schemas import (
    ErrorResponse,
    HealthResponse,
    QuoteItem,
    QuoteResponse,
    StatusResponse,
)
from src.services.cache import get_cache_service
from src.services.queue import get_queue_lock

router = APIRouter(tags=["quote"])


@router.post(
    "/quote/process",
    response_model=QuoteResponse,
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="處理 PDF 報價單",
    description="""
上傳多份 PDF 檔案，系統自動解析並返回 15 欄位報價單 JSON。

**支援的 PDF 類型**:
- 數量總表 (QUANTITY_SHEET)
- 明細規格表 (SPEC_SHEET)
- 面料表 (FABRIC_SHEET)
- Index 檔案 (INDEX)
    """,
)
async def process_pdf_quote(
    files: Annotated[list[UploadFile], File(description="上傳 PDF 檔案")],
    supplier_id: Annotated[
        str,
        Query(description="供應商識別符"),
    ] = "fairmont",
) -> QuoteResponse:
    """處理 PDF 報價單"""
    settings = get_settings()
    start_time = time.time()

    # 驗證檔案數量
    if len(files) > settings.max_upload_files:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_FILE_TYPE",
                message=f"上傳檔案數量超過限制 ({settings.max_upload_files})",
            ).model_dump(),
        )

    # 驗證檔案類型
    invalid_files = []
    for f in files:
        if not f.filename:
            invalid_files.append("未知檔案")
        elif not f.filename.lower().endswith(".pdf"):
            invalid_files.append(f.filename)

    if invalid_files:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_FILE_TYPE",
                message="上傳的檔案必須為 PDF 格式",
                details={"invalid_files": invalid_files},
            ).model_dump(),
        )

    # 檢查架構切換
    if not is_sqlite_pipeline_enabled():
        # 使用舊架構 (placeholder)
        raise HTTPException(
            status_code=501,
            detail=ErrorResponse(
                error_code="INTERNAL_ERROR",
                message="舊架構尚未實作",
            ).model_dump(),
        )

    # 檢查佇列鎖定
    queue_lock = get_queue_lock()
    batch_uuid = str(uuid.uuid4())

    async with queue_lock.acquire(batch_uuid) as acquired:
        if not acquired:
            current_batch = queue_lock.get_current_batch()
            raise HTTPException(
                status_code=409,
                detail=ErrorResponse(
                    error_code="BATCH_IN_QUEUE",
                    message="目前有其他批次正在處理中，請稍後再試",
                    details={"current_batch": current_batch},
                ).model_dump(),
            )

        # 讀取檔案內容
        file_contents: list[tuple[str, bytes]] = []
        raw_contents: list[bytes] = []
        for f in files:
            content = await f.read()
            file_contents.append((f.filename or "unknown.pdf", content))
            raw_contents.append(content)

        # 檢查快取 (T050, FR-009)
        cache_service = get_cache_service()
        is_cached, cache_path, cached_result = cache_service.check_cache(raw_contents)

        if is_cached and cached_result:
            processing_time_ms = int((time.time() - start_time) * 1000)
            # 將快取結果轉換為 QuoteResponse
            items = []
            for item_data in cached_result.get("items", []):
                items.append(QuoteItem(**item_data))
            return QuoteResponse(
                batch_id=cached_result.get("batch_id", batch_uuid),
                supplier_id=cached_result.get("supplier_id", supplier_id),
                status="completed",
                processing_time_ms=processing_time_ms,
                cached=True,
                items=items,
                errors=[],
            )

        # 執行管線處理
        from src.services.pipeline import run_pipeline

        try:
            result = await run_pipeline(batch_uuid, file_contents, supplier_id)

            # 儲存快取 (T049)
            cache_result = {
                "batch_id": result.batch_id,
                "supplier_id": result.supplier_id,
                "items": [item.model_dump() for item in result.items],
            }
            cache_service.save_cache(raw_contents, batch_uuid, cache_result)

            return result
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=ErrorResponse(
                    error_code="PROCESSING_FAILED",
                    message=f"處理失敗: {str(e)}",
                ).model_dump(),
            )


@router.get(
    "/quote/status/{batch_id}",
    response_model=StatusResponse,
    responses={
        404: {"model": ErrorResponse},
    },
    summary="查詢處理進度",
    description="""
查詢指定批次的處理進度。

**回應說明**:
- `current_stage`: 目前處理階段 (1-7)
- `progress_percent`: 總體進度百分比
- `stage_name`: 當前階段名稱
    """,
)
async def get_quote_status(batch_id: str) -> StatusResponse:
    """查詢處理進度"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 查詢批次
        cursor.execute(
            "SELECT * FROM processing_batches WHERE batch_uuid = ?",
            (batch_id,),
        )
        batch_row = cursor.fetchone()

        if not batch_row:
            raise HTTPException(
                status_code=404,
                detail=ErrorResponse(
                    error_code="BATCH_NOT_FOUND",
                    message="找不到指定的批次",
                ).model_dump(),
            )

        # 查詢最新階段
        cursor.execute(
            """
            SELECT * FROM processing_stages
            WHERE batch_id = ?
            ORDER BY stage_number DESC
            LIMIT 1
            """,
            (batch_row["batch_id"],),
        )
        stage_row = cursor.fetchone()

        # 建立回應
        status_map = {
            "PENDING": "pending",
            "RUNNING": "running",
            "COMPLETED": "completed",
            "FAILED": "failed",
        }

        current_stage = stage_row["stage_number"] if stage_row else None
        stage_name = None
        if stage_row:
            try:
                stage_enum = StageName(stage_row["stage_name"])
                stage_name = STAGE_DISPLAY_NAME.get(stage_enum, stage_row["stage_name"])
            except ValueError:
                stage_name = stage_row["stage_name"]

        progress_percent = 0
        if current_stage:
            progress_percent = int((current_stage / TOTAL_STAGES) * 100)

        return StatusResponse(
            batch_id=batch_id,
            supplier_id=batch_row["supplier_id"] or "fairmont",
            status=status_map.get(batch_row["status"], "pending"),
            current_stage=current_stage,
            total_stages=TOTAL_STAGES,
            stage_name=stage_name,
            progress_percent=progress_percent,
            started_at=batch_row["started_at"],
            estimated_completion=None,
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="健康檢查",
    description="檢查 API 服務狀態",
)
async def health_check() -> HealthResponse:
    """健康檢查"""
    settings = get_settings()
    db_health = check_database_health(settings.db_path)

    db_status_map = {
        "connected": "connected",
        "not_initialized": "not_initialized",
        "incomplete": "disconnected",
        "error": "disconnected",
    }

    return HealthResponse(
        status="healthy" if db_health["status"] == "connected" else "unhealthy",
        version="1.0.0",
        database=db_status_map.get(db_health["status"], "disconnected"),
    )
