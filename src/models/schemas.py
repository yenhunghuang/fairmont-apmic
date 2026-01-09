"""Pydantic Schemas for API Request/Response"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class QuoteItem(BaseModel):
    """17 欄位報價單項目 (符合 EXCEL_OUTPUT_SPECIFICATION.md)"""

    # 1-7: 核心解析欄位
    no: int = Field(..., description="序號")
    item_no: str = Field(..., description="項目編號 (如 DLX-100)")
    description: str | None = Field(None, description="品名描述")
    photo_base64: str | None = Field(None, description="產品圖片 (Base64 編碼)")
    dimension: str | None = Field(None, description="家具:尺寸; 面料:規格字串")
    qty: int | None = Field(None, description="數量 (面料留空)")
    uom: str | None = Field(None, description="單位 (ea/m)")

    # 8-12: 預留欄位 (空白，供採購填寫)
    unit_rate: float | None = Field(None, description="單價 (預留欄位)")
    amount: float | None = Field(None, description="總價 (預留欄位)")
    unit_cbm: float | None = Field(None, description="單位材積 (預留欄位)")
    total_cbm: float | None = Field(None, description="總材積 (預留欄位)")
    note: str | None = Field(None, description="備註 (預留欄位)")

    # 13-15: 元資料欄位
    location: str | None = Field(None, description="房型/位置 (@ 之後文字)")
    materials_used: str | None = Field(None, description="材料規格")
    brand: str | None = Field(None, description="品牌 (家具:Null, 面料:必填)")

    # 16-17: 分類與關聯欄位
    category: int = Field(..., description="產品分類 (1=家具, 5=面料)")
    affiliate: str | None = Field(None, description="所屬家具 (面料專用, 多個用 ', ' 分隔)")


class ItemError(BaseModel):
    """項目錯誤"""

    item_no: str | None = Field(None, description="發生錯誤的項目編號")
    error_code: str = Field(..., description="錯誤代碼")
    message: str = Field(..., description="錯誤訊息 (繁體中文)")


class QuoteResponse(BaseModel):
    """報價單處理回應"""

    batch_id: str = Field(..., description="批次識別符")
    supplier_id: str = Field(default="fairmont", description="使用的供應商適配器")
    status: Literal["completed", "failed"] = Field(..., description="處理狀態")
    processing_time_ms: int = Field(..., description="處理時間 (毫秒)")
    cached: bool = Field(default=False, description="是否為快取結果")
    items: list[QuoteItem] = Field(default_factory=list, description="報價單項目列表")
    errors: list[ItemError] = Field(default_factory=list, description="處理錯誤列表")


class StatusResponse(BaseModel):
    """處理進度回應"""

    batch_id: str = Field(..., description="批次識別符")
    supplier_id: str = Field(default="fairmont", description="使用的供應商適配器")
    status: Literal["pending", "running", "completed", "failed"] = Field(
        ..., description="批次狀態"
    )
    current_stage: int | None = Field(None, ge=1, le=7, description="當前階段編號")
    total_stages: int = Field(default=7, description="總階段數")
    stage_name: str | None = Field(None, description="當前階段名稱 (繁體中文)")
    progress_percent: int = Field(default=0, ge=0, le=100, description="總體進度百分比")
    started_at: datetime | None = Field(None, description="開始處理時間")
    estimated_completion: datetime | None = Field(None, description="預估完成時間")


class ErrorResponse(BaseModel):
    """錯誤回應"""

    error_code: Literal[
        "INVALID_FILE_TYPE",
        "FILE_TOO_LARGE",
        "PROCESSING_FAILED",
        "BATCH_NOT_FOUND",
        "DATABASE_ERROR",
        "LLM_ERROR",
        "INTERNAL_ERROR",
        "BATCH_IN_QUEUE",
    ] = Field(..., description="錯誤代碼")
    message: str = Field(..., description="錯誤訊息 (繁體中文)")
    details: dict | None = Field(None, description="額外錯誤詳情")


class HealthResponse(BaseModel):
    """健康檢查回應"""

    status: Literal["healthy", "unhealthy"] = Field(..., description="服務狀態")
    version: str = Field(default="1.0.0", description="API 版本")
    database: Literal["connected", "disconnected", "not_initialized"] = Field(
        ..., description="資料庫狀態"
    )
