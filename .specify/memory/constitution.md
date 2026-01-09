<!--
============================================================================
SYNC IMPACT REPORT
============================================================================
Version Change: N/A → 1.0.0 (Initial ratification)
Bump Rationale: Initial constitution establishment for PDF Q&A System

Modified Principles: N/A (new document)

Added Sections:
- Core Principles (5 principles)
  - I. 代碼品質 (Code Quality)
  - II. 測試標準 (Testing Standards)
  - III. UX 一致性 (UX Consistency)
  - IV. 效能要求 (Performance Standards)
  - V. 語言要求 (Language Requirements)
- Governance

Removed Sections: N/A (template sections replaced)

Templates Requiring Updates:
- .specify/templates/plan-template.md ✅ No updates needed (Constitution Check
  section already references constitution file dynamically)
- .specify/templates/spec-template.md ✅ No updates needed (Requirements section
  is generic and aligns with constitution principles)
- .specify/templates/tasks-template.md ✅ No updates needed (Test-first workflow
  mentioned aligns with Principle II)
- .specify/templates/commands/*.md ⚠️ Directory does not exist - N/A

Follow-up TODOs: None
============================================================================
-->

# PDF Q&A System Constitution

## Core Principles

### I. 代碼品質 (Code Quality)

- 自文檔化代碼，命名清晰。
- 合併前強制進行代碼審查。
- 語法檢查/格式化零警告。
- 公共 API 必須具有內嵌文件。
- 第三方依賴需要安全審查。

### II. 測試標準 (Testing Standards - NON-NEGOTIABLE)

- **測試優先開發**：編寫測試 → 驗證失敗 → 實作 → 驗證通過。
- 最低 80% 代碼覆蓋率（關鍵路徑 100%）。
- 必需的測試類型：單元、整合、E2E。
- 合併前所有測試必須通過。

### III. UX 一致性 (UX Consistency)

- WCAG 2.1 Level AA 可訪問性合規。
- 響應式設計（行動/平板/桌面）。
- 繁體中文清晰的錯誤訊息。
- 操作 >100ms 的載入狀態。
- 國際化支援。

### IV. 效能要求 (Performance Standards)

- API 回應時間：<300ms (p95) 標準、Q&A <15 秒。
- 頁面載入：<2 秒。
- 支援 10+ 併發使用者。
- 資料庫查詢必須使用索引（無 N+1 問題）。

### V. 語言要求 (Language Requirements)

- **繁體中文 (zh-TW)**：規格、計畫、使用者文件、API 文件、UI 文字、錯誤訊息。
- **允許英文**：代碼註解、內部筆記、第三方文件。

## Governance

- 憲法高於所有其他實踐。
- 修訂需要記錄、批准和遷移計畫。
- 所有 PR/審查必須驗證合規性。

**Version**: 1.0.0 | **Ratified**: 2026-01-07 | **Last Amended**: 2026-01-07
