"""fabric_formatter 單元測試"""

import pytest

from src.utils.fabric_formatter import (
    extract_location_from_description,
    format_fabric_description,
    format_fabric_dimension,
    is_pattern_fabric,
)


class TestFormatFabricDimension:
    """測試 format_fabric_dimension()"""

    def test_full_format_pattern(self):
        """完整格式 - pattern (Morbern Europe 範例)"""
        result = format_fabric_dimension(
            content="Vinyl-First Edition",
            vendor="Morbern Europe",
            brand="Prodigy PRO 682",
            pattern="Lt Neutral",
            width="137cmW",
            has_repeat=True,
        )
        assert result == "Vinyl-First Edition-Morbern Europe-Prodigy PRO 682-Lt Neutral-137cmW pattern"

    def test_full_format_plain(self):
        """完整格式 - plain"""
        result = format_fabric_dimension(
            content="Cotton",
            vendor="TextileCo",
            brand="JAB",
            pattern="Solid",
            width=150,
            has_repeat=False,
        )
        assert result == "Cotton-TextileCo-JAB-Solid-150cmW plain"

    def test_partial_fields(self):
        """部分欄位缺失"""
        result = format_fabric_dimension(
            content=None,
            vendor="Vendor",
            brand="Brand",
            pattern=None,
            width=None,
            has_repeat=True,
        )
        assert result == "Vendor-Brand pattern"

    def test_width_with_unit(self):
        """寬度已包含單位"""
        result = format_fabric_dimension(
            content="Polyester",
            vendor=None,
            brand="Brand",
            pattern="Pattern",
            width="140cm",
            has_repeat=True,
        )
        assert "140cm" in result
        assert "cmW" not in result  # 不應重複加上單位

    def test_width_without_unit(self):
        """寬度無單位時自動加上 cmW"""
        result = format_fabric_dimension(
            content="Polyester",
            vendor=None,
            brand="Brand",
            pattern="Pattern",
            width=140,
            has_repeat=True,
        )
        assert "140cmW" in result

    def test_empty_input(self):
        """全部為空時"""
        result = format_fabric_dimension(
            content=None,
            vendor=None,
            brand=None,
            pattern=None,
            width=None,
            has_repeat=True,
        )
        assert result == "pattern"

    def test_empty_input_plain(self):
        """全部為空時 - plain"""
        result = format_fabric_dimension(
            content=None,
            vendor=None,
            brand=None,
            pattern=None,
            width=None,
            has_repeat=False,
        )
        assert result == "plain"


class TestFormatFabricDescription:
    """測試 format_fabric_description()"""

    def test_with_target(self):
        """有關聯家具 - 使用 Brand (Morbern Europe) 作為 material_type"""
        result = format_fabric_description("Morbern Europe", "DLX-100")
        assert result == "Morbern Europe to DLX-100"

    def test_without_target(self):
        """無關聯家具 (孤立面料)"""
        result = format_fabric_description("Morbern Europe", None)
        assert result == "Morbern Europe"

    def test_default_material_type(self):
        """未提供材料類型時預設為 Fabric"""
        result = format_fabric_description(None, "DLX-200")
        assert result == "Fabric to DLX-200"

    def test_empty_target(self):
        """目標為空字串"""
        result = format_fabric_description("Leather", "")
        assert result == "Leather"


class TestExtractLocationFromDescription:
    """測試 extract_location_from_description()"""

    def test_with_at_symbol(self):
        """含 @ 符號"""
        result = extract_location_from_description("Bedside Table @ Deluxe Room")
        assert result == "Deluxe Room"

    def test_without_at_symbol(self):
        """不含 @ 符號"""
        result = extract_location_from_description("Simple Table")
        assert result is None

    def test_empty_after_at(self):
        """@ 後無文字"""
        result = extract_location_from_description("Table @")
        assert result is None

    def test_empty_after_at_with_space(self):
        """@ 後只有空格"""
        result = extract_location_from_description("Table @   ")
        assert result is None

    def test_multiple_at_symbols(self):
        """多個 @ 符號"""
        result = extract_location_from_description("Item @ Room @ Floor 5")
        assert result == "Room @ Floor 5"

    def test_none_input(self):
        """輸入為 None"""
        result = extract_location_from_description(None)
        assert result is None

    def test_empty_string(self):
        """輸入為空字串"""
        result = extract_location_from_description("")
        assert result is None

    def test_whitespace_handling(self):
        """前後空格處理"""
        result = extract_location_from_description("  Table  @  Deluxe Room  ")
        assert result == "Deluxe Room"


class TestIsPatternFabric:
    """測試 is_pattern_fabric()"""

    def test_has_repeat_true(self):
        """有 repeat = pattern"""
        assert is_pattern_fabric(True) is True

    def test_has_repeat_false(self):
        """無 repeat = plain"""
        assert is_pattern_fabric(False) is False

    def test_none_defaults_to_pattern(self):
        """None 預設為 pattern"""
        assert is_pattern_fabric(None) is True
