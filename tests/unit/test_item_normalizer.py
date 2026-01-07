"""Item No. 正規化單元測試 (T018)"""



class TestItemNormalizer:
    """Item No. 正規化器測試"""

    def test_remove_spaces_between_parts(self):
        """測試移除 Item No. 中的多餘空格 (FR-015)

        例如: "DLX-201 .1" → "DLX-201.1"
        """
        from src.utils.item_normalizer import normalize_item_no

        assert normalize_item_no("DLX-201 .1") == "DLX-201.1"
        assert normalize_item_no("ABC -100") == "ABC-100"
        assert normalize_item_no("TEST- 200") == "TEST-200"

    def test_unify_dashes(self):
        """測試統一破折號格式"""
        from src.utils.item_normalizer import normalize_item_no

        # 各種 dash 字元統一為標準 hyphen
        assert normalize_item_no("DLX–100") == "DLX-100"  # en-dash
        assert normalize_item_no("DLX—100") == "DLX-100"  # em-dash
        assert normalize_item_no("DLX‐100") == "DLX-100"  # hyphen
        assert normalize_item_no("DLX−100") == "DLX-100"  # minus sign

    def test_strip_whitespace(self):
        """測試去除首尾空白"""
        from src.utils.item_normalizer import normalize_item_no

        assert normalize_item_no("  DLX-100  ") == "DLX-100"
        assert normalize_item_no("\tABC-200\n") == "ABC-200"

    def test_preserve_valid_format(self):
        """測試保留正確格式"""
        from src.utils.item_normalizer import normalize_item_no

        assert normalize_item_no("DLX-100") == "DLX-100"
        assert normalize_item_no("ABC-200.1") == "ABC-200.1"
        assert normalize_item_no("TEST-300A") == "TEST-300A"

    def test_handle_empty_input(self):
        """測試處理空輸入"""
        from src.utils.item_normalizer import normalize_item_no

        assert normalize_item_no("") == ""
        assert normalize_item_no("   ") == ""

    def test_handle_none_input(self):
        """測試處理 None 輸入"""
        from src.utils.item_normalizer import normalize_item_no

        assert normalize_item_no(None) == ""

    def test_uppercase_conversion(self):
        """測試轉為大寫"""
        from src.utils.item_normalizer import normalize_item_no

        assert normalize_item_no("dlx-100") == "DLX-100"
        assert normalize_item_no("Abc-200") == "ABC-200"

    def test_multiple_spaces(self):
        """測試處理多個連續空格"""
        from src.utils.item_normalizer import normalize_item_no

        assert normalize_item_no("DLX  -  100") == "DLX-100"
        assert normalize_item_no("ABC   200") == "ABC 200"  # 非 dash 相關的空格保留

    def test_500_series_fabric(self):
        """測試 500 系列面料編號"""
        from src.utils.item_normalizer import normalize_item_no

        assert normalize_item_no("500-001") == "500-001"
        assert normalize_item_no("500 -001") == "500-001"
        assert normalize_item_no("500- 001") == "500-001"

    def test_is_fabric_item(self):
        """測試識別面料項目"""
        from src.utils.item_normalizer import is_fabric_item

        assert is_fabric_item("500-001") is True
        assert is_fabric_item("500-100") is True
        assert is_fabric_item("501-001") is True
        assert is_fabric_item("DLX-100") is False
        assert is_fabric_item("ABC-500") is False

    def test_extract_base_item_no(self):
        """測試提取基礎編號 (去除子編號)"""
        from src.utils.item_normalizer import extract_base_item_no

        assert extract_base_item_no("DLX-100.1") == "DLX-100"
        assert extract_base_item_no("DLX-100.2") == "DLX-100"
        assert extract_base_item_no("DLX-100") == "DLX-100"
        assert extract_base_item_no("ABC-200A") == "ABC-200"
