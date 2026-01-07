"""LLM 客戶端單元測試 (T025b)"""



class TestContentChunking:
    """內容分塊策略測試 (FR-010)"""

    def test_split_large_content(self):
        """測試大內容分割 (> 2K tokens)"""
        from src.services.llm_client import split_content_to_chunks

        # 模擬有段落分隔的大內容
        paragraph = "This is a paragraph of text. " * 50  # ~1500 chars per paragraph
        large_content = "\n\n".join([paragraph] * 10)  # ~15000 chars

        chunks = split_content_to_chunks(large_content, max_tokens=2000)

        assert len(chunks) > 1
        for chunk in chunks:
            # 每個 chunk 應該 <= max_tokens * 3 (估計每 token 3 chars)
            assert len(chunk) <= 2000 * 3

    def test_small_content_no_split(self):
        """測試小內容不分割"""
        from src.services.llm_client import split_content_to_chunks

        small_content = "Short content"
        chunks = split_content_to_chunks(small_content, max_tokens=2000)

        assert len(chunks) == 1
        assert chunks[0] == small_content

    def test_chunk_at_logical_breaks(self):
        """測試在邏輯斷點分割"""
        from src.services.llm_client import split_content_to_chunks

        content = "Paragraph 1.\n\nParagraph 2.\n\nParagraph 3." * 100
        chunks = split_content_to_chunks(content, max_tokens=500)

        # 應該在段落邊界分割
        for chunk in chunks:
            # 不應該在句子中間斷開
            assert not chunk.startswith(".")
            assert not chunk.startswith(" ")

    def test_handle_empty_content(self):
        """測試處理空內容"""
        from src.services.llm_client import split_content_to_chunks

        chunks = split_content_to_chunks("", max_tokens=2000)
        assert chunks == [""]


class TestResponseMerging:
    """回應合併測試"""

    def test_merge_json_arrays(self):
        """測試合併 JSON 陣列"""
        from src.services.llm_client import merge_json_responses

        responses = [
            '[{"item_no": "DLX-100"}]',
            '[{"item_no": "DLX-200"}]',
        ]

        merged = merge_json_responses(responses)
        assert len(merged) == 2
        assert merged[0]["item_no"] == "DLX-100"
        assert merged[1]["item_no"] == "DLX-200"

    def test_merge_partial_json(self):
        """測試合併部分 JSON (跨邊界)"""
        from src.services.llm_client import merge_json_responses

        # 模擬跨邊界的情況
        responses = [
            '[{"item_no": "DLX-100", "description": "Table"}]',
            '[{"item_no": "DLX-200"}]',
        ]

        merged = merge_json_responses(responses)
        assert len(merged) == 2

    def test_handle_invalid_json(self):
        """測試處理無效 JSON"""
        from src.services.llm_client import merge_json_responses

        responses = [
            '[{"item_no": "DLX-100"}]',
            "invalid json",
            '[{"item_no": "DLX-200"}]',
        ]

        merged = merge_json_responses(responses)
        # 應該跳過無效的 JSON，返回有效部分
        assert len(merged) >= 2


class TestLLMClient:
    """LLM 客戶端測試"""

    def test_extract_json_from_response(self):
        """測試從回應中提取 JSON"""
        from src.services.llm_client import extract_json_from_response

        # 包含 JSON 的文字回應
        response = """Here is the result:
        [{"item_no": "DLX-100", "description": "Table"}]
        Done."""

        result = extract_json_from_response(response)
        assert len(result) == 1
        assert result[0]["item_no"] == "DLX-100"

    def test_extract_json_object_from_response(self):
        """測試從回應中提取 JSON 物件"""
        from src.services.llm_client import extract_json_from_response

        response = 'The item is: {"item_no": "DLX-100"}'
        result = extract_json_from_response(response)
        assert result["item_no"] == "DLX-100"

    def test_fix_common_json_errors(self):
        """測試修復常見 JSON 錯誤"""
        from src.services.llm_client import fix_json_errors

        # 尾隨逗號
        json_with_trailing_comma = '{"item": "value",}'
        fixed = fix_json_errors(json_with_trailing_comma)
        assert fixed == '{"item": "value"}'

        # 單引號
        json_with_single_quotes = "{'item': 'value'}"
        fixed = fix_json_errors(json_with_single_quotes)
        assert '"item"' in fixed
