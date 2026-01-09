# SQLite 多階段 PDF 報價單處理系統架構文件

**版本**: 1.0
**日期**: 2026-01-08
**專案**: Fairmont APMIC Quote Processing System

---

## 目錄

1. [系統概覽](#1-系統概覽)
2. [架構設計](#2-架構設計)
3. [數據流與處理管線](#3-數據流與處理管線)
4. [API 設計](#4-api-設計)
5. [資料模型](#5-資料模型)
6. [關鍵設計決策](#6-關鍵設計決策)
7. [可擴展性與效能考量](#7-可擴展性與效能考量)
8. [錯誤處理與重試機制](#8-錯誤處理與重試機制)
9. [部署與維運](#9-部署與維運)

---

## 1. 系統概覽

### 1.1 系統目的

本系統為**地端 (On-Premise) 運行的家具報價單自動化處理系統**，專為惠而蒙 (Fairmont) 供應商報價單設計。核心目標是將供應商提供的多份 PDF 檔案（家具規格書、數量總表、面料表、Index）自動解析並轉換為標準化的 17 欄位 Excel 報價單，大幅減少人工處理時間。

### 1.2 核心價值

- **自動化解析**: 使用 LLM (Large Language Model) 擷取 PDF 中的結構化資料
- **彈性處理**: 支援多種 PDF 格式與供應商變化
- **容錯機制**: 斷點續傳 (Checkpoint) 與快取 (Cache) 確保處理穩定性
- **地端運行**: 資料不離開本地環境，滿足安全合規需求
- **輕量設計**: 使用 SQLite + 輕量 LLM (Gemma-3-12b)，適合資源受限環境

### 1.3 主要功能特性

| 功能 | 說明 |
|------|------|
| **7 階段管線** | PDF 解析 → 資料擷取 → 正規化 → 合併 → 家具處理 → 面料關聯 → 匯出 |
| **檔案角色偵測** | 自動識別數量總表、規格表、面料表、Index |
| **斷點續傳** | 每階段完成後儲存 checkpoint，失敗後可從斷點恢復 |
| **智慧快取** | 相同檔案內容返回快取結果 (TTL 1 天) |
| **並發控制** | Queue Lock 確保同一時間只處理一個批次 |
| **LLM 分塊策略** | 將大 PDF 內容分割成 2K tokens 以內的 chunks，避免 Context Window 限制 |
| **圖片去重** | 從 ATTACHMENT 頁面提取產品主圖，去重選擇最佳解析度 |

### 1.4 技術棧

| 層級 | 技術選型 | 用途 |
|------|----------|------|
| **API 框架** | FastAPI 0.115.6 | RESTful API 服務 |
| **資料庫** | SQLite 3 (WAL mode) | 輕量級持久化儲存 |
| **PDF 處理** | pdfplumber + PyMuPDF | 文字/圖片擷取 |
| **LLM** | APMIC API (Gemma-3-12b) | 結構化資料擷取 |
| **語言** | Python 3.11+ | 主要開發語言 |
| **Schema 驗證** | Pydantic 2.10.5 | API 請求/回應驗證 |

---

## 2. 架構設計

### 2.1 整體架構圖

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Layer (FastAPI)                       │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                │
│  │ POST       │  │ GET        │  │ GET        │                │
│  │ /process   │  │ /status    │  │ /health    │                │
│  └────────────┘  └────────────┘  └────────────┘                │
└────────────┬────────────────────────────┬───────────────────────┘
             │                            │
             ▼                            ▼
┌─────────────────────────┐  ┌────────────────────────┐
│   Queue Lock Service    │  │   Cache Service        │
│   (並發控制)             │  │   (SHA256 Hash)        │
└────────────┬────────────┘  └────────────┬───────────┘
             │                            │
             ▼                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Pipeline Orchestrator (7 Stages)               │
│                                                                   │
│  Stage 1: PDF_PARSING     ────→  FileRole Detection             │
│  Stage 2: EXTRACTION      ────→  LLM Client (Chunked)           │
│  Stage 3: NORMALIZATION   ────→  Item No. Normalizer            │
│  Stage 4: MERGING         ────→  Quantity + Location Merge      │
│  Stage 5: FURNITURE       ────→  Furniture Filter                │
│  Stage 6: FABRIC_LINKING  ────→  Furniture-Fabric Mapping       │
│  Stage 7: EXPORT          ────→  15-Column JSON Output          │
│                                                                   │
│  每階段完成 → Checkpoint 存入 SQLite                              │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SQLite Database (WAL Mode)                  │
│                                                                   │
│  Tables:                                                         │
│  - processing_batches    (批次狀態管理)                          │
│  - processing_stages     (階段進度追蹤)                          │
│  - uploaded_files        (檔案元資料)                            │
│  - furniture_items       (家具項目)                              │
│  - fabric_items          (面料項目)                              │
│  - cache_records         (快取記錄)                              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 分層架構說明

#### Layer 1: API 層 (Presentation)
- **職責**: HTTP 請求處理、參數驗證、回應序列化
- **核心檔案**: `src/api/routes/quote.py`, `src/api/main.py`
- **關鍵功能**:
  - FastAPI 路由定義
  - OpenAPI 文件自動生成
  - Pydantic Schema 驗證

#### Layer 2: 服務層 (Business Logic)
- **職責**: 核心業務邏輯、狀態管理、外部服務整合
- **核心檔案**:
  - `src/services/pipeline.py` - 主要處理管線
  - `src/services/queue.py` - 並發控制
  - `src/services/cache.py` - 快取服務
  - `src/services/llm_client.py` - LLM 呼叫封裝
  - `src/services/pdf_parser.py` - PDF 解析

#### Layer 3: 資料存取層 (Data Access)
- **職責**: 資料庫連線、CRUD 操作、事務管理
- **核心檔案**: `src/models/database.py`, `src/models/entities.py`

#### Layer 4: 工具層 (Utilities)
- **職責**: 共用函式、資料轉換、格式化
- **核心檔案**:
  - `src/utils/item_normalizer.py` - Item No. 正規化
  - `src/utils/fabric_formatter.py` - 面料欄位格式化
  - `src/utils/logger.py` - 日誌記錄

### 2.3 核心元件職責

| 元件 | 職責 | 關鍵方法 |
|------|------|----------|
| **Pipeline** | 管線編排、階段執行、Checkpoint 管理 | `run()`, `_stage_*()` |
| **QueueLock** | 並發控制、批次佇列管理 | `acquire()`, `is_locked()` |
| **CacheService** | 快取檢查、快取儲存、過期清理 | `check_cache()`, `save_cache()` |
| **LLMClient** | LLM 呼叫、分塊策略、重試邏輯 | `call_chunked()`, `call_with_retry()` |
| **PdfParser** | PDF 文字/圖片擷取、檔案角色偵測 | `extract_text_from_bytes()`, `extract_attachment_images()` |

---

## 3. 數據流與處理管線

### 3.1 完整數據流

```
[使用者上傳 PDF]
       │
       ▼
[API: POST /quote/process]
       │
       ├─→ [檔案驗證: PDF 格式、數量限制]
       │
       ├─→ [Queue Lock 檢查: 是否有批次執行中]
       │
       ├─→ [快取檢查: SHA256 Hash → 若命中直接返回]
       │
       ▼
[Pipeline.run() 啟動]
       │
       ├─→ Stage 1: PDF_PARSING
       │   ├─ 使用 pdfplumber 擷取文字
       │   ├─ 使用 PyMuPDF 擷取圖片
       │   ├─ detect_file_role() 判斷檔案類型
       │   └─ 從 ATTACHMENT 頁面提取產品主圖
       │
       ├─→ Stage 2: EXTRACTION
       │   ├─ 規格表: LLM 擷取 item_no, description, dimension, materials
       │   ├─ Index: LLM 擷取 location_map (item_no → location)
       │   └─ 分塊策略: 每 2K tokens 一個 chunk
       │
       ├─→ Stage 3: NORMALIZATION
       │   ├─ 正規化 Item No. (去空格、統一破折號)
       │   └─ normalize_item_no(): "DLX-201 .1" → "DLX-201.1"
       │
       ├─→ Stage 4: MERGING
       │   ├─ 數量總表: LLM 擷取 qty_map
       │   ├─ 按 item_no 去重 (保留資訊最完整版本)
       │   ├─ 合併數量: qty 以數量總表為準 (FR-006)
       │   └─ 合併位置: location 從 Index PDF 提取
       │
       ├─→ Stage 5: FURNITURE
       │   └─ 過濾非面料項目 (Item No. 非 500 系列)
       │
       ├─→ Stage 6: FABRIC_LINKING
       │   ├─ 面料表: LLM 擷取 brand, pattern, color, width, content, abrasion
       │   ├─ 解析 furniture_com 欄位 (關聯家具編號)
       │   └─ 建立 furniture_to_fabrics 映射
       │
       └─→ Stage 7: EXPORT
           ├─ Fabric-Follows-Furniture 排序
           ├─ 格式化家具項目 (brand = null)
           ├─ 格式化面料項目 (dimension 為規格字串)
           └─ 輸出 17 欄位 JSON
       │
       ▼
[儲存快取 → 返回 QuoteResponse]
```

### 3.2 七階段處理詳解

#### Stage 1: PDF_PARSING (PDF 解析)

**目的**: 將 PDF 轉換為可處理的文字與圖片資料

**輸入**:
- 原始 PDF 檔案 (bytes)

**輸出**:
```python
{
    "filename": "Casegoods & Seatings.pdf",
    "role": FileRole.SPEC_SHEET,
    "text": "ITEM NO.: DLX-100\nITEM: King Bed\n...",
    "images": [...],  # 傳統方法擷取的圖片
    "content": bytes,  # 原始內容供 ATTACHMENT 提取使用
}
```

**關鍵技術**:
- **文字擷取**: pdfplumber (保留排版資訊)
- **圖片擷取**: PyMuPDF (支援多種圖片格式)
- **ATTACHMENT 提取**:
  - 定位 "ATTACHMENT" 頁面
  - 使用 `find_largest_content_region()` 尋找產品主圖
  - 裁切並儲存最高解析度版本

**檔案角色偵測邏輯**:
```python
優先順序: 檔名關鍵字 → 內容關鍵字 → 預設 SPEC_SHEET

數量總表: "qty", "quantity", "overall"
面料表: "fabric" AND "leather" (排他)
Index: "index"
規格表: "casegood", "seating", "furniture", "spec"
```

---

#### Stage 2: EXTRACTION (資料擷取)

**目的**: 使用 LLM 從 PDF 文字中擷取結構化資料

**輸入**:
- Stage 1 解析的文字內容

**輸出**:
```python
# 規格表項目
[
    {
        "item_no": "DLX-100",
        "description": "King Bed",
        "dimension": "L2130 x W1930 x HT290mm",
        "uom": "ea",
        "materials": "10mm THK Rebonded FR Foam",
        "brand": null
    },
    ...
]

# Location 映射 (從 Index 提取)
{
    "DLX-100": "King Deluxe Room Type A / King Deluxe Room Type B / ...",
    "DLX-104": "Grand King Deluxe Room Type A / Grand King Deluxe Room Type B / ...",
    ...
}
```

**LLM Prompt 範例** (規格表):
```
你是專業的家具報價單解析助手。
從 PDF 內容中提取所有家具項目。

只輸出 JSON 陣列，格式：
[{
  "item_no": "DLX-100",
  "description": "King Bed",
  "dimension": "L2130 x W1930 x HT290mm",
  "uom": "ea",
  "materials": "10mm THK Rebonded FR Foam",
  "brand": null
}, ...]

欄位說明：
- dimension: 從 "Overall Dimensions" 欄位提取，只取尺寸數值部分
- materials: 從 DESCRIPTION 中的材質/規格說明
- brand: 家具通常為 null
```

**分塊策略** (FR-010):
- 每個 chunk 最多 2000 tokens (約 4000 字元)
- 在段落邊界分割，保持語意完整性
- 多個 chunk 的 JSON 回應自動合併

---

#### Stage 3: NORMALIZATION (正規化)

**目的**: 統一 Item No. 格式，避免合併失敗

**輸入**:
- Stage 2 擷取的原始項目

**輸出**:
- Item No. 正規化後的項目

**正規化規則**:
```python
normalize_item_no("DLX-201 .1")   # → "DLX-201.1"
normalize_item_no("DLX‐100")      # → "DLX-100" (統一破折號)
normalize_item_no(" DLX-100 ")   # → "DLX-100" (去空格)
```

**支援的 Unicode 破折號** (10+ 種):
- U+002D (Hyphen-Minus)
- U+2010 (Hyphen)
- U+2011 (Non-Breaking Hyphen)
- U+2012 (Figure Dash)
- U+2013 (En Dash)
- U+2014 (Em Dash)
- ... 等

---

#### Stage 4: MERGING (資料合併)

**目的**: 合併數量總表、規格表、Index 的資料，去重並填補欄位

**輸入**:
- Stage 3 正規化的項目
- 數量總表 (qty_map)
- Index (location_map)

**輸出**:
- 合併且去重後的項目 (以 item_no 為 key)

**合併邏輯** (FR-006):
```python
# 按 item_no 去重
for item in normalized_items:
    item_no = item["item_no"]
    if item_no not in item_map:
        item_map[item_no] = item  # 首次出現
    else:
        # 重複項目：保留非空值，優先保留資訊更完整的版本
        existing = item_map[item_no]
        for key, value in item.items():
            if value and not existing.get(key):
                existing[key] = value

# 合併數量 (以數量總表為準)
if item_no in qty_map:
    merged["qty"] = qty_map[item_no]

# 合併位置 (從 Index 提取)
if item_no in location_map:
    merged["location"] = location_map[item_no]
```

---

#### Stage 5: FURNITURE (家具擷取)

**目的**: 分離家具項目與面料項目

**輸入**:
- Stage 4 合併的項目

**輸出**:
- furniture_items (非 500 系列)
- fabric_items (500 系列，留待 Stage 6 處理)

**判斷邏輯**:
```python
def is_fabric_item(item_no: str) -> bool:
    """判斷是否為面料項目 (500-599 系列)"""
    match = re.search(r'\d{3}', item_no)
    if match:
        number = int(match.group())
        return 500 <= number < 600
    return False
```

---

#### Stage 6: FABRIC_LINKING (面料關聯)

**目的**: 從面料 PDF 擷取面料資訊，並建立與家具的關聯

**輸入**:
- 面料 PDF 檔案
- Stage 5 的 furniture_items

**輸出**:
```python
[
    {
        "item_no": "DLX-505",
        "description": "Fabric @ DLX-102 and DLX-106 Sofa",
        "vendor": "Sankon Interior Limited",
        "brand": "Bravo Collection",
        "pattern": "BV106-05M084C",
        "color": "Cream",
        "width": "140 cm",
        "content": "55% cotton, 40% viscose, 5% linen",
        "abrasion": "40,000 Double Rubs",
        "fire_rating": "NFPA 260, Class 1",
        "horizontal_repeat": "14cm",
        "vertical_repeat": "16cm",
        "furniture_com": "DLX-102 AND DLX-106",  # 關聯家具編號
        "has_repeat": false
    },
    ...
]
```

**furniture_to_fabrics 映射**:
```python
{
    "DLX-102": [fabric_505, fabric_506, ...],
    "DLX-106": [fabric_505, ...],
    ...
}
```

**孤立面料處理**:
- 若 furniture_com 為空 → 孤立面料
- 若 furniture_com 對應的家具不在 furniture_items 中 → 孤立面料
- 孤立面料會在 Stage 7 末尾輸出

---

#### Stage 7: EXPORT (匯出)

**目的**: 產生符合 Fairmont 17 欄位規範的 JSON 輸出

**輸入**:
- Stage 5 的 furniture_items
- Stage 6 的 fabric_items
- furniture_to_fabrics 映射

**輸出**:
```python
QuoteResponse(
    batch_id="uuid",
    supplier_id="fairmont",
    status="completed",
    items=[
        QuoteItem(no=1, item_no="DLX-100", ...),  # 家具
        QuoteItem(no=2, item_no="DLX-505", ...),  # 面料 (緊跟家具)
        QuoteItem(no=3, item_no="DLX-506", ...),  # 面料 (緊跟家具)
        QuoteItem(no=4, item_no="DLX-102", ...),  # 家具
        ...
    ]
)
```

**Fabric-Follows-Furniture 排序**:
```python
seq_no = 1
for furniture in furniture_items:
    # 1. 輸出家具
    result.append(format_furniture_item(furniture, seq_no))
    seq_no += 1

    # 2. 輸出關聯面料
    for fabric in furniture_to_fabrics.get(furniture.item_no, []):
        result.append(format_fabric_item(fabric, seq_no))
        seq_no += 1

# 3. 輸出孤立面料
for fabric in orphan_fabrics:
    result.append(format_fabric_item(fabric, seq_no))
    seq_no += 1
```

**家具 vs 面料格式化差異**:

| 欄位 | 家具 | 面料 |
|------|------|------|
| **Description** | 原始描述 | `{material_type} to {furniture_item_no}` |
| **Dimension** | `W{w} x D{d} x H{h} mm` | `{Content}-{Vendor}-{Brand}-{Pattern}-{Width} pattern/plain` |
| **Qty** | 數量總表優先 | 留空 |
| **Brand** | **強制 Null** (OEM) | **必填** |
| **Location** | Index PDF `@` 後文字 | description `@` 後文字 (關聯家具編號) |
| **Materials Used** | 原始材質規格描述 | `Pattern: {pattern}. Color: {color}. Rub Test: {abrasion}\nFire Rating: {fire_rating}` |

### 3.3 Checkpoint 機制

**目的**: 支援斷點續傳，避免失敗後從頭開始

**實作方式**:
1. 每階段完成後，將中間結果序列化為 JSON 儲存至 `processing_stages.checkpoint_data`
2. 批次失敗後，使用者重新啟動系統
3. 系統檢查 `can_resume(batch_uuid)` → 若批次狀態為 FAILED，則可恢復
4. `get_resume_stage(batch_uuid)` 找出第一個失敗或待處理的階段
5. `load_checkpoint(batch_uuid, stage_name)` 載入該階段的中間結果
6. Pipeline 從該階段繼續執行

**Checkpoint 資料範例**:
```python
# Stage 3 checkpoint
{
    "normalized_items": [
        {"item_no": "DLX-100", "description": "King Bed", ...},
        {"item_no": "DLX-102", "description": "L-Shaped Sofa", ...},
    ]
}

# Stage 4 checkpoint
{
    "merged_items": [...],
    "location_map": {"DLX-100": "King Deluxe Room Type A", ...}
}
```

---

## 4. API 設計

### 4.1 RESTful 端點

#### POST /api/v1/quote/process

**用途**: 上傳 PDF 檔案並啟動處理管線

**請求格式**:
```http
POST /api/v1/quote/process?supplier_id=fairmont&include_images=false
Content-Type: multipart/form-data

files: [file1.pdf, file2.pdf, ...]
```

**Query Parameters**:
| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `supplier_id` | string | "fairmont" | 供應商識別符 |
| `include_images` | boolean | false | 是否返回 base64 圖片 (設為 false 可減少回應大小) |

**成功回應** (200 OK):
```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "supplier_id": "fairmont",
  "status": "completed",
  "processing_time_ms": 45000,
  "cached": false,
  "items": [
    {
      "no": 1,
      "item_no": "DLX-100",
      "description": "King Bed",
      "photo_base64": "data:image/png;base64,iVBORw0KGgoAAAA...",
      "dimension": "L2130 x W1930 x HT290mm",
      "qty": 10,
      "uom": "ea",
      "unit_rate": null,
      "amount": null,
      "unit_cbm": null,
      "total_cbm": null,
      "note": null,
      "location": "King Deluxe Room Type A / King Deluxe Room Type B",
      "materials_used": "10mm THK Rebonded FR Foam",
      "brand": null
    },
    {
      "no": 2,
      "item_no": "DLX-505",
      "description": "Fabric to DLX-102 AND DLX-106",
      "photo_base64": null,
      "dimension": "55% cotton-Sankon Interior Limited-Bravo Collection-BV106-05M084C-140 cm plain",
      "qty": null,
      "uom": "m",
      "unit_rate": null,
      "amount": null,
      "unit_cbm": null,
      "total_cbm": null,
      "note": null,
      "location": "DLX-102 AND DLX-106",
      "materials_used": "Pattern: BV106-05M084C. Color: Cream. Rub Test: 40,000 Double Rubs\nFire Rating: NFPA 260, Class 1",
      "brand": "Bravo Collection"
    }
  ],
  "errors": []
}
```

**錯誤回應**:

- **400 Bad Request**: 檔案格式錯誤、數量超過限制
```json
{
  "error_code": "INVALID_FILE_TYPE",
  "message": "上傳的檔案必須為 PDF 格式",
  "details": {
    "invalid_files": ["image.jpg"]
  }
}
```

- **409 Conflict**: 有其他批次正在處理中
```json
{
  "error_code": "BATCH_IN_QUEUE",
  "message": "目前有其他批次正在處理中，請稍後再試",
  "details": {
    "current_batch": "550e8400-e29b-41d4-a716-446655440001"
  }
}
```

- **422 Unprocessable Entity**: 處理失敗
```json
{
  "error_code": "PROCESSING_FAILED",
  "message": "處理失敗: LLM 呼叫逾時"
}
```

---

#### GET /api/v1/quote/status/{batch_id}

**用途**: 查詢批次處理進度

**請求格式**:
```http
GET /api/v1/quote/status/550e8400-e29b-41d4-a716-446655440000
```

**成功回應** (200 OK):
```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "supplier_id": "fairmont",
  "status": "running",
  "current_stage": 4,
  "total_stages": 7,
  "stage_name": "資料合併中",
  "progress_percent": 57,
  "started_at": "2026-01-08T10:30:00Z",
  "estimated_completion": null
}
```

**錯誤回應**:

- **404 Not Found**: 批次不存在
```json
{
  "error_code": "BATCH_NOT_FOUND",
  "message": "找不到指定的批次"
}
```

---

#### GET /api/v1/health

**用途**: 健康檢查

**請求格式**:
```http
GET /api/v1/health
```

**成功回應** (200 OK):
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected"
}
```

**異常回應** (200 OK):
```json
{
  "status": "unhealthy",
  "version": "1.0.0",
  "database": "disconnected"
}
```

### 4.2 認證機制

**目前狀態**: 無認證 (地端環境預設信任所有存取者)

**未來擴展** (若需要):
- API Key 認證: `X-API-Key: <secret>`
- JWT Token 認證
- OAuth 2.0

---

## 5. 資料模型

### 5.1 SQLite Schema

#### 5.1.1 processing_batches (處理批次)

```sql
CREATE TABLE processing_batches (
    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_uuid TEXT UNIQUE NOT NULL,
    supplier_id TEXT DEFAULT 'fairmont',
    status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','COMPLETED','FAILED')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,
    total_files INTEGER DEFAULT 0,
    processed_files INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE INDEX idx_batches_status_created ON processing_batches(status, created_at DESC);
CREATE INDEX idx_batches_uuid ON processing_batches(batch_uuid);
```

**用途**: 追蹤批次生命週期與狀態

---

#### 5.1.2 processing_stages (處理階段)

```sql
CREATE TABLE processing_stages (
    stage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES processing_batches(batch_id),
    stage_number INTEGER NOT NULL,
    stage_name TEXT NOT NULL CHECK(stage_name IN ('PDF_PARSING','EXTRACTION','NORMALIZATION','MERGING','FURNITURE','FABRIC_LINKING','EXPORT')),
    status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','COMPLETED','FAILED','RETRYING')),
    progress_percent INTEGER DEFAULT 0 CHECK(progress_percent >= 0 AND progress_percent <= 100),
    started_at DATETIME,
    completed_at DATETIME,
    execution_time_ms INTEGER,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    checkpoint_data TEXT
);

CREATE INDEX idx_stages_batch_status ON processing_stages(batch_id, status, stage_number);
```

**用途**:
- 記錄每階段進度與執行時間
- 儲存 checkpoint 資料 (JSON)
- 支援斷點續傳

---

#### 5.1.3 uploaded_files (上傳檔案)

```sql
CREATE TABLE uploaded_files (
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES processing_batches(batch_id),
    file_hash TEXT UNIQUE NOT NULL,
    original_filename TEXT NOT NULL,
    file_role TEXT NOT NULL CHECK(file_role IN ('QUANTITY_SHEET','SPEC_SHEET','FABRIC_SHEET','INDEX')),
    file_size_bytes INTEGER,
    status TEXT NOT NULL CHECK(status IN ('PENDING','CACHED','COMPLETED','FAILED')),
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    cached_result_path TEXT
);

CREATE INDEX idx_files_batch_status ON uploaded_files(batch_id, status);
CREATE INDEX idx_files_hash ON uploaded_files(file_hash);
```

**用途**:
- 記錄檔案元資料
- 快取檔案 Hash (SHA256)
- 檔案角色識別結果

---

#### 5.1.4 furniture_items (家具項目)

```sql
CREATE TABLE furniture_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES processing_batches(batch_id),
    item_no TEXT NOT NULL,
    description TEXT,
    dimensions TEXT,
    qty INTEGER,
    uom TEXT,
    materials TEXT,
    location TEXT,
    photo_path TEXT,
    brand TEXT,
    status TEXT CHECK(status IN ('SUCCESS','FAILED_EXTRACTION','PENDING_REVIEW')),
    related_fabric_ids TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_items_batch_item_no ON furniture_items(batch_id, item_no);
```

**用途**: 儲存家具項目 (目前未使用，為未來擴展預留)

---

#### 5.1.5 fabric_items (面料項目)

```sql
CREATE TABLE fabric_items (
    fabric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES processing_batches(batch_id),
    item_no TEXT NOT NULL,
    brand TEXT,
    pattern TEXT,
    color TEXT,
    width REAL,
    content TEXT,
    abrasion TEXT,
    vendor TEXT,
    furniture_com TEXT,
    status TEXT CHECK(status IN ('SUCCESS','PENDING_LINK','ORPHAN')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_fabrics_batch ON fabric_items(batch_id);
CREATE INDEX idx_fabrics_furniture_com ON fabric_items(furniture_com);
```

**用途**: 儲存面料項目 (目前未使用，為未來擴展預留)

---

#### 5.1.6 cache_records (快取記錄)

```sql
CREATE TABLE cache_records (
    cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash TEXT UNIQUE NOT NULL,
    result_path TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    hit_count INTEGER DEFAULT 0
);

CREATE INDEX idx_cache_hash ON cache_records(file_hash);
CREATE INDEX idx_cache_expires ON cache_records(expires_at);
```

**用途**:
- 快取已處理的批次結果
- TTL 管理 (預設 1 天)
- 命中次數統計

### 5.2 狀態機設計

#### BatchStatus 狀態轉換

```
PENDING → RUNNING → COMPLETED
               ↓
             FAILED
```

| 狀態 | 說明 | 可轉換至 |
|------|------|----------|
| PENDING | 批次已建立，等待處理 | RUNNING |
| RUNNING | 批次處理中 | COMPLETED, FAILED |
| COMPLETED | 批次成功完成 | - (終態) |
| FAILED | 批次失敗 | - (終態) |

#### StageStatus 狀態轉換

```
PENDING → RUNNING → COMPLETED
            ↓   ↗
          RETRYING → FAILED (retry_count >= 3)
```

| 狀態 | 說明 | 可轉換至 |
|------|------|----------|
| PENDING | 階段待處理 | RUNNING |
| RUNNING | 階段執行中 | COMPLETED, RETRYING, FAILED |
| RETRYING | 階段重試中 | RUNNING, FAILED |
| COMPLETED | 階段成功完成 | - (終態) |
| FAILED | 階段失敗 (超過重試次數) | - (終態) |

---

## 6. 關鍵設計決策

### 6.1 為何選擇 SQLite

**優勢**:
1. **零配置**: 無需獨立資料庫伺服器，適合地端部署
2. **高效率**: WAL (Write-Ahead Logging) 模式提升並發讀寫效能
3. **輕量化**: 單一檔案，易於備份與遷移
4. **ACID 保證**: 完整的事務支援，確保資料一致性
5. **成熟穩定**: 經過 20+ 年驗證，廣泛應用於各種場景

**限制與因應**:
| 限制 | 影響 | 因應策略 |
|------|------|----------|
| 單一寫入者 | 並發寫入受限 | 使用 Queue Lock 確保單一批次執行 |
| 檔案鎖定 | 網路檔案系統 (NFS) 效能差 | 部署於本地檔案系統 |
| 資料庫大小 | 超過 GB 等級效能下降 | 定期清理過期快取 (TTL 1 天) |

**效能設定**:
```sql
PRAGMA journal_mode = WAL;          -- 啟用 WAL 模式
PRAGMA synchronous = NORMAL;        -- 平衡效能與安全
PRAGMA foreign_keys = ON;           -- 啟用外鍵約束
PRAGMA busy_timeout = 5000;         -- 鎖定等待 5 秒
PRAGMA cache_size = -64000;         -- 64MB 記憶體快取
```

### 6.2 Queue Lock 機制

**設計目的**: 確保同一時間只有一個批次在處理 (FR-013)

**實作方式**:
```python
class BatchQueueLock:
    def __init__(self):
        self._lock = asyncio.Lock()  # asyncio 協程鎖
        self._current_batch_uuid = None

    @asynccontextmanager
    async def acquire(self, batch_uuid: str):
        if self._lock.locked():
            yield False  # 已有批次執行中
            return

        async with self._lock:
            self._current_batch_uuid = batch_uuid
            try:
                yield True  # 成功取得鎖定
            finally:
                self._current_batch_uuid = None
```

**使用範例**:
```python
async with queue_lock.acquire(batch_uuid) as acquired:
    if not acquired:
        raise HTTPException(409, "有其他批次正在處理中")

    # 執行處理
    result = await run_pipeline(batch_uuid, files)
```

**為何不使用資料庫鎖**:
- SQLite 檔案鎖無法跨 Python 協程共享
- asyncio.Lock 效能更好，延遲更低
- 支援非阻塞式檢查 (`locked()`)

**系統重啟處理**:
```python
# 啟動時清理卡住的批次
await queue_lock.force_release_stale_batches()
# 將所有 RUNNING 狀態的批次標記為 FAILED
```

### 6.3 Cache 策略

**快取鍵**: 多檔案批次的組合 Hash
```python
def compute_batch_hash(file_hashes: list[str]) -> str:
    combined = "".join(sorted(file_hashes))  # 排序後組合
    return hashlib.sha256(combined.encode()).hexdigest()
```

**快取流程**:
```
1. 使用者上傳 [file1, file2, file3]
2. 計算各檔案 Hash: [hash1, hash2, hash3]
3. 排序後組合: "hash1hash2hash3"
4. 計算批次 Hash: sha256(combined)
5. 查詢 cache_records 表
6. 若命中 → 載入快取結果 (JSON)
7. 若未命中 → 執行管線處理
8. 處理完成 → 儲存快取 (TTL 1 天)
```

**TTL 管理**:
- 預設過期時間: 1 天 (POC 階段設定)
- 定期清理任務: 刪除 `expires_at < CURRENT_TIMESTAMP` 的記錄
- 清理檔案: 同時刪除對應的快取 JSON 檔案

**命中率追蹤**:
- `cache_records.hit_count` 欄位記錄每次命中
- 可用於分析快取效益

### 6.4 家具 vs 面料的處理差異

這是系統最複雜的業務邏輯之一，源於 Fairmont 報價單格式的特殊要求。

#### 差異原因

| 項目 | 家具 | 面料 |
|------|------|------|
| **供應鏈角色** | OEM 代工 | 品牌供應商 |
| **採購關鍵** | 尺寸、材質 | 品牌、花色、規格 |
| **報價單定位** | 主要項目 | 附屬項目 (跟隨家具) |

#### 實作細節

**Description 欄位**:
```python
# 家具: 使用原始描述
furniture.description = "King Bed"

# 面料: 格式化為關聯描述
fabric.description = "Fabric to DLX-102 AND DLX-106"
```

**Dimension 欄位**:
```python
# 家具: 物理尺寸
furniture.dimension = "W2130 x D1930 x H290 mm"

# 面料: 規格字串 (識別資訊)
fabric.dimension = "55% cotton-Sankon Interior-Bravo Collection-BV106-140 cm plain"
# 格式: {Content}-{Vendor}-{Brand}-{Pattern}-{Width} pattern/plain
```

**Brand 欄位**:
```python
# 家具: 強制 Null (OEM 產品)
furniture.brand = None

# 面料: 必填 (品牌是採購關鍵)
fabric.brand = "Bravo Collection"
```

**Location 欄位**:
```python
# 家具: 從 Index PDF 提取的完整房型列表
furniture.location = "King Deluxe Room Type A / King Deluxe Room Type B / ..."

# 面料: 關聯的家具編號
fabric.location = "DLX-102 AND DLX-106"
```

**Materials Used 欄位**:
```python
# 家具: 原始材質描述
furniture.materials_used = "10mm THK Rebonded FR Foam"

# 面料: 規格組合字串
fabric.materials_used = """Pattern: BV106-05M084C. Color: Cream. Rub Test: 40,000 Double Rubs
Fire Rating: NFPA 260, Class 1"""
```

---

## 7. 可擴展性與效能考量

### 7.1 並發控制

**目前策略**: 單一批次執行 (Queue Lock)

**原因**:
- SQLite 單一寫入者限制
- LLM API 呼叫成本高 (避免過度並發)
- 地端環境資源有限 (CPU/記憶體)

**擴展方案** (若需要):
1. **水平擴展**: 多節點部署，使用 Redis 分散式鎖
2. **資料庫升級**: 遷移至 PostgreSQL，支援多寫入者
3. **非同步處理**: 引入訊息佇列 (RabbitMQ/Redis Queue)

```python
# 未來擴展架構
┌─────────┐    ┌─────────┐    ┌─────────┐
│ Worker 1│    │ Worker 2│    │ Worker 3│
└────┬────┘    └────┬────┘    └────┬────┘
     │              │              │
     └──────────────┴──────────────┘
                    │
              ┌─────▼─────┐
              │   Redis   │ (分散式鎖 + 任務佇列)
              └───────────┘
                    │
              ┌─────▼─────┐
              │PostgreSQL │ (多寫入支援)
              └───────────┘
```

### 7.2 檔案快取

**目前實作**:
- 檔案級別快取 (SHA256 Hash)
- 批次結果儲存為 JSON 檔案

**優勢**:
- 相同檔案內容直接返回 (秒級回應)
- 減少 LLM API 呼叫成本

**優化方向**:
1. **階段級快取**: 快取每個階段的中間結果
2. **項目級快取**: 快取單一 Item No. 的解析結果
3. **Redis 快取**: 將熱門結果放入記憶體快取

### 7.3 LLM API 呼叫優化

**目前策略**:

| 優化方式 | 說明 | 效果 |
|----------|------|------|
| **分塊策略** | 將大內容切割成 2K tokens chunks | 避免 Context Window 限制 |
| **重試機制** | 指數退避重試 (最多 3 次) | 提高成功率 |
| **超時控制** | 預設 120 秒超時 | 避免長時間卡住 |
| **平行處理** | 多個 chunks 並行呼叫 | 提升吞吐量 (未實作) |

**優化方向**:
```python
# 未來：平行處理多個 chunks
async def call_chunked_parallel(chunks: list[str]) -> list[dict]:
    tasks = [call_with_retry(system_prompt, chunk) for chunk in chunks]
    responses = await asyncio.gather(*tasks)
    return merge_json_responses(responses)
```

**成本控制**:
- 計算每次呼叫的 token 數
- 記錄至 `processing_stages.execution_time_ms`
- 定期分析成本與效益

### 7.4 資料庫效能

**索引策略**:
```sql
-- 批次查詢 (最常用)
CREATE INDEX idx_batches_uuid ON processing_batches(batch_uuid);

-- 進度查詢
CREATE INDEX idx_stages_batch_status ON processing_stages(batch_id, status, stage_number);

-- 快取查詢
CREATE INDEX idx_cache_hash ON cache_records(file_hash);
```

**查詢優化**:
- 避免 `SELECT *`，只查詢需要的欄位
- 使用 `LIMIT` 限制結果數量
- 定期執行 `VACUUM` 清理碎片

**監控指標**:
- 批次處理時間 (`processing_time_ms`)
- 階段執行時間 (`execution_time_ms`)
- 快取命中率 (`hit_count`)

---

## 8. 錯誤處理與重試機制

### 8.1 階段級錯誤處理

**策略**: 每階段獨立捕捉異常，記錄錯誤訊息後決定是否重試或失敗

```python
try:
    await self._stage_extraction()
except Exception as e:
    self.logger.error(f"Stage 2 失敗: {e}")
    self._update_stage_status(stage_id, StageStatus.FAILED, str(e))
    raise
```

**錯誤記錄**:
- 階段層級: `processing_stages.error_message`
- 批次層級: `processing_batches.error_message`
- 應用層級: 日誌檔案 (PipelineLogger)

### 8.2 LLM 呼叫重試

**指數退避策略**:
```python
for attempt in range(max_retries + 1):  # max_retries = 3
    try:
        response = await self.call(system_prompt, user_prompt)
        return response
    except Exception as e:
        if attempt < max_retries:
            wait_time = 2 ** (attempt + 1)  # 2, 4, 8 秒
            await asyncio.sleep(wait_time)
        else:
            raise RuntimeError(f"LLM 呼叫失敗 (重試 {max_retries} 次): {e}")
```

**重試條件**:
- 網路逾時 (TimeoutError)
- Rate Limit (429 錯誤)
- 暫時性錯誤 (5xx 錯誤)

**不重試條件**:
- 認證錯誤 (401 錯誤)
- 參數錯誤 (400 錯誤)

### 8.3 斷點續傳

**觸發條件**:
- 系統崩潰 (OOM, 斷電)
- 手動終止 (Ctrl+C)
- 階段失敗 (超過重試次數)

**恢復流程**:
```python
1. 使用者重新啟動系統
2. 檢查是否有失敗的批次 (status = FAILED)
3. 使用者呼叫 POST /process 並傳入相同檔案
4. 系統檢測到快取未命中 (因為尚未完成)
5. 呼叫 can_resume(batch_uuid) → True
6. 呼叫 get_resume_stage(batch_uuid) → 失敗的階段
7. 載入 checkpoint 資料
8. 從該階段繼續執行
```

**Checkpoint 資料完整性**:
- 每階段完成後立即寫入 SQLite (ACID 保證)
- 使用 JSON 序列化，支援複雜資料結構
- 包含足夠資訊供下一階段使用

### 8.4 容錯設計

**原則**: Fail Fast + Graceful Degradation

| 錯誤類型 | 處理方式 | 影響範圍 |
|----------|----------|----------|
| **檔案格式錯誤** | 400 錯誤，拒絕處理 | 單一請求 |
| **單一項目解析失敗** | 記錄警告，繼續處理其他項目 | 單一項目 |
| **LLM 呼叫失敗** | 重試 3 次，失敗後標記階段失敗 | 單一階段 |
| **資料庫錯誤** | 立即失敗，返回 500 錯誤 | 整個系統 |

**使用者面向錯誤訊息** (繁體中文):
```python
{
    "error_code": "PROCESSING_FAILED",
    "message": "處理失敗: LLM 呼叫逾時，請稍後重試",
    "details": {
        "stage": "EXTRACTION",
        "retry_count": 3
    }
}
```

---

## 9. 部署與維運

### 9.1 部署架構

**單機部署** (目前):
```
┌─────────────────────────────────────────┐
│         Windows Server / Linux           │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │   FastAPI (uvicorn)                │ │
│  │   Port: 8000                       │ │
│  └────────────┬───────────────────────┘ │
│               │                          │
│  ┌────────────▼───────────────────────┐ │
│  │   SQLite (data/fairmont.db)        │ │
│  │   Mode: WAL                        │ │
│  └────────────┬───────────────────────┘ │
│               │                          │
│  ┌────────────▼───────────────────────┐ │
│  │   Cache (data/cache/*.json)        │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

**啟動指令**:
```bash
# 初始化資料庫
python -m src.models.database init

# 啟動服務
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# 背景執行 (生產環境)
nohup uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > logs/app.log 2>&1 &
```

### 9.2 環境變數

**關鍵設定**:
```bash
# 資料庫路徑
DATABASE_PATH=data/fairmont.db

# LLM API 設定
OPENAI_API_KEY=<your-api-key>
OPENAI_API_BASE=https://api.apmic-ai.com/v1
OPENAI_MODEL=gemma-3-12b

# 快取設定
CACHE_TTL_DAYS=1

# 架構切換
USE_SQLITE_PIPELINE=true

# 檔案限制
MAX_UPLOAD_FILES=10
MAX_FILE_SIZE_MB=50
```

### 9.3 監控指標

**系統健康**:
- `/health` 端點狀態
- SQLite 資料庫連線狀態
- 磁碟空間使用率

**業務指標**:
- 批次處理時間 (平均/P95/P99)
- 階段執行時間分布
- 快取命中率
- LLM API 呼叫次數與成本

**日誌記錄**:
```python
# PipelineLogger 輸出格式
[2026-01-08 10:30:00] [INFO] [batch-550e8400] Stage 1: PDF_PARSING 開始
[2026-01-08 10:30:05] [DEBUG] [batch-550e8400] 解析完成: Casegoods & Seatings.pdf (role=SPEC_SHEET)
[2026-01-08 10:30:10] [INFO] [batch-550e8400] Stage 1: PDF_PARSING 完成 (5000ms)
```

### 9.4 維運任務

**定期任務**:
```bash
# 每日清理過期快取
python -m src.services.cache cleanup_expired_cache

# 每週備份資料庫
cp data/fairmont.db backups/fairmont_$(date +%Y%m%d).db

# 每月執行 VACUUM (清理碎片)
sqlite3 data/fairmont.db "VACUUM;"
```

**災難恢復**:
```bash
# 備份策略: 每日全量備份 + WAL 檔案
1. 複製 fairmont.db
2. 複製 fairmont.db-wal
3. 複製 fairmont.db-shm

# 恢復方式: 直接替換資料庫檔案
cp backups/fairmont_20260108.db data/fairmont.db
```

### 9.5 效能調校

**SQLite 優化**:
```sql
-- 增加快取大小 (根據可用記憶體調整)
PRAGMA cache_size = -128000;  -- 128MB

-- 啟用記憶體暫存檔
PRAGMA temp_store = MEMORY;

-- 定期分析查詢計劃
ANALYZE;
```

**FastAPI 優化**:
```bash
# 使用 Gunicorn + uvicorn workers (多核心)
gunicorn src.api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

**作業系統調校**:
```bash
# Linux: 增加檔案描述符限制
ulimit -n 65536

# 監控記憶體使用
watch -n 1 'ps aux | grep uvicorn'
```

---

## 附錄

### A. 常見問題 (FAQ)

**Q1: 為何選擇 Gemma-3-12b 而非 GPT-4？**

A:
- 地端部署需求：Gemma 可在地端運行，符合資料安全要求
- 成本考量：APMIC API 費用較低
- 效能足夠：12B 模型對於結構化資料擷取已足夠準確

**Q2: 若 LLM 解析錯誤，如何人工修正？**

A:
- 短期：手動編輯輸出的 JSON 檔案
- 長期：開發前端介面，支援項目級別的手動校正

**Q3: 系統能處理多大的 PDF？**

A:
- 單檔案限制：50MB (可調整 `MAX_FILE_SIZE_MB`)
- 總頁數限制：無硬性限制，但超過 100 頁會影響效能
- 分塊策略：自動分割大內容，避免 Context Window 限制

**Q4: 如何處理供應商變更 PDF 格式？**

A:
- Adapter Pattern：新增供應商適配器 (參考 `src/services/adapters/`)
- 檔案角色偵測：調整 `detect_file_role()` 邏輯
- LLM Prompt：更新 System Prompt 描述

### B. 技術債務與未來改進

| 項目 | 現狀 | 改進方向 |
|------|------|----------|
| **測試覆蓋率** | ~60% | 提升至 80% 以上 |
| **前端介面** | 無 | 開發 Web UI (Vue.js / React) |
| **多供應商支援** | 基礎架構已有 | 實作更多 Adapter |
| **Excel 匯出** | 目前僅輸出 JSON | 直接生成 Excel (openpyxl) |
| **使用者認證** | 無 | 實作 API Key / JWT 認證 |
| **分散式部署** | 單機 | 支援多節點 + Redis 分散式鎖 |

### C. 參考文件

- [功能規格](../specs/001-sqlite-pipeline-quote/spec.md)
- [資料模型](../specs/001-sqlite-pipeline-quote/data-model.md)
- [輸出規格](EXCEL_OUTPUT_SPECIFICATION.md)
- [API 參考](APMIC_API_REFERENCE.md)

---

**文件版本**: 1.0
**最後更新**: 2026-01-08
**維護者**: Fairmont APMIC 開發團隊
