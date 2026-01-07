# Quickstart: 地端 SQLite 多階段 PDF 報價單處理系統

## 環境需求

- Python >= 3.11
- Windows 10/11 (地端部署)
- 8GB+ RAM (建議)
- 10GB+ 可用磁碟空間

## 快速開始

### 1. 安裝依賴

```powershell
# 建立虛擬環境
python -m venv venv
.\venv\Scripts\Activate.ps1

# 安裝依賴
pip install -r requirements.txt
```

### 2. 環境設定

```powershell
# 複製範例環境變數
copy .env.example .env

# 編輯 .env 設定 (如需要)
```

**環境變數說明**:
| 變數 | 預設值 | 說明 |
|------|--------|------|
| `DATABASE_PATH` | `data/fairmont.db` | SQLite 資料庫路徑 |
| `USE_SQLITE_PIPELINE` | `true` | 使用新架構 |
| `CACHE_TTL_DAYS` | `1` | 快取保留天數 |
| `MAX_UPLOAD_FILES` | `20` | 最大上傳檔案數 |

### 3. 初始化資料庫

```powershell
# 自動建立資料庫與索引
python -m src.models.database init
```

### 4. 啟動服務

```powershell
# 開發模式 (自動重載)
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# 生產模式
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 2
```

### 5. 測試 API (Swagger)

開啟瀏覽器訪問：**http://localhost:8000/docs**

#### 使用 Swagger 上傳 PDF
1. 展開 `POST /api/v1/quote/process`
2. 點擊「Try it out」
3. 點擊「Choose File」選擇多個 PDF
4. 點擊「Execute」
5. 查看 JSON 回應

#### 使用 cURL 測試

```powershell
# 上傳 PDF 處理
curl -X POST "http://localhost:8000/api/v1/quote/process" \
  -H "accept: application/json" \
  -F "files=@quantity_sheet.pdf" \
  -F "files=@spec_sheet.pdf" \
  -F "files=@fabric.pdf"

# 查詢進度
curl -X GET "http://localhost:8000/api/v1/quote/status/{batch_id}"

# 健康檢查
curl -X GET "http://localhost:8000/api/v1/health"
```

## API 端點

| Method | Path | 說明 |
|--------|------|------|
| POST | `/api/v1/quote/process` | 上傳 PDF 並處理 |
| GET | `/api/v1/quote/status/{batch_id}` | 查詢處理進度 |
| GET | `/api/v1/health` | 健康檢查 |
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc 文件 |

## 回應格式範例

### 成功回應

```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "processing_time_ms": 12345,
  "cached": false,
  "items": [
    {
      "no": 1,
      "item_no": "DLX-100",
      "description": "Bedside Table",
      "photo_base64": "data:image/png;base64,...",
      "dimension": "600 x 450 x 550",
      "qty": 10,
      "uom": "ea",
      "materials_used": "Solid Oak, Lacquered Finish",
      "location": "Deluxe Room",
      "note": "",
      "brand": "Custom Furniture Co.",
      "unit_rate": null,
      "amount": null,
      "cbm": null,
      "total_cbm": null
    }
  ],
  "errors": []
}
```

### 錯誤回應

```json
{
  "error_code": "INVALID_FILE_TYPE",
  "message": "上傳的檔案必須為 PDF 格式",
  "details": {
    "invalid_files": ["document.docx"]
  }
}
```

## 執行測試

```powershell
# 執行所有測試
pytest

# 執行單元測試
pytest tests/unit/ -v

# 執行整合測試
pytest tests/integration/ -v

# 檢查覆蓋率
pytest --cov=src --cov-report=html
```

## 專案結構

```
src/
├── api/
│   ├── main.py           # FastAPI 入口
│   └── routes/quote.py   # 報價單端點
├── models/
│   ├── database.py       # SQLite 連線
│   ├── schemas.py        # Pydantic schemas
│   └── entities.py       # 資料庫實體
├── services/
│   ├── pdf_parser.py     # PDF 解析
│   ├── pipeline.py       # 多階段管線
│   └── cache.py          # 快取服務
└── utils/
    └── item_normalizer.py # Item No. 正規化

tests/
├── unit/                 # 單元測試
└── integration/          # 整合測試

data/
└── fairmont.db          # SQLite 資料庫
```

## 疑難排解

### 常見錯誤

**Q: 「資料庫被鎖定」錯誤**
```
sqlite3.OperationalError: database is locked
```
A: 確認沒有其他程序正在存取資料庫，或增加 `busy_timeout` 設定。

**Q: PDF 解析失敗**
```
"error_code": "PROCESSING_FAILED"
```
A: 確認 PDF 檔案未損壞，且為標準 PDF 格式。

**Q: 快取未命中**
A: 確認檔案內容完全相同（SHA256 雜湊一致）。

### 日誌查看

```powershell
# 檢查應用程式日誌
type logs\app.log

# 即時查看日誌
Get-Content logs\app.log -Wait
```

## 下一步

- 詳細 API 規範：`contracts/openapi.yaml`
- 資料模型說明：`data-model.md`
- 研究決策紀錄：`research.md`
