# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

地端 SQLite 多階段 PDF 報價單處理系統。接受多份供應商 PDF 上傳，透過 7 階段管線處理，輸出符合 Fairmont 格式的 15 欄位 JSON 報價單。

## 常用指令

```powershell
# 安裝依賴
pip install -r requirements.txt

# 啟動開發伺服器
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000

# 執行所有測試
pytest

# 執行單一測試檔案
pytest tests/unit/test_pipeline.py -v

# 執行符合特定名稱的測試
pytest -k "test_normalization" -v

# 覆蓋率報告
pytest --cov=src --cov-report=html

# 格式化
black src tests
ruff check src tests --fix
```

## 架構

### 7 階段處理管線 (`src/services/pipeline.py`)

```
PDF_PARSING → EXTRACTION → NORMALIZATION → MERGING → FURNITURE → FABRIC_LINKING → EXPORT
    1             2            3             4           5             6            7
```

- **Stage 1**: PDF 解析 (pdfplumber + PyMuPDF)
- **Stage 2**: LLM 資料擷取 + Index PDF Location 提取
- **Stage 3**: Item No. 正規化 (去空格、統一破折號)
- **Stage 4**: 合併數量總表 + location_map (qty 以數量總表為準)
- **Stage 5**: 家具項目處理
- **Stage 6**: 面料關聯 (從面料 PDF 提取 has_repeat 等欄位)
- **Stage 7**: 匯出 15 欄位 JSON (Fabric-Follows-Furniture 排序)

### 家具 vs 面料處理差異

| 欄位 | 家具 | 面料 |
|------|------|------|
| Description | 原始描述 | `{brand} to {furniture_item_no}` |
| Dimension | `W{w} x D{d} x H{h} mm` | `{材質}-{供應商}-{品牌}-{花色}-{寬度} pattern/plain` |
| Qty | 數量總表優先 | 留空 |
| Brand | **強制 Null** | **必填** |
| Location | Index PDF `@` 後文字 | description `@` 後文字 |

詳見 `docs/EXCEL_OUTPUT_SPECIFICATION.md`

### 核心元件

- **Pipeline** (`src/services/pipeline.py`): 主要處理邏輯，checkpoint 機制支援斷點續傳
- **Adapters** (`src/services/adapters/`): 供應商適配器 (Fairmont/Generic)
- **Queue Lock** (`src/services/queue.py`): 確保一次只處理一個批次
- **Cache Service** (`src/services/cache.py`): 相同 Hash 檔案返回快取
- **LLM Client** (`src/services/llm_client.py`): 分塊策略保持 Prompt < 2K tokens

### 資料流

```
UploadFile[] → detect_file_role() → Pipeline.run() → QuoteResponse
                     ↓                    ↓
              FileRole enum         SQLite checkpoint
           (QUANTITY_SHEET,         (processing_stages)
            SPEC_SHEET,
            FABRIC_SHEET,
            INDEX)
```

### 狀態管理 (`src/models/entities.py`)

- `BatchStatus`: PENDING → RUNNING → COMPLETED/FAILED
- `StageStatus`: PENDING → RUNNING → COMPLETED/FAILED/RETRYING
- `StageName`: 7 階段 enum

## 關鍵環境變數

```
USE_SQLITE_PIPELINE=true   # 啟用新架構
DATABASE_PATH=data/fairmont.db
OPENAI_API_KEY=...         # LLM API 金鑰 (APMIC API)
```

## 測試

測試使用臨時 SQLite 資料庫，在 `tests/conftest.py` 中自動設定。fixtures:
- `test_db_path`: 臨時資料庫路徑
- `test_client`: FastAPI TestClient
- `mock_batch_uuid`: 固定 UUID 供測試用

## 功能規格

- 規格: `specs/001-sqlite-pipeline-quote/spec.md`
- 輸出規格: `docs/EXCEL_OUTPUT_SPECIFICATION.md`
- 資料模型: `specs/001-sqlite-pipeline-quote/data-model.md`
