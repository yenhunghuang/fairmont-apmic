# Research: 地端 SQLite 多階段 PDF 報價單處理系統

**Date**: 2026-01-07
**Feature**: 001-sqlite-pipeline-quote
**Status**: Complete

---

## 1. FastAPI 多檔案上傳 API 設計

### Decision: 使用 `list[UploadFile]` 接收多 PDF，同步處理後返回 JSON

### Rationale
- 根據用戶需求：單一 API，輸入複數 PDF，輸出 JSON
- FastAPI 原生支援 `list[UploadFile]`，Swagger UI 自動產生檔案上傳介面
- POC 階段採用同步處理（單批次 <100 項目，<15 分鐘），避免過度設計

### Alternatives Considered
| 方案 | 優點 | 缺點 | 結論 |
|------|------|------|------|
| 非同步 (Job ID + Polling) | 適合長時間處理 | 增加複雜度，需額外 API | POC 暫不採用 |
| WebSocket 進度串流 | 即時更新 | 前端需額外支援 | 未來擴展 |
| **同步處理** | 簡單、Swagger 直接測試 | 長時間處理可能超時 | ✅ 採用 |

### Implementation Pattern
```python
from fastapi import FastAPI, File, UploadFile
from typing import Annotated

@app.post("/api/v1/quote/process")
async def process_pdfs(
    files: Annotated[list[UploadFile], File(description="上傳 PDF 檔案")]
) -> QuoteResponse:
    # 1. 驗證檔案類型
    # 2. 計算 file hash (快取查詢)
    # 3. 執行多階段管線
    # 4. 返回 15 欄位 JSON
    ...
```

---

## 2. PDF 解析策略

### Decision: 使用 pdfplumber 擷取文字與表格，PyMuPDF (fitz) 擷取圖片

### Rationale
- pdfplumber 擅長表格偵測與文字擷取，API 直覺
- pdfplumber 對圖片支援有限，PyMuPDF 更適合高品質圖片擷取
- 兩者搭配可覆蓋所有需求

### Implementation Pattern
```python
import pdfplumber
import fitz  # PyMuPDF

def parse_pdf(file_path: str):
    # 文字與表格擷取
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            tables = page.extract_tables()

    # 圖片擷取
    doc = fitz.open(file_path)
    for page in doc:
        images = page.get_images()
        for img in images:
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
```

### Error Handling
- 使用 try-except 包裝每頁處理
- 單頁失敗不影響整份 PDF
- 記錄錯誤並標記該項目為待人工確認

---

## 3. SQLite 多階段管線設計

### Decision: WAL 模式 + 7 階段管線 + SAVEPOINT 分支

### Rationale
- WAL (Write-Ahead Logging) 提供更好的並行讀取與崩潰恢復
- 7 階段管線符合處理流程：解析 → 擷取 → 正規化 → 合併 → 家具擷取 → 面料關聯 → 匯出
- SAVEPOINT 允許 Item-level 錯誤不影響整批次

### 7 階段定義
| 階段 | 名稱 | 輸入 | 輸出 |
|------|------|------|------|
| 1 | PDF_PARSING | 上傳 PDF | 原始文字/表格 |
| 2 | EXTRACTION | 原始資料 | 結構化 Item 列表 |
| 3 | NORMALIZATION | Item 列表 | Item No. 正規化 |
| 4 | MERGING | 正規化結果 | 合併數量總表與規格表 |
| 5 | FURNITURE_EXTRACTION | 合併結果 | 家具項目詳情 |
| 6 | FABRIC_LINKING | 家具項目 | 面料關聯完成 |
| 7 | EXPORT | 完整資料 | 15 欄位 JSON |

### Checkpoint Pattern
```sql
-- 階段完成後原子提交
UPDATE processing_stages
SET status='COMPLETED',
    completed_at=CURRENT_TIMESTAMP,
    checkpoint_data=?
WHERE batch_id=? AND stage_number=?;
COMMIT;

-- 重啟時查詢最後完成階段
SELECT MAX(stage_number)
FROM processing_stages
WHERE batch_id=? AND status='COMPLETED';
```

---

## 4. 檔案快取策略

### Decision: SHA256 雜湊 + 1 天過期

### Rationale
- SHA256 足夠穩定，碰撞機率極低
- 1 天過期符合 POC 需求 (FR-021)
- 快取命中應 < 3 秒 (SC-003)

### Implementation Pattern
```python
import hashlib

def compute_file_hash(file_content: bytes) -> str:
    return hashlib.sha256(file_content).hexdigest()

# SQL 快取查詢
SELECT result_path FROM cache_records
WHERE file_hash = ?
  AND expires_at > CURRENT_TIMESTAMP;
```

---

## 5. PRAGMA 生產設定

### Decision: 採用 WAL + NORMAL 同步 + 5 秒 busy_timeout

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA cache_size = -64000;  -- 64MB cache (地端環境)
```

### Rationale
- WAL 模式：支援並行讀取，崩潰恢復更快
- NORMAL 同步：WAL 模式下已足夠安全
- 5 秒 busy_timeout：避免「資料庫被鎖定」錯誤

---

## 6. 索引設計

### 高頻查詢索引

| 索引 | 欄位 | 用途 |
|------|------|------|
| `idx_batches_status_created` | `(status, created_at)` | 批次列表查詢 |
| `idx_files_hash` | `(file_hash)` UNIQUE | 快取查詢 (< 100ms) |
| `idx_stages_batch_status` | `(batch_id, status, stage_number)` | 進度查詢、復蘇 |
| `idx_items_batch_item_no` | `(batch_id, item_no)` | Item 合併 |
| `idx_cache_expires` | `(expires_at)` | 批次清理 |

---

## 7. API 回應格式

### Decision: 符合前端需求的 15 欄位 JSON 結構

```json
{
  "batch_id": "uuid",
  "status": "completed",
  "items": [
    {
      "no": 1,
      "item_no": "DLX-100",
      "description": "Bedside Table",
      "photo_base64": "...",
      "dimension": "600 x 450 x 550",
      "qty": 10,
      "uom": "ea",
      "materials_used": "Solid Oak, Lacquered Finish",
      "location": "Deluxe Room",
      "note": "",
      "brand": "Custom",
      "unit_rate": null,
      "amount": null,
      "cbm": null,
      "total_cbm": null
    }
  ],
  "errors": [],
  "processing_time_ms": 12345
}
```

---

## 8. 未解決項目

所有技術決策已完成，無 NEEDS CLARIFICATION 項目。
