"""LLM 客戶端封裝 (APMIC OpenAI-compatible API)"""

import asyncio
import json
import re
from typing import Any

import httpx
from openai import OpenAI

from src.api.deps import get_settings


def get_llm_client() -> OpenAI:
    """取得 OpenAI 客戶端 (APMIC)

    使用 verify=False 處理自簽憑證
    """
    settings = get_settings()

    http_client = httpx.Client(verify=False)

    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        http_client=http_client,
    )


def split_content_to_chunks(content: str, max_tokens: int = 2000) -> list[str]:
    """將大內容分割成多個 chunks (FR-010)

    在邏輯斷點 (段落、換行) 分割

    Args:
        content: 原始內容
        max_tokens: 每個 chunk 的最大 token 數

    Returns:
        分割後的 chunks 列表
    """
    if not content:
        return [""]

    # 估計每個 token 約 4 個字元 (英文)，中文約 1.5 個字元
    # 混合中英文使用更保守的估計: 2 字元/token
    max_chars = max_tokens * 2

    if len(content) <= max_chars:
        return [content]

    chunks = []
    current_chunk = ""

    # 按段落分割
    paragraphs = re.split(r"\n\n+", content)

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_chars:
            if current_chunk:
                current_chunk += "\n\n"
            current_chunk += para
        else:
            # 當前段落太長，需要進一步分割
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            if len(para) <= max_chars:
                current_chunk = para
            else:
                # 按句子分割
                sentences = re.split(r"(?<=[.!?。！？])\s+", para)
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 1 <= max_chars:
                        if current_chunk:
                            current_chunk += " "
                        current_chunk += sentence
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks if chunks else [content]


def merge_json_responses(responses: list[str]) -> list[dict]:
    """合併多個 JSON 回應 (FR-010)

    Args:
        responses: JSON 字串列表

    Returns:
        合併後的物件列表
    """
    merged = []

    for response in responses:
        try:
            # 嘗試解析 JSON
            data = extract_json_from_response(response)
            if isinstance(data, list):
                merged.extend(data)
            elif isinstance(data, dict):
                merged.append(data)
        except (json.JSONDecodeError, ValueError):
            # 跳過無效 JSON
            continue

    return merged


def extract_json_from_response(response: str) -> Any:
    """從 LLM 回應中提取 JSON

    Args:
        response: LLM 回應文字

    Returns:
        解析後的 JSON 物件

    Raises:
        ValueError: 如果找不到有效 JSON
    """
    if not response:
        raise ValueError("回應為空")

    # 嘗試直接解析
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # 嘗試提取 JSON 陣列
    json_match = re.search(r"\[[\s\S]*\]", response)
    if json_match:
        try:
            fixed = fix_json_errors(json_match.group(0))
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    # 嘗試提取 JSON 物件
    json_match = re.search(r"\{[\s\S]*\}", response)
    if json_match:
        try:
            fixed = fix_json_errors(json_match.group(0))
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"無法從回應中提取 JSON: {response[:100]}...")


def fix_json_errors(json_str: str) -> str:
    """修復常見 JSON 錯誤

    Args:
        json_str: 可能有錯誤的 JSON 字串

    Returns:
        修復後的 JSON 字串
    """
    # 移除尾隨逗號
    result = re.sub(r",\s*([}\]])", r"\1", json_str)

    # 將單引號替換為雙引號 (簡單情況)
    # 注意：這個替換不夠完美，但對於大多數情況足夠
    if "'" in result and '"' not in result:
        result = result.replace("'", '"')

    # 修復 unquoted keys
    result = re.sub(r"(\{|\,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', result)

    return result


class LLMClient:
    """LLM 客戶端"""

    def __init__(self):
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """延遲初始化客戶端"""
        if self._client is None:
            self._client = get_llm_client()
        return self._client

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 8192,
        temperature: float = 0.1,
    ) -> str:
        """呼叫 LLM API

        Args:
            system_prompt: 系統提示
            user_prompt: 使用者提示
            max_tokens: 最大輸出 token
            temperature: 溫度參數

        Returns:
            LLM 回應文字
        """
        settings = get_settings()

        response = await asyncio.to_thread(
            self.client.chat.completions.create,
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        return response.choices[0].message.content or ""

    async def call_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 8192,
        temperature: float = 0.1,
        max_retries: int | None = None,
        timeout_seconds: int | None = None,
    ) -> str:
        """帶重試的 LLM 呼叫 (FR-020)

        Args:
            system_prompt: 系統提示
            user_prompt: 使用者提示
            max_tokens: 最大輸出 token
            temperature: 溫度參數
            max_retries: 最大重試次數
            timeout_seconds: 超時秒數

        Returns:
            LLM 回應文字
        """
        settings = get_settings()
        retries = max_retries or settings.openai_max_retries
        timeout = timeout_seconds or settings.openai_timeout_seconds

        last_error = None

        for attempt in range(retries + 1):
            try:
                response = await asyncio.wait_for(
                    self.call(system_prompt, user_prompt, max_tokens, temperature),
                    timeout=timeout,
                )
                return response
            except TimeoutError:
                last_error = "逾時"
                wait_time = 2 ** (attempt + 1)
                await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = str(e)
                if "rate" in str(e).lower() and attempt < retries:
                    wait_time = 2 ** (attempt + 1)
                    await asyncio.sleep(wait_time)
                elif attempt >= retries:
                    raise

        raise RuntimeError(f"LLM 呼叫失敗 (重試 {retries} 次): {last_error}")

    async def call_chunked(
        self,
        system_prompt: str,
        content: str,
        max_tokens: int = 2000,
    ) -> list[dict]:
        """分塊呼叫 LLM (FR-010)

        將大內容分割成多個 chunks，分別處理後合併

        Args:
            system_prompt: 系統提示
            content: 大內容
            max_tokens: 每個 chunk 的最大 token

        Returns:
            合併後的結果列表
        """
        chunks = split_content_to_chunks(content, max_tokens)
        responses = []

        for i, chunk in enumerate(chunks):
            chunk_prompt = f"[區塊 {i+1}/{len(chunks)}]\n\n{chunk}"
            response = await self.call_with_retry(system_prompt, chunk_prompt)
            responses.append(response)

        return merge_json_responses(responses)


# 全域單例
_llm_client: LLMClient | None = None


def get_llm() -> LLMClient:
    """取得 LLM 客戶端單例"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
