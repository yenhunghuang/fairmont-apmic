"""舊架構管線處理 (T063 - Placeholder)

當 USE_SQLITE_PIPELINE=false 時使用此模組。
目前僅為 placeholder，實際實作保留給未來需求。
"""

from src.models.schemas import QuoteResponse


async def run_legacy_pipeline(
    batch_uuid: str,
    files: list[tuple[str, bytes]],
    supplier_id: str = "fairmont",
) -> QuoteResponse:
    """執行舊架構管線處理

    Args:
        batch_uuid: 批次 UUID
        files: 檔案列表 (檔名, 內容)
        supplier_id: 供應商 ID

    Returns:
        處理結果

    Raises:
        NotImplementedError: 舊架構尚未實作
    """
    raise NotImplementedError("舊架構尚未實作，請設定 USE_SQLITE_PIPELINE=true 使用新架構")
