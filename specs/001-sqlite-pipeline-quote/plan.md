# Implementation Plan: 地端 SQLite 多階段 PDF 報價單處理系統

**Branch**: `001-sqlite-pipeline-quote` | **Date**: 2026-01-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-sqlite-pipeline-quote/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

開發單一 FastAPI 端點，接受多份 PDF 檔案上傳，透過 SQLite 多階段管線處理，輸出符合惠而蒙 (Fairmont) 格式的 15 欄位 JSON 報價單資料。前後端分離架構，後端專注於 API 設計，使用 Swagger 介面供前端工程師測試。

## Technical Context

**Language/Version**: Python >= 3.11
**Primary Dependencies**: FastAPI, python-multipart, pdfplumber (PDF 解析), SQLite3 (內建), Pydantic (資料驗證)
**Storage**: SQLite (`data/fairmont.db`) - 輕量級地端資料庫
**Testing**: pytest + pytest-asyncio
**Target Platform**: Windows 地端伺服器 (單機部署)
**Project Type**: single (僅後端 API)
**Performance Goals**: 單一批次 100 項目 < 15 分鐘處理完成；快取命中 < 3 秒回應
**Constraints**: LLM Prompt < 2K tokens 單次呼叫；支援斷點續傳
**Scale/Scope**: 10+ 併發上傳請求排隊處理；單批次 < 100 項目

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### 原則 I - 代碼品質 ✅
- [x] 自文檔化代碼，命名清晰 → 將於實作時遵循
- [x] 語法檢查/格式化零警告 → 使用 Black + Ruff
- [x] 公共 API 必須具有內嵌文件 → OpenAPI 規範已定義於 `contracts/openapi.yaml`
- [x] 第三方依賴需要安全審查 → 使用主流穩定套件 (FastAPI, pdfplumber, PyMuPDF)

### 原則 II - 測試標準 (NON-NEGOTIABLE) ✅
- [x] 測試優先開發 → 編寫測試 → 驗證失敗 → 實作 → 驗證通過
- [x] 最低 80% 代碼覆蓋率 → pytest-cov 驗證
- [x] 必需測試類型：單元、整合 → tests/unit/, tests/integration/ 已規劃

### 原則 III - UX 一致性 ✅
- [x] 繁體中文清晰的錯誤訊息 → ErrorResponse schema 定義繁體中文訊息
- [x] 操作 >100ms 的載入狀態 → 進度 API `/api/v1/quote/status/{batch_id}` 已定義

### 原則 IV - 效能要求 ✅
- [x] API 回應時間 <300ms (p95) → 快取命中 < 3 秒；長時間處理由進度 API 回報
- [x] 支援 10+ 併發使用者 → SQLite 佇列處理機制設計於 data-model.md
- [x] 資料庫查詢必須使用索引 → 7 個索引已定義於 data-model.md

### 原則 V - 語言要求 ✅
- [x] 繁體中文 (zh-TW) 用於 API 文件、錯誤訊息 → openapi.yaml 使用繁體中文描述
- [x] 允許英文用於代碼註解 → 符合

**Gate 評估 (Phase 1 後)**: ✅ 所有原則已滿足，設計符合憲法要求。

## Project Structure

### Documentation (this feature)

```text
specs/001-sqlite-pipeline-quote/
├── plan.md              # 本檔案 (/speckit.plan 輸出)
├── research.md          # Phase 0 輸出
├── data-model.md        # Phase 1 輸出
├── quickstart.md        # Phase 1 輸出
├── contracts/           # Phase 1 輸出 (OpenAPI 規範)
└── tasks.md             # Phase 2 輸出 (/speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI 應用程式入口
│   ├── routes/
│   │   ├── __init__.py
│   │   └── quote.py         # 報價單處理端點
│   └── deps.py              # 依賴注入
├── models/
│   ├── __init__.py
│   ├── database.py          # SQLite 連線與初始化
│   ├── schemas.py           # Pydantic schemas (API 輸入/輸出)
│   └── entities.py          # 資料庫實體定義
├── services/
│   ├── __init__.py
│   ├── pdf_parser.py        # PDF 解析服務
│   ├── pipeline.py          # 多階段處理管線
│   ├── cache.py             # 快取服務
│   ├── queue.py             # 批次佇列鎖定機制 (FR-013)
│   ├── llm_client.py        # LLM 呼叫封裝 (含分塊策略)
│   └── adapters/            # 多供應商適配器
│       ├── __init__.py
│       ├── base.py          # SupplierAdapter Protocol
│       ├── registry.py      # Adapter 註冊與載入
│       ├── fairmont.py      # Fairmont 專用 Adapter
│       └── generic.py       # LLM 動態判斷 Adapter (兜底)
└── utils/
    ├── __init__.py
    └── item_normalizer.py   # Item No. 正規化

tests/
├── conftest.py              # pytest fixtures
├── integration/
│   └── test_quote_api.py    # API 整合測試
└── unit/
    ├── test_pdf_parser.py
    ├── test_pipeline.py
    ├── test_item_normalizer.py
    ├── test_queue.py        # 佇列鎖定測試
    ├── test_llm_client.py   # LLM 分塊測試
    └── test_adapters.py     # 供應商適配器測試

configs/
└── suppliers/
    ├── fairmont.yaml        # Fairmont 規則配置
    └── _generic.yaml        # 通用 LLM Prompt 配置

data/
└── fairmont.db              # SQLite 資料庫 (執行時產生)
```

**Structure Decision**: 採用單一專案結構 (Single project)，因本功能僅需後端 API，無前端。FastAPI 應用程式位於 `src/api/`，核心處理邏輯位於 `src/services/`。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

無違反項目，本設計符合所有憲法原則。
