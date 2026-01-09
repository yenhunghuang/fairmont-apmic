# Tasks: 地端 SQLite 多階段 PDF 報價單處理系統

**Input**: Design documents from `/specs/001-sqlite-pipeline-quote/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included - spec.md 要求 80% 測試覆蓋率 (Constitution Check: 原則 II)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root (per plan.md)
- Database: `data/fairmont.db`

---

## Phase 1: Setup (Shared Infrastructure) ✅ 完成

**Purpose**: Project initialization and basic structure

- [x] T001 Create project structure per plan.md (src/api/, src/models/, src/services/, src/utils/, tests/, data/)
- [x] T002 Initialize Python project with requirements.txt (FastAPI, python-multipart, pdfplumber, PyMuPDF, Pydantic, pytest, pytest-asyncio, pytest-cov, httpx, openai, openpyxl)
- [x] T003 [P] Configure linting and formatting tools (pyproject.toml with Black + Ruff settings)
- [x] T004 [P] Create .env.example with DATABASE_PATH, USE_SQLITE_PIPELINE, CACHE_TTL_DAYS, MAX_UPLOAD_FILES, OPENAI_API_KEY, OPENAI_API_BASE

---

## Phase 2: Foundational (Blocking Prerequisites) ✅ 完成

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Setup SQLite database initialization with PRAGMA settings in src/models/database.py (WAL, NORMAL sync, foreign_keys, busy_timeout=5000)
- [x] T006 [P] Create SQLite schema migrations for all 6 tables in src/models/database.py (processing_batches, uploaded_files, processing_stages, furniture_items, fabric_items, cache_records)
- [x] T007 [P] Implement ProcessingBatch entity in src/models/entities.py with status enum (PENDING, RUNNING, COMPLETED, FAILED)
- [x] T008 [P] Implement UploadedFile entity in src/models/entities.py with file_role enum (QUANTITY_SHEET, SPEC_SHEET, FABRIC_SHEET, INDEX)
- [x] T009 [P] Implement ProcessingStage entity in src/models/entities.py with stage_name enum (7 stages)
- [x] T010 [P] Implement FurnitureItem entity in src/models/entities.py with status enum
- [x] T011 [P] Implement FabricItem entity in src/models/entities.py with status enum
- [x] T012 [P] Implement CacheRecord entity in src/models/entities.py
- [x] T013 Create Pydantic request/response schemas in src/models/schemas.py (QuoteResponse, QuoteItem, StatusResponse, ErrorResponse per openapi.yaml)
- [x] T014 Create FastAPI application skeleton in src/api/main.py with CORS, lifespan events, error handlers
- [x] T015 [P] Implement structured logging infrastructure in src/utils/logger.py (繁體中文訊息)
- [x] T016 [P] Create configuration management in src/api/deps.py with Settings class (Pydantic BaseSettings)
- [x] T017 Create base test fixtures in tests/conftest.py (test database, test client, sample PDF fixtures)
- [x] T017a [P] Implement batch queue lock mechanism in src/services/queue.py (FR-013: single batch execution, asyncio.Lock + DB status check)
- [x] T017b [P] Unit test for queue lock in tests/unit/test_queue.py (concurrent batch rejection, lock release on completion/failure)

### Adapter 架構擴展（多供應商支援） ✅ 已完成

- [x] T017c Create adapters directory structure (src/services/adapters/__init__.py, base.py, registry.py)
- [x] T017d Implement SupplierAdapter Protocol in src/services/adapters/base.py (detect_file_role, get_extraction_prompt, normalize_item_no, is_fabric_item, map_to_output)
- [x] T017e [P] Implement AdapterRegistry in src/services/adapters/registry.py (load from YAML, auto-discover adapters)
- [x] T017f [P] Implement FairmontAdapter in src/services/adapters/fairmont.py (YAML-driven rules)
- [x] T017g [P] Implement GenericAdapter in src/services/adapters/generic.py (LLM dynamic detection fallback)
- [x] T017h Create configs/suppliers/fairmont.yaml (role_detection, item_normalization, fabric_detection, prompts)
- [x] T017i [P] Unit test for adapters in tests/unit/test_adapters.py (registry loading, role detection, normalization)

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - PDF 上傳與報價單產出 (Priority: P1) 🎯 MVP ✅ 完成

**Goal**: 使用者上傳多份 PDF，系統產出 17 欄位 JSON 報價單

**Independent Test**: 上傳完整 PDF 組合，驗證回傳 JSON 包含正確 17 欄位、合併數量、嵌入圖片 (Base64)

### Tests for User Story 1 ✅

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T018 [P] [US1] Unit test for Item No. normalizer in tests/unit/test_item_normalizer.py (DLX-201 .1 → DLX-201.1)
- [x] T019 [P] [US1] Unit test for PDF parser in tests/unit/test_pdf_parser.py (text/table extraction)
- [x] T020 [P] [US1] Unit test for pipeline stages in tests/unit/test_pipeline.py (7 stage transitions)
- [x] T021 [P] [US1] Integration test for quote API in tests/integration/test_quote_api.py (full upload → JSON flow)

### Implementation for User Story 1 ✅

- [x] T022 [P] [US1] Implement Item No. normalizer in src/utils/item_normalizer.py (FR-015: remove spaces, unify dashes)
- [x] T023 [P] [US1] Implement PDF parser service in src/services/pdf_parser.py (pdfplumber for text/tables)
- [x] T024 [P] [US1] Implement image extractor in src/services/pdf_parser.py (PyMuPDF for images, FR-005: dedup, best resolution)
- [x] T025 [US1] Implement LLM client for APMIC in src/services/llm_client.py (OpenAI-compatible, verify=False, temperature=0.1)
- [x] T025a [US1] Implement content chunking strategy in src/services/llm_client.py (FR-010: split content > 2K tokens, merge partial responses, handle chunk boundaries at logical breaks)
- [x] T025b [P] [US1] Unit test for chunking in tests/unit/test_llm_client.py (large content splitting, response merging, boundary handling)
- [x] T026 [US1] Implement Stage 1: PDF_PARSING in src/services/pipeline.py (parse all uploaded PDFs)
- [x] T027 [US1] Implement Stage 2: EXTRACTION in src/services/pipeline.py (extract structured items via LLM)
- [x] T028 [US1] Implement Stage 3: NORMALIZATION in src/services/pipeline.py (normalize Item No. using item_normalizer)
- [x] T029 [US1] Implement Stage 4: MERGING in src/services/pipeline.py (merge quantity sheet with spec sheet, FR-006: qty from quantity sheet)
- [x] T030 [US1] Implement Stage 5: FURNITURE_EXTRACTION in src/services/pipeline.py (extract furniture details)
- [x] T031 [US1] Implement Stage 6: FABRIC_LINKING in src/services/pipeline.py (link 500-series fabrics via FURNITURE COM, FR-016)
- [x] T032 [US1] Implement Stage 7: EXPORT in src/services/pipeline.py (generate 15-field JSON output)
- [x] T033 [US1] Implement PDF role detection in src/services/pdf_parser.py (FR-002: identify QUANTITY_SHEET, SPEC_SHEET, FABRIC_SHEET, INDEX)
- [x] T034 [US1] Implement POST /api/v1/quote/process endpoint in src/api/routes/quote.py (accept list[UploadFile])
- [x] T035 [US1] Implement image type classification in src/services/pdf_parser.py (FR-018: furniture photo, fabric sample, engineering drawing)
- [x] T036 [US1] Implement smart matching for Item No. mismatch in src/services/pipeline.py (FR-017: fallback to Description matching)
- [x] T037 [US1] Add繁體中文 error messages in src/api/routes/quote.py (FR-014)

**Checkpoint**: User Story 1 完成 - 核心 PDF 上傳與 JSON 產出功能可獨立測試

---

## Phase 4: User Story 2 - 斷點續傳與失敗恢復 (Priority: P2) ✅ 完成

**Goal**: 系統中斷後能從最後完成階段繼續處理

**Independent Test**: 在第 4 階段手動終止，重啟後驗證從第 4 階段繼續

### Tests for User Story 2

- [x] T038 [P] [US2] Unit test for checkpoint save/restore in tests/unit/test_pipeline.py (checkpoint_data JSON)
- [x] T039 [P] [US2] Integration test for resume in tests/integration/test_quote_api.py (interrupt + resume flow)

### Implementation for User Story 2

- [x] T040 [US2] Implement checkpoint saving after each stage completion in src/services/pipeline.py (FR-007: persist to ProcessingStage.checkpoint_data)
- [x] T041 [US2] Implement resume logic in pipeline orchestrator src/services/pipeline.py (FR-008: query last COMPLETED stage)
- [x] T042 [US2] Implement stage recovery in src/services/pipeline.py (load checkpoint_data, resume from breakpoint)
- [x] T043 [US2] Implement retry with exponential backoff in src/services/llm_client.py (FR-020: 3 retries)
- [x] T044 [US2] Add stage-level logging in src/services/pipeline.py (FR-019: start_time, end_time, error_message)

**Checkpoint**: User Story 2 完成 - 斷點續傳功能可獨立測試

---

## Phase 5: User Story 3 - 快取機制與重複檔案處理 (Priority: P3) ✅ 完成

**Goal**: 相同檔案秒級返回快取結果

**Independent Test**: 上傳相同 PDF 兩次，第二次 < 3 秒返回

### Tests for User Story 3

- [x] T045 [P] [US3] Unit test for file hash calculation in tests/unit/test_cache.py (SHA256)
- [x] T046 [P] [US3] Integration test for cache hit in tests/integration/test_quote_api.py (second upload < 3s)

### Implementation for User Story 3

- [x] T047 [US3] Implement file hash calculation in src/services/cache.py (SHA256, FR-009)
- [x] T048 [US3] Implement cache lookup in src/services/cache.py (check CacheRecord by file_hash)
- [x] T049 [US3] Implement cache storage after successful processing in src/services/cache.py (store result_path, expires_at)
- [x] T050 [US3] Integrate cache check in POST /api/v1/quote/process in src/api/routes/quote.py (early return if cached)
- [x] T051 [US3] Implement cache expiration cleanup in src/services/cache.py (FR-021: delete records > 1 day)
- [x] T052 [US3] Add scheduled cache cleanup task in src/api/main.py (daily cleanup on startup)

**Checkpoint**: User Story 3 完成 - 快取機制可獨立測試

---

## Phase 6: User Story 4 - 處理進度即時回報 (Priority: P4) ✅ 完成

**Goal**: 前端可查詢當前處理進度

**Independent Test**: 呼叫 GET /api/v1/quote/status/{batch_id}，返回階段 4/7, 35%

### Tests for User Story 4

- [x] T053 [P] [US4] Unit test for progress calculation in tests/unit/test_pipeline.py (stage → percent mapping)
- [x] T054 [P] [US4] Integration test for status API in tests/integration/test_quote_api.py (GET /status returns correct stage)

### Implementation for User Story 4

- [x] T055 [US4] Implement progress percentage calculation in src/services/pipeline.py (FR-011: stage_number / 7 * 100)
- [x] T056 [US4] Implement GET /api/v1/quote/status/{batch_id} endpoint in src/api/routes/quote.py (per openapi.yaml StatusResponse)
- [x] T057 [US4] Update pipeline to write progress_percent during stage execution in src/services/pipeline.py
- [x] T058 [US4] Add estimated_completion calculation in src/services/pipeline.py (based on avg stage time)

**Checkpoint**: User Story 4 完成 - 進度查詢功能可獨立測試

---

## Phase 7: User Story 5 - 架構切換與回退 (Priority: P5) ✅ 完成

**Goal**: 透過環境變數切換新舊處理架構

**Independent Test**: 設定 USE_SQLITE_PIPELINE=false，驗證使用舊架構

### Tests for User Story 5

- [x] T059 [P] [US5] Unit test for feature toggle in tests/unit/test_deps.py (env var parsing)
- [x] T060 [P] [US5] Integration test for architecture switching in tests/integration/test_quote_api.py (toggle behavior)

### Implementation for User Story 5

- [x] T061 [US5] Implement feature toggle check in src/api/deps.py (USE_SQLITE_PIPELINE env var, FR-012)
- [x] T062 [US5] Implement architecture router in src/api/routes/quote.py (route to new or legacy handler)
- [x] T063 [US5] Create legacy handler stub in src/services/legacy_pipeline.py (placeholder for old architecture)

**Checkpoint**: User Story 5 完成 - 架構切換功能可獨立測試

---

## Phase 8: Polish & Cross-Cutting Concerns ✅ 完成

**Purpose**: Improvements that affect multiple user stories

- [x] T064 [P] Implement GET /api/v1/health endpoint in src/api/routes/quote.py (per openapi.yaml)
- [x] T065 [P] Add database connection health check in src/api/routes/quote.py
- [x] T066 Run pytest --cov=src --cov-report=html and verify >= 80% coverage
- [x] T067 Run Black and Ruff on all files, fix warnings
- [x] T068 Validate quickstart.md instructions (install → init → run → test)
- [x] T069 Test with real PDF samples from docs/ folder

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - US1 must complete before US2 (checkpoint depends on pipeline)
  - US3 can run parallel to US2 (independent)
  - US4 can run after US1 (needs pipeline for progress)
  - US5 can run parallel to others (just routing)
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

```
       ┌──────────────────────────────────────────────────────┐
       │              Phase 2: Foundational                   │
       └───────────────────────┬──────────────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
         ▼                     ▼                     ▼
   ┌─────────┐           ┌─────────┐           ┌─────────┐
   │   US1   │───────────│   US3   │           │   US5   │
   │  (P1)   │           │  (P3)   │           │  (P5)   │
   └────┬────┘           └─────────┘           └─────────┘
        │
        ├─────────────────────┐
        │                     │
        ▼                     ▼
   ┌─────────┐           ┌─────────┐
   │   US2   │           │   US4   │
   │  (P2)   │           │  (P4)   │
   └─────────┘           └─────────┘
```

- **US1 (P1)**: Can start after Foundational - Core MVP
- **US2 (P2)**: Depends on US1 (checkpoint needs pipeline stages)
- **US3 (P3)**: Can start after Foundational - Independent caching
- **US4 (P4)**: Depends on US1 (progress needs pipeline)
- **US5 (P5)**: Can start after Foundational - Just routing logic

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models → Services → Endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

**Phase 2 (Foundational)**:
```bash
# All entity implementations can run in parallel:
T007, T008, T009, T010, T011, T012  # 6 entities in parallel
T015, T016  # Logger and config in parallel
```

**Phase 3 (US1)**:
```bash
# All tests in parallel:
T018, T019, T020, T021  # 4 tests in parallel

# Parser components in parallel:
T022, T023, T024  # normalizer, parser, extractor

# Stages 1-3 can be developed in parallel (different functions):
T026, T027, T028
```

**Multiple User Stories**:
```bash
# After US1 completes, these can run in parallel:
US2 (T038-T044) || US3 (T045-T052) || US4 (T053-T058) || US5 (T059-T063)
```

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: T018 "Unit test for Item No. normalizer in tests/unit/test_item_normalizer.py"
Task: T019 "Unit test for PDF parser in tests/unit/test_pdf_parser.py"
Task: T020 "Unit test for pipeline stages in tests/unit/test_pipeline.py"
Task: T021 "Integration test for quote API in tests/integration/test_quote_api.py"

# Launch parser components together:
Task: T022 "Implement Item No. normalizer in src/utils/item_normalizer.py"
Task: T023 "Implement PDF parser service in src/services/pdf_parser.py"
Task: T024 "Implement image extractor in src/services/pdf_parser.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test with real PDFs from docs/
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → Test with real PDFs → **MVP Ready!**
3. Add User Story 2 → Test checkpoint/resume → Robust processing
4. Add User Story 3 → Test cache hit → Performance optimized
5. Add User Story 4 → Test progress API → UX improved
6. Add User Story 5 → Test toggle → Production ready

### Suggested MVP Scope

**MVP = Phase 1 + Phase 2 + Phase 3 (User Story 1)**

This delivers:
- PDF upload endpoint (POST /api/v1/quote/process)
- 7-stage SQLite pipeline
- 15-field JSON output with images
- Item No. normalization
- Qty merging (quantity sheet priority)
- Fabric linking (500-series)

---

## Task Summary

| Phase | User Story | Task Count | Parallel Tasks | Status |
|-------|------------|------------|----------------|--------|
| 1 | Setup | 4 | 2 | ⏳ |
| 2 | Foundational | 17 | 12 | ⏳ |
| 2.5 | Adapter 架構 | 7 | 4 | ✅ 完成 |
| 3 | US1 (P1) MVP | 22 | 9 | ⏳ |
| 4 | US2 (P2) | 7 | 2 | ⏳ |
| 5 | US3 (P3) | 8 | 2 | ⏳ |
| 6 | US4 (P4) | 6 | 2 | ⏳ |
| 7 | US5 (P5) | 5 | 2 | ⏳ |
| 8 | Polish | 6 | 2 | ⏳ |
| **Total** | | **80** | **35** | **7/80** |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- All error messages in 繁體中文 (FR-014)
- LLM calls via APMIC (api.apmic-ai.com) with verify=False
