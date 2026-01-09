# APMIC PrivAI API Reference

> Last Updated: 2026-01-07 (基於 Fairmont BOQ 系統實際整合經驗更新)

## Table of Contents

1. [Overview](#overview)
2. [Implementation Status](#implementation-status)
3. [Fairmont 專案實際使用狀況](#fairmont-專案實際使用狀況)
4. [Authentication](#authentication)
5. [OpenAI Compatible API (/v1/)](#openai-compatible-api-v1)
6. [search_kwargs Parameters](#search_kwargs-parameters)
7. [LLM API (/api/llm/)](#llm-api-apillm)
8. [Known Limitations](#known-limitations)
9. [Usage Examples](#usage-examples)
10. [RAG Patterns](#rag-patterns)
11. [改進建議與缺失分析](#改進建議與缺失分析)

---

## Overview

APMIC PrivAI Platform provides two API styles:

| Type | Path Prefix | Description | LangChain Integration |
|------|-------------|-------------|----------------------|
| **OpenAI Compatible** | `/v1/` | Follows OpenAI API spec | Direct use of `langchain-openai` |
| **APMIC Native** | `/api/` | APMIC-specific features | Requires custom wrapper |

### Base URL

```
https://api.apmic-ai.com
```

---

## Implementation Status

### OpenAI Compatible API (/v1/)

| Endpoint | Method | Status | Fairmont 使用狀況 |
|----------|--------|--------|------------------|
| `/v1/models` | GET | **IMPL** ✅ | 驗證可用模型清單 |
| `/v1/chat/completions` | POST | **IMPL** ✅ | **核心使用** - PDF 解析、Item 提取 |
| `/v1/chat/references` | POST | **IMPL** | 未使用（無 RAG 需求）|
| `/v1/embeddings` | POST | **NOT IMPL** | 未使用 |
| `/v1/files` | GET/POST/DELETE | **IMPL** | 未使用（PDF 本地處理）|
| `/v1/filesets` | GET/POST/PUT/DELETE | **IMPL** | 未使用 |
| `/v1/qa/generate` | POST | **IMPL** ✅ | 未使用（可用於未來擴展）|
| `/v1/prompts/*` | CRUD | **IMPL** ✅ | 未使用（Skills YAML 為主）|

### APMIC Native API (/api/llm/)

| Endpoint | Method | Status | Fairmont 使用狀況 |
|----------|--------|--------|------------------|
| `/api/llm/ot/embedding` | POST | **IMPL** | 未使用 |
| `/api/llm/ot/question` | POST | **IMPL** | 未使用 |
| `/api/llm/ot/vision` | POST | **NOT SUPPORTED** | N/A（圖片用 PyMuPDF 處理）|

---

## Fairmont 專案實際使用狀況

> 📅 **更新**: 2026-01-07 - 基於 SQLite Multi-Stage Pipeline 實際運作經驗

### 核心整合方式

Fairmont BOQ 系統使用 OpenAI Python SDK 透過 `/v1/chat/completions` 端點與 APMIC 互動。

```python
# backend/app/services/pdf_parser.py
import httpx
from openai import OpenAI

# 處理 APMIC 自簽憑證
http_client = httpx.Client(verify=False)

client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,  # https://api.apmic-ai.com/v1
    http_client=http_client,
)
```

### 使用場景與 Token 消耗

| Pipeline Stage | LLM 用途 | 平均 Token 消耗 | 超時設定 |
|----------------|----------|----------------|----------|
| Stage 3: Item Detection | 偵測 item_no + source_page | ~1.7K tokens/call | 120 秒 |
| Stage 4: Item Extraction | 每項目詳細欄位提取 | ~2K tokens/call | 60 秒/item |
| Stage 6: Quantity Merge | 數量總表解析 | ~1.5K tokens/call | 120 秒 |
| Metadata Extraction | 專案名稱提取 | ~0.5K tokens/call | 30 秒 |

### 實際 API 呼叫配置

```python
response = client.chat.completions.create(
    model="gemma-3-12b",       # 或 ace-1-24b-reasoning-v1
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ],
    temperature=0.1,           # 低溫度確保 JSON 輸出穩定
    max_tokens=8192,           # 足夠容納 BOQ JSON 輸出
)
```

### JSON 輸出策略

APMIC 未支援 OpenAI 的 `response_format={"type": "json_object"}`，Fairmont 透過 prompt engineering 達成：

1. **System Prompt 指示**：明確要求「只輸出 JSON，不要任何說明」
2. **低溫度設定**：`temperature=0.1` 降低隨機性
3. **JSON 解析容錯**：使用 regex 提取 `[...]` 或 `{...}` 區塊
4. **修復機制**：移除尾隨逗號、修復 unquoted keys

```python
# JSON 提取邏輯 (pdf_parser.py:811-819)
json_start = response_text.find("[")
json_end = response_text.rfind("]") + 1
if json_start != -1 and json_end > json_start:
    json_str = response_text[json_start:json_end]
    items = json.loads(json_str)
```

### 錯誤處理與重試

```python
# 重試配置 (config.py)
openai_max_retries: int = 2        # 最多重試 2 次
openai_timeout_seconds: int = 300  # 5 分鐘超時

# 重試邏輯 (pdf_parser.py:308-402)
for attempt in range(max_retries + 1):
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(client.chat.completions.create, ...),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        wait_time = 2 ** (attempt + 1)  # 指數退避：2, 4, 8 秒
        await asyncio.sleep(wait_time)
```

### 實際觀察到的 Token 使用量

| 操作 | Input Tokens | Output Tokens | Total |
|------|-------------|---------------|-------|
| Item Detection (15 頁 PDF) | ~800-1200 | ~200-400 | ~1000-1600 |
| Item Extraction (單項目) | ~400-600 | ~150-300 | ~550-900 |
| Metadata Extraction | ~600-800 | ~50-100 | ~650-900 |

---

## Authentication

### OpenAI Compatible API (`/v1/`)

```http
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

### APMIC Native API (`/api/`)

```http
auth: <API_KEY>
Content-Type: application/json
```

**Note**: Native API uses lowercase `auth` header, not `Authorization`

---

## OpenAI Compatible API (/v1/)

### Models

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/models` | List available models |

**Available Models** (2026-01-07 驗證):

| Model | Description | Context Window | Fairmont 建議用途 |
|-------|-------------|----------------|------------------|
| `gemma-3-12b` | Fast model | 8K-32K | **主要使用** - Item Detection/Extraction |
| `ace-1-24b-reasoning-v1` | Reasoning model | 32K+ | 複雜結構解析、深度推理 |
| `apmic-embedding-v1` | Embedding model | N/A | 2048 dimensions（未使用）|

> ⚠️ **Context Window 限制**: `gemma-3-12b` 的 8K context window 是 Fairmont 採用 SQLite Multi-Stage Pipeline 的主要原因

---

### Chat Completions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/chat/completions` | Chat completion (OpenAI compatible) |

**Fairmont 實際使用的 Request**:
```json
{
  "model": "gemma-3-12b",
  "messages": [
    {"role": "system", "content": "你是專業的家具報價單解析助手..."},
    {"role": "user", "content": "從以下 PDF 內容提取所有 BOQ 項目..."}
  ],
  "max_tokens": 8192,
  "temperature": 0.1
}
```

**Response** (實際觀察):
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1704067200,
  "model": "gemma-3-12b",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "[{\"item_no\": \"DLX-100\", \"description\": \"King Bed\", ...}]"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 951,
    "completion_tokens": 230,
    "total_tokens": 1181
  }
}
```

---

### Chat References

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/chat/references` | Get RAG references only |

**Fairmont 未使用此端點** - 無 RAG 需求，PDF 內容直接注入 prompt。

---

### Files & Filesets

Fairmont 專案未使用 Files/Filesets API，PDF 處理流程如下：

```
前端上傳 PDF → FastAPI 暫存 → PyMuPDF 提取文字 → 注入 LLM Prompt → 解析 JSON
```

---

## search_kwargs Parameters

> **CRITICAL**: APMIC search_kwargs does NOT support `filter`. Use Python-layer filtering instead (Two-Pass RAG).

### Supported Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `distance_score_threshold` | float | Vector distance threshold (0-1, higher = stricter) | 0.85 |
| `k` | int | Number of vectors to retrieve | 20 |
| `rerank_score_threshold` | float | Rerank score threshold | 0.3 |
| `n` | int | Final number of results after rerank | 5 |

### NOT Supported

| Parameter | Status | Alternative |
|-----------|--------|-------------|
| `filter` | **NOT SUPPORTED** | Use Python-layer filtering (Two-Pass RAG) |

---

## LLM API (/api/llm/)

> APMIC Native API, requires custom wrapper

### Embedding

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/llm/ot/embedding` | Generate text embedding |

**Request**:
```http
POST /api/llm/ot/embedding?embedding_name=apmic-embedding-v1&env=dev
auth: <API_KEY>
Content-Type: application/json

{
  "text": "Text to embed"
}
```

**Response**:
```json
{
  "embedding": [0.123, -0.456, ...]  // 2048 dimensions
}
```

---

### Vision

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/llm/ot/vision` | Vision Q&A (VLM) |

> **NOT SUPPORTED**: Vision API is not implemented.

**Fairmont 替代方案**: PyMuPDF 提取圖片 + 頁面偏移演算法匹配（無 VLM）

---

## QA API (/v1/qa/)

### Generate QA

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/qa/generate` | 從 Fileset 產生 Q&A 對 |

**Fairmont 未使用** - 但可用於未來建立測試資料集

---

## Prompts API (/v1/prompts/)

### 與 Fairmont Skills 架構的關係

| 面向 | Fairmont Skills (YAML) | APMIC Prompts API |
|------|------------------------|-------------------|
| 儲存位置 | `skills/vendors/*.yaml` | 雲端 API |
| 版本控制 | Git | API 內建 |
| 優化方式 | 手動調整 | `/optimize/auto` AI 優化 |
| 離線使用 | ✅ 支援 | ❌ 需網路 |

**建議**: 維持 Skills YAML 為主，APMIC Prompts API 作為 prompt 優化工具

---

## Known Limitations

> 📅 **更新日期**: 2026-01-07 - 基於 Fairmont 實際整合經驗

### 1. Context Window 限制 (已緩解)

**問題**: `gemma-3-12b` 的 8K-32K context window 無法處理完整 PDF

**Fairmont 解決方案**: SQLite Multi-Stage Pipeline
- Stage 3: 輕量偵測，只提取 item_no + source_page (~1.7K tokens)
- Stage 4: Per-item 提取，每項目獨立 LLM 呼叫 (~2K tokens)
- 分頁處理：超過 15 頁的 PDF 自動分段

### 2. JSON Response Format 未支援 (已緩解)

**問題**: `response_format={"type": "json_object"}` 參數無效

**Fairmont 解決方案**: Prompt Engineering
- System prompt 明確指示只輸出 JSON
- temperature=0.1 降低隨機性
- JSON 解析容錯機制

### 3. SSL 憑證驗證 (開發環境)

**問題**: APMIC 使用自簽憑證，預設 HTTPS 請求失敗

**Fairmont 解決方案**:
```python
import httpx
http_client = httpx.Client(verify=False)
client = OpenAI(..., http_client=http_client)
```

### 4. Vision API 不支援 (架構限制)

**問題**: 無法使用 LLM 分析圖片內容

**Fairmont 解決方案**:
- 圖片提取：PyMuPDF
- 圖片匹配：頁面偏移演算法（deterministic，非 AI）

### 5. Streaming 未實作

**影響**: 前端無法顯示即時進度

**Fairmont 現狀**: 批次處理，前端顯示階段進度（非 token-level streaming）

### 6. Rate Limiting 未文件化

**問題**: 未知每分鐘/每小時請求限制

**Fairmont 風險緩解**: 指數退避重試（2, 4, 8 秒）

---

## Usage Examples

### 1. Fairmont 風格的 OpenAI Client 初始化

```python
import httpx
from openai import OpenAI
from app.config import settings

# 停用 SSL 驗證 (APMIC 自簽憑證)
http_client = httpx.Client(verify=False)

client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    http_client=http_client,
)
```

### 2. BOQ Item Detection (Stage 3 風格)

```python
async def detect_items(pdf_text: str) -> list[dict]:
    system_prompt = """你是專業的家具報價單解析助手。
    從 PDF 內容中找出所有項目編號 (item_no) 和所在頁碼 (source_page)。
    只輸出 JSON 陣列，格式：[{"item_no": "DLX-100", "source_page": 3}, ...]"""

    response = client.chat.completions.create(
        model="gemma-3-12b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"PDF 內容：\n{pdf_text}"}
        ],
        temperature=0.1,
        max_tokens=2048,
    )

    # 提取 JSON
    text = response.choices[0].message.content
    json_match = re.search(r'\[[\s\S]*\]', text)
    if json_match:
        return json.loads(json_match.group(0))
    return []
```

### 3. Per-Item Extraction (Stage 4 風格)

```python
async def extract_item_details(item_no: str, context: str) -> dict:
    system_prompt = """提取家具項目的詳細資訊。
    只輸出單一 JSON 物件，包含：item_no, description, dimension, uom, materials_specs, brand, location"""

    user_prompt = f"項目編號: {item_no}\n\n相關內容:\n{context}"

    response = client.chat.completions.create(
        model="gemma-3-12b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1,
        max_tokens=1024,
    )

    text = response.choices[0].message.content
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        return json.loads(json_match.group(0))
    return {}
```

### 4. 帶超時和重試的呼叫

```python
import asyncio

async def call_with_retry(prompt: str, max_retries: int = 2) -> str:
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.chat.completions.create,
                    model="gemma-3-12b",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                ),
                timeout=300,  # 5 分鐘
            )
            return response.choices[0].message.content

        except asyncio.TimeoutError:
            last_error = "Timeout"
            wait_time = 2 ** (attempt + 1)
            await asyncio.sleep(wait_time)

        except Exception as e:
            if "rate" in str(e).lower() and attempt < max_retries:
                wait_time = 2 ** (attempt + 1)
                await asyncio.sleep(wait_time)
            else:
                raise

    raise Exception(f"All retries failed: {last_error}")
```

---

## RAG Patterns

> Fairmont 專案未使用 RAG，以下為 APMIC 支援的 RAG 模式參考

### Pattern 1: Standard RAG (Single Fileset)

```python
llm = llm.bind(
    extra_body={
        "fileset_id": "fs_xxxxx",
        "search_kwargs": {"k": 20, "n": 5}
    }
)
```

### Pattern 2: Two-Pass RAG (Metadata Filtering)

由於 `search_kwargs.filter` 不支援，需使用 Two-Pass 策略：

1. 取得 References（過度提取）
2. Python 層過濾（by file_id, product_code）
3. 重新建構 Context
4. Chat-Only 生成答案

---

## 改進建議與缺失分析

> 📅 **2026-01-07** - 基於 Fairmont BOQ 系統整合經驗提出

### P0 - 嚴重影響開發效率

#### 1. Context Window 資訊不透明

**現況問題**:
- `/v1/models` 端點不回傳 `context_length` 欄位
- 開發者無法程式化判斷模型限制
- 只能透過試錯或文件查詢

**建議改進**:
```json
// GET /v1/models 期望回應
{
  "data": [
    {
      "id": "gemma-3-12b",
      "context_length": 32768,
      "max_output_tokens": 8192,
      "input_token_limit": 24576
    }
  ]
}
```

**影響評估**: Fairmont 因此必須硬編碼分頁策略，無法動態調整

---

#### 2. response_format 參數不支援

**現況問題**:
- OpenAI 的 `response_format={"type": "json_object"}` 無效
- 必須依賴 prompt engineering 確保 JSON 輸出
- 偶爾仍會產出非 JSON 格式的回應

**建議改進**:
```json
{
  "model": "gemma-3-12b",
  "messages": [...],
  "response_format": {"type": "json_object"}
}
```

**影響評估**: Fairmont 約 5% 的 LLM 回應需要 JSON 修復

---

### P1 - 影響生產環境穩定性

#### 3. 錯誤回應格式未標準化

**現況問題**:
- 錯誤回應格式不一致，難以程式化處理
- 缺乏明確的錯誤碼定義

**建議改進**: 採用 OpenAI 標準錯誤格式
```json
{
  "error": {
    "message": "Rate limit exceeded",
    "type": "rate_limit_error",
    "code": "rate_limit_exceeded",
    "param": null
  }
}
```

**常見錯誤碼建議**:

| HTTP Status | Error Code | 說明 |
|-------------|------------|------|
| 400 | `invalid_request_error` | 請求格式錯誤 |
| 401 | `authentication_error` | API Key 無效 |
| 429 | `rate_limit_error` | 速率限制 |
| 500 | `server_error` | 伺服器錯誤 |

---

#### 4. Rate Limiting 策略未文件化

**現況問題**:
- 不知道每分鐘/每小時請求限制
- 無法預估大批量處理的可行性
- 無法實作精確的 throttling

**建議改進**:
1. 文件化各模型的 rate limit
2. 回應 Header 包含剩餘配額資訊
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704067260
```

**影響評估**: Fairmont 目前使用保守的指數退避策略，可能導致不必要的等待

---

### P2 - 功能擴展受限

#### 5. Vision API 不支援

**現況問題**:
- 無法使用 LLM 分析 PDF 中的圖表、工程圖
- 無法實作「圖片內容理解」功能

**建議改進**: 支援 multimodal 請求
```json
{
  "model": "vision-model",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "描述此家具圖片"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
      ]
    }
  ]
}
```

**影響評估**: Fairmont 圖片匹配使用 deterministic 演算法，準確度約 85%

---

#### 6. Streaming 端點未實作

**現況問題**:
- `/v1/chat/completions` 的 `stream=true` 狀態未知
- 前端無法顯示 token-by-token 的生成進度

**建議改進**: 支援 SSE streaming
```http
POST /v1/chat/completions
Content-Type: application/json

{"model": "gemma-3-12b", "messages": [...], "stream": true}
```

**影響評估**: Fairmont 批次處理模式不受影響，但 UX 可改善

---

#### 7. search_kwargs.filter 不支援

**現況問題**:
- RAG 查詢無法依 metadata 過濾
- 必須使用 Two-Pass RAG 模式

**建議改進**:
```json
{
  "search_kwargs": {
    "k": 20,
    "filter": {"product_code": "rider650"}
  }
}
```

**影響評估**: Fairmont 目前無 RAG 需求，但未來擴展會受限

---

### P3 - 文件與開發體驗

#### 8. SSL 憑證處理文件不足

**現況問題**:
- 開發者需要自行發現 SSL 問題
- 無官方建議的解決方案

**建議改進**:
1. 提供正式 SSL 憑證（生產環境）
2. 提供根憑證安裝指南
3. 文件化開發環境的 `verify=False` 設定

---

#### 9. Token 計算工具未提供

**現況問題**:
- 無法預估請求的 token 消耗
- 難以精確規劃分頁策略

**建議改進**: 提供 tokenizer 端點或工具
```http
POST /v1/tokenize
{"model": "gemma-3-12b", "text": "要計算的文字..."}

Response: {"token_count": 256}
```

---

#### 10. 模型能力文件不足

**現況問題**:
- 各模型的最佳使用場景不明確
- JSON 輸出穩定性差異未說明

**建議改進**: 提供模型能力矩陣

| 能力 | gemma-3-12b | ace-1-24b-reasoning-v1 |
|------|-------------|------------------------|
| JSON 輸出穩定性 | 中等 | 高 |
| 長文本理解 | 受限 | 良好 |
| 複雜推理 | 基本 | 優秀 |
| 回應速度 | 快 | 中等 |

---

## 結論

APMIC PrivAI Platform 的 `/v1/chat/completions` 端點已能滿足 Fairmont BOQ 系統的核心需求。透過以下策略成功整合：

1. **SQLite Multi-Stage Pipeline**: 解決 context window 限制
2. **Prompt Engineering**: 達成 JSON 輸出
3. **指數退避重試**: 處理網路/超時錯誤
4. **SSL 繞過**: 開發環境自簽憑證

**優先改進建議**:
1. 在 `/v1/models` 回傳 `context_length`（P0）
2. 支援 `response_format` 參數（P0）
3. 標準化錯誤回應格式（P1）
4. 文件化 rate limiting 策略（P1）

---

## 附錄

### A. 相關文件

- [APMIC 可行性分析](./APMIC_FEASIBILITY_ANALYSIS.md)
- [APMIC 功能請求](./APMIC_FEATURE_REQUEST.md)
- [Fairmont 系統架構](../CLAUDE.md)

### B. 變更記錄

| 版本 | 日期 | 變更說明 |
|------|------|----------|
| 1.0 | 2025-12-31 | 初版 |
| 1.1 | 2025-12-31 | 新增已實作 API (QA, Prompts) |
| 2.0 | 2026-01-07 | 完整重寫：加入 Fairmont 實際使用經驗、改進建議 |
