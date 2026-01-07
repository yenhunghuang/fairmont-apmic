# Data Model: 地端 SQLite 多階段 PDF 報價單處理系統

**Date**: 2026-01-07
**Feature**: 001-sqlite-pipeline-quote
**Database**: SQLite (`data/fairmont.db`)

---

## Entity Relationship Diagram

```
┌─────────────────────┐      ┌─────────────────────┐
│  ProcessingBatch    │──1:N─│   UploadedFile      │
│  (處理批次)          │      │   (上傳檔案)         │
├─────────────────────┤      ├─────────────────────┤
│ batch_id (PK)       │      │ file_id (PK)        │
│ batch_uuid (UNIQUE) │      │ batch_id (FK)       │
│ supplier_id         │      │ file_hash (UNIQUE)  │
│ status              │      │ original_filename   │
│ created_at          │      │ file_role           │
│ completed_at        │      │ status              │
│ total_files         │      └─────────────────────┘
│ error_message       │               │
└─────────────────────┘               │
         │                            │
         │ 1:N                        │ 1:1 (optional)
         ▼                            ▼
┌─────────────────────┐      ┌─────────────────────┐
│  ProcessingStage    │      │   CacheRecord       │
│  (處理階段)          │      │   (快取記錄)         │
├─────────────────────┤      ├─────────────────────┤
│ stage_id (PK)       │      │ cache_id (PK)       │
│ batch_id (FK)       │      │ file_hash (FK)      │
│ stage_number        │      │ result_path         │
│ stage_name          │      │ created_at          │
│ status              │      │ expires_at          │
│ progress_percent    │      │ hit_count           │
│ checkpoint_data     │      └─────────────────────┘
└─────────────────────┘
         │
         │ N:N (via batch_id)
         ▼
┌─────────────────────┐      ┌─────────────────────┐
│  FurnitureItem      │──N:N─│   FabricItem        │
│  (家具項目)          │      │   (面料項目)         │
├─────────────────────┤      ├─────────────────────┤
│ item_id (PK)        │      │ fabric_id (PK)      │
│ batch_id (FK)       │      │ batch_id (FK)       │
│ item_no             │      │ item_no             │
│ description         │      │ brand               │
│ dimensions          │      │ pattern             │
│ qty                 │      │ color               │
│ uom                 │      │ width               │
│ materials           │      │ content             │
│ location            │      │ abrasion            │
│ photo_path          │      │ vendor              │
│ brand               │      │ furniture_com       │
│ related_fabric_ids  │      │ status              │
└─────────────────────┘      └─────────────────────┘
```

---

## 1. ProcessingBatch (處理批次)

代表一次 PDF 上傳處理請求。

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `batch_id` | INTEGER | PK, AUTO | 內部識別符 |
| `batch_uuid` | TEXT | UNIQUE, NOT NULL | 外部 UUID (API 回傳) |
| `supplier_id` | TEXT | DEFAULT 'fairmont' | 供應商識別符 (多供應商支援) |
| `status` | TEXT | NOT NULL, CHECK | PENDING/RUNNING/COMPLETED/FAILED |
| `created_at` | DATETIME | DEFAULT NOW | 建立時間 |
| `started_at` | DATETIME | | 開始處理時間 |
| `completed_at` | DATETIME | | 完成時間 |
| `total_files` | INTEGER | DEFAULT 0 | 上傳檔案數 |
| `processed_files` | INTEGER | DEFAULT 0 | 已處理檔案數 |
| `error_message` | TEXT | | 錯誤訊息 (繁體中文) |

**Indexes**:
- `idx_batches_status_created (status, created_at DESC)`
- `idx_batches_uuid (batch_uuid)` UNIQUE
- `idx_batches_supplier (supplier_id)`

---

## 2. UploadedFile (上傳檔案)

代表單一上傳的 PDF 檔案。

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `file_id` | INTEGER | PK, AUTO | 內部識別符 |
| `batch_id` | INTEGER | FK → ProcessingBatch | 所屬批次 |
| `file_hash` | TEXT | UNIQUE, NOT NULL | SHA256 雜湊 (快取鍵) |
| `original_filename` | TEXT | NOT NULL | 原始檔名 |
| `file_role` | TEXT | NOT NULL, CHECK | QUANTITY_SHEET/SPEC_SHEET/FABRIC_SHEET/INDEX |
| `file_size_bytes` | INTEGER | | 檔案大小 |
| `status` | TEXT | NOT NULL, CHECK | PENDING/CACHED/COMPLETED/FAILED |
| `uploaded_at` | DATETIME | DEFAULT NOW | 上傳時間 |
| `cached_result_path` | TEXT | | 快取結果路徑 |

**Indexes**:
- `idx_files_batch_status (batch_id, status)`
- `idx_files_hash (file_hash)` UNIQUE

**Validation Rules**:
- `file_role` 必須是定義的四種類型之一
- `file_hash` 採用 SHA256 (64 字元)

---

## 3. ProcessingStage (處理階段)

代表管線中的一個處理階段。

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `stage_id` | INTEGER | PK, AUTO | 內部識別符 |
| `batch_id` | INTEGER | FK → ProcessingBatch | 所屬批次 |
| `stage_number` | INTEGER | NOT NULL | 階段編號 (1-7) |
| `stage_name` | TEXT | NOT NULL, CHECK | 階段名稱 |
| `status` | TEXT | NOT NULL, CHECK | PENDING/RUNNING/COMPLETED/FAILED/RETRYING |
| `progress_percent` | INTEGER | CHECK 0-100 | 進度百分比 |
| `started_at` | DATETIME | | 開始時間 |
| `completed_at` | DATETIME | | 完成時間 |
| `execution_time_ms` | INTEGER | | 執行時間 (毫秒) |
| `error_message` | TEXT | | 錯誤訊息 |
| `retry_count` | INTEGER | DEFAULT 0 | 重試次數 |
| `checkpoint_data` | TEXT | | 中間結果 (JSON) |

**Indexes**:
- `idx_stages_batch_status (batch_id, status, stage_number)`
- `idx_stages_batch_completed (batch_id, status) WHERE status='COMPLETED'`

**Stage Names (Enum)**:
```python
class StageName(str, Enum):
    PDF_PARSING = "PDF_PARSING"           # 階段 1
    EXTRACTION = "EXTRACTION"             # 階段 2
    NORMALIZATION = "NORMALIZATION"       # 階段 3
    MERGING = "MERGING"                   # 階段 4
    FURNITURE_EXTRACTION = "FURNITURE"    # 階段 5
    FABRIC_LINKING = "FABRIC_LINKING"     # 階段 6
    EXPORT = "EXPORT"                     # 階段 7
```

---

## 4. FurnitureItem (家具項目)

代表解析出的單一家具項目。

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `item_id` | INTEGER | PK, AUTO | 內部識別符 |
| `batch_id` | INTEGER | FK → ProcessingBatch | 所屬批次 |
| `item_no` | TEXT | NOT NULL | Item No. (正規化後) |
| `description` | TEXT | | 品名描述 |
| `dimensions` | TEXT | | 尺寸 (寬 x 深 x 高) |
| `qty` | INTEGER | | 數量 (從數量總表獲取) |
| `uom` | TEXT | | 單位 (ea, m, etc.) |
| `materials` | TEXT | | 材料規格 |
| `location` | TEXT | | 房型/位置 |
| `photo_path` | TEXT | | 圖片儲存路徑 |
| `brand` | TEXT | | 品牌/供應商 |
| `status` | TEXT | CHECK | SUCCESS/FAILED_EXTRACTION/PENDING_REVIEW |
| `related_fabric_ids` | TEXT | | JSON 陣列 [fabric_id, ...] |
| `created_at` | DATETIME | DEFAULT NOW | 建立時間 |

**Indexes**:
- `idx_items_batch_item_no (batch_id, item_no)`
- `idx_items_status (status)`

**Validation Rules**:
- `item_no` 經正規化處理 (移除多餘空格、統一破折號)
- `qty` 若數量總表與規格表衝突，以數量總表為準 (FR-006)

---

## 5. FabricItem (面料項目)

代表解析出的面料/皮革項目 (500 系列)。

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `fabric_id` | INTEGER | PK, AUTO | 內部識別符 |
| `batch_id` | INTEGER | FK → ProcessingBatch | 所屬批次 |
| `item_no` | TEXT | NOT NULL | Item No. (500 系列) |
| `brand` | TEXT | | 品牌 |
| `pattern` | TEXT | | 花紋 |
| `color` | TEXT | | 顏色 |
| `width` | REAL | | 寬度 (cm) |
| `content` | TEXT | | 材質成分 |
| `abrasion` | TEXT | | 耐磨度 |
| `vendor` | TEXT | | 供應商 |
| `furniture_com` | TEXT | | 關聯家具 Item No. |
| `status` | TEXT | CHECK | SUCCESS/PENDING_LINK/ORPHAN |
| `created_at` | DATETIME | DEFAULT NOW | 建立時間 |

**Indexes**:
- `idx_fabrics_batch (batch_id)`
- `idx_fabrics_furniture_com (furniture_com)`

---

## 6. CacheRecord (快取記錄)

代表已處理檔案的快取。

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `cache_id` | INTEGER | PK, AUTO | 內部識別符 |
| `file_hash` | TEXT | UNIQUE, FK | 檔案 SHA256 雜湊 |
| `result_path` | TEXT | NOT NULL | 結果 JSON 檔案路徑 |
| `created_at` | DATETIME | DEFAULT NOW | 建立時間 |
| `expires_at` | DATETIME | | 過期時間 (1 天後) |
| `hit_count` | INTEGER | DEFAULT 0 | 快取命中次數 |

**Indexes**:
- `idx_cache_hash (file_hash)` UNIQUE
- `idx_cache_expires (expires_at)`

**Lifecycle**:
- 建立時設定 `expires_at = created_at + 1 day`
- 每日清理任務刪除過期記錄

---

## 7. State Transitions

### ProcessingBatch Status
```
PENDING → RUNNING → COMPLETED
                 ↘ FAILED
```

### ProcessingStage Status
```
PENDING → RUNNING → COMPLETED
           ↓   ↗
         RETRYING → FAILED (retry_count >= 3)
```

### FurnitureItem Status
```
(parsed) → SUCCESS
        ↘ FAILED_EXTRACTION
        ↘ PENDING_REVIEW (Item No. 不一致)
```

### FabricItem Status
```
(parsed) → SUCCESS (已關聯家具)
        ↘ PENDING_LINK (待關聯)
        ↘ ORPHAN (無對應家具)
```

---

## 8. SQLite Schema (完整)

```sql
-- 初始化設定
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

-- ProcessingBatch
CREATE TABLE IF NOT EXISTS processing_batches (
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
CREATE INDEX IF NOT EXISTS idx_batches_status_created ON processing_batches(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_batches_uuid ON processing_batches(batch_uuid);
CREATE INDEX IF NOT EXISTS idx_batches_supplier ON processing_batches(supplier_id);

-- UploadedFile
CREATE TABLE IF NOT EXISTS uploaded_files (
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
CREATE INDEX IF NOT EXISTS idx_files_batch_status ON uploaded_files(batch_id, status);
CREATE INDEX IF NOT EXISTS idx_files_hash ON uploaded_files(file_hash);

-- ProcessingStage
CREATE TABLE IF NOT EXISTS processing_stages (
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
CREATE INDEX IF NOT EXISTS idx_stages_batch_status ON processing_stages(batch_id, status, stage_number);

-- FurnitureItem
CREATE TABLE IF NOT EXISTS furniture_items (
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
CREATE INDEX IF NOT EXISTS idx_items_batch_item_no ON furniture_items(batch_id, item_no);
CREATE INDEX IF NOT EXISTS idx_items_status ON furniture_items(status);

-- FabricItem
CREATE TABLE IF NOT EXISTS fabric_items (
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
CREATE INDEX IF NOT EXISTS idx_fabrics_batch ON fabric_items(batch_id);
CREATE INDEX IF NOT EXISTS idx_fabrics_furniture_com ON fabric_items(furniture_com);

-- CacheRecord
CREATE TABLE IF NOT EXISTS cache_records (
    cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash TEXT UNIQUE NOT NULL,
    result_path TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    hit_count INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cache_hash ON cache_records(file_hash);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache_records(expires_at);
```
