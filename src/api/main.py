"""FastAPI 應用程式入口"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.deps import get_settings
from src.api.routes import quote
from src.models.database import check_database_health, init_database
from src.models.schemas import ErrorResponse
from src.utils.logger import setup_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """應用程式生命週期事件"""
    settings = get_settings()
    logger = setup_logger(
        "fairmont",
        level=settings.log_level,
        log_file=settings.log_file,
    )

    # 啟動時初始化
    logger.info("正在初始化應用程式...")

    # 初始化資料庫
    try:
        init_database(settings.db_path)
        health = check_database_health(settings.db_path)
        logger.info(f"資料庫狀態: {health['status']}")
    except Exception as e:
        logger.error(f"資料庫初始化失敗: {e}")

    # 啟動時清理過期快取 (T052, FR-021)
    try:
        from src.services.cache import cleanup_expired_cache

        deleted_count = cleanup_expired_cache()
        if deleted_count > 0:
            logger.info(f"已清理 {deleted_count} 筆過期快取")
    except Exception as e:
        logger.warning(f"快取清理失敗: {e}")

    logger.info("應用程式已啟動")

    yield

    # 關閉時清理
    logger.info("應用程式正在關閉...")


# 建立 FastAPI 應用程式
app = FastAPI(
    title="Fairmont PDF 報價單處理 API",
    description="""
地端 SQLite 多階段 PDF 報價單處理系統。

## 功能說明
- 上傳多份 PDF 檔案（家具規格書、數量總表、面料表、Index）
- 自動解析並產出符合惠而蒙 (Fairmont) 格式的 15 欄位報價單 JSON
- 支援快取機制，相同檔案秒級回應

## 使用 Swagger 測試
1. 點擊「Try it out」
2. 選擇多個 PDF 檔案上傳
3. 執行後查看 JSON 回應
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 錯誤處理
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """處理 ValueError"""
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error_code="INVALID_FILE_TYPE",
            message=str(exc),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """處理一般例外"""
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="發生內部錯誤，請稍後再試",
            details={"error": str(exc)},
        ).model_dump(),
    )


# 註冊路由
app.include_router(quote.router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
