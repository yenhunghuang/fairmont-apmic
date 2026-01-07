"""
Adapter 架構單元測試

測試項目：
- AdapterRegistry: 載入、註冊、取得適配器
- FairmontAdapter: 角色識別、Item No. 正規化、面料判斷
- GenericAdapter: LLM 動態判斷 (mock)
"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.services.adapters.base import (
    FileRole,
    ParsedTable,
    RawItem,
    SupplierAdapter,
)
from src.services.adapters.fairmont import FairmontAdapter
from src.services.adapters.generic import GenericAdapter
from src.services.adapters.registry import AdapterRegistry

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def fairmont_adapter() -> FairmontAdapter:
    """建立 FairmontAdapter 實例"""
    return FairmontAdapter()


@pytest.fixture
def generic_adapter() -> GenericAdapter:
    """建立 GenericAdapter 實例 (使用 mock LLM)"""
    mock_llm = AsyncMock()
    return GenericAdapter(llm_client=mock_llm)


@pytest.fixture
def registry(tmp_path: Path) -> AdapterRegistry:
    """建立 AdapterRegistry 實例"""
    return AdapterRegistry(config_dir=tmp_path)


@pytest.fixture
def quantity_sheet_content() -> str:
    """數量總表範例內容"""
    return """
    FURNITURE QUANTITY SCHEDULE
    Project: Fairmont Hotel

    CODE        DESCRIPTION             TOTAL QTY
    DLX-100     Bedside Table           50
    DLX-101     Writing Desk            25
    DLX-102     Wardrobe                50
    """


@pytest.fixture
def spec_sheet_content() -> str:
    """規格書範例內容"""
    return """
    FURNITURE SPECIFICATION
    Item No: DLX-100
    Description: Bedside Table

    DIMENSION: 600W x 450D x 550H mm
    MATERIALS: Solid Oak, Lacquered Finish
    Brand: Custom Furniture Co.
    """


@pytest.fixture
def fabric_sheet_content() -> str:
    """面料表範例內容"""
    return """
    FABRIC SPECIFICATION
    Item No: 501
    Brand: Morbern
    Pattern: Prodigy PRO 682
    Color: Lt Neutral
    Width: 137cm
    Content: 100% Vinyl
    Abrasion: 100,000 DR
    """


@pytest.fixture
def index_content() -> str:
    """Index 範例內容"""
    return """
    FURNITURE INDEX

    ROOM TYPE       LOCATION        ITEM CODE
    Deluxe Room     Bedroom         DLX-100
    Deluxe Room     Bedroom         DLX-101
    Suite           Living Area     SUT-200
    """


# ============================================================================
# FairmontAdapter Tests
# ============================================================================


class TestFairmontAdapter:
    """FairmontAdapter 測試"""

    def test_supplier_id(self, fairmont_adapter: FairmontAdapter):
        """測試供應商 ID"""
        assert fairmont_adapter.supplier_id == "fairmont"

    def test_display_name(self, fairmont_adapter: FairmontAdapter):
        """測試顯示名稱"""
        assert "Fairmont" in fairmont_adapter.display_name

    def test_implements_protocol(self, fairmont_adapter: FairmontAdapter):
        """測試實作 SupplierAdapter Protocol"""
        assert isinstance(fairmont_adapter, SupplierAdapter)

    # -------------------------------------------------------------------------
    # Role Detection Tests
    # -------------------------------------------------------------------------

    def test_detect_quantity_sheet(
        self, fairmont_adapter: FairmontAdapter, quantity_sheet_content: str
    ):
        """測試識別數量總表"""
        tables = [
            ParsedTable(
                headers=["CODE", "DESCRIPTION", "TOTAL QTY"],
                rows=[["DLX-100", "Bedside Table", "50"]],
            )
        ]
        role = fairmont_adapter.detect_file_role(quantity_sheet_content, tables)
        assert role == FileRole.QUANTITY_SHEET

    def test_detect_spec_sheet(self, fairmont_adapter: FairmontAdapter, spec_sheet_content: str):
        """測試識別規格書"""
        tables = [
            ParsedTable(
                headers=["SPECIFICATION", "VALUE"],
                rows=[["DIMENSION", "600W x 450D x 550H mm"]],
            )
        ]
        role = fairmont_adapter.detect_file_role(spec_sheet_content, tables)
        assert role == FileRole.SPEC_SHEET

    def test_detect_fabric_sheet(
        self, fairmont_adapter: FairmontAdapter, fabric_sheet_content: str
    ):
        """測試識別面料表"""
        tables = [
            ParsedTable(
                headers=["Brand", "Pattern", "Color"],
                rows=[["Morbern", "Prodigy", "Lt Neutral"]],
            )
        ]
        role = fairmont_adapter.detect_file_role(fabric_sheet_content, tables)
        assert role == FileRole.FABRIC_SHEET

    def test_detect_index(self, fairmont_adapter: FairmontAdapter, index_content: str):
        """測試識別 Index"""
        tables = [
            ParsedTable(
                headers=["ROOM TYPE", "LOCATION", "ITEM CODE"],
                rows=[["Deluxe Room", "Bedroom", "DLX-100"]],
            )
        ]
        role = fairmont_adapter.detect_file_role(index_content, tables)
        assert role == FileRole.INDEX

    def test_detect_unknown(self, fairmont_adapter: FairmontAdapter):
        """測試無法識別的內容"""
        role = fairmont_adapter.detect_file_role("Random content", [])
        assert role == FileRole.UNKNOWN

    # -------------------------------------------------------------------------
    # Item No. Normalization Tests
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("DLX-100", "DLX-100"),
            ("DLX-201 .1", "DLX-201.1"),
            ("DLX 100", "DLX-100"),
            ("dlx-100", "DLX-100"),
            ("DLX - 100", "DLX-100"),
            ("  DLX-100  ", "DLX-100"),
            ("DLX-201.1", "DLX-201.1"),
        ],
    )
    def test_normalize_item_no(self, fairmont_adapter: FairmontAdapter, raw: str, expected: str):
        """測試 Item No. 正規化"""
        assert fairmont_adapter.normalize_item_no(raw) == expected

    # -------------------------------------------------------------------------
    # Fabric Detection Tests
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize(
        "item_no,is_fabric",
        [
            ("DLX-100", False),
            ("501", True),
            ("500", True),
            ("599", True),
            ("499", False),
            ("600", False),
            ("5001", False),
        ],
    )
    def test_is_fabric_item(self, fairmont_adapter: FairmontAdapter, item_no: str, is_fabric: bool):
        """測試面料項目判斷"""
        assert fairmont_adapter.is_fabric_item(item_no) == is_fabric

    # -------------------------------------------------------------------------
    # Prompt Generation Tests
    # -------------------------------------------------------------------------

    def test_get_extraction_prompt_item_detection(self, fairmont_adapter: FairmontAdapter):
        """測試 item_detection Prompt"""
        prompt = fairmont_adapter.get_extraction_prompt("item_detection")
        assert "item_no" in prompt.lower() or "項目" in prompt

    def test_get_extraction_prompt_item_extraction(self, fairmont_adapter: FairmontAdapter):
        """測試 item_extraction Prompt"""
        prompt = fairmont_adapter.get_extraction_prompt(
            "item_extraction", context="Sample PDF content"
        )
        assert len(prompt) > 0

    # -------------------------------------------------------------------------
    # Output Mapping Tests
    # -------------------------------------------------------------------------

    def test_map_to_output(self, fairmont_adapter: FairmontAdapter):
        """測試欄位映射"""
        raw_item = RawItem(
            item_no="DLX-100",
            description="Bedside Table",
            dimensions="600 x 450 x 550",
            qty=50,
            uom="ea",
            materials="Solid Oak",
            location="Deluxe Room",
            brand="Custom Furniture Co.",
        )
        quote_item = fairmont_adapter.map_to_output(raw_item, sequence=1)

        assert quote_item.no == 1
        assert quote_item.item_no == "DLX-100"
        assert quote_item.description == "Bedside Table"
        assert quote_item.dimension == "600 x 450 x 550"
        assert quote_item.qty == 50
        assert quote_item.uom == "ea"
        assert quote_item.materials_used == "Solid Oak"
        assert quote_item.location == "Deluxe Room"
        assert quote_item.brand == "Custom Furniture Co."

    def test_get_merge_key(self, fairmont_adapter: FairmontAdapter):
        """測試合併鍵值"""
        raw_item = RawItem(item_no="DLX-201 .1")
        merge_key = fairmont_adapter.get_merge_key(raw_item)
        assert merge_key == "DLX-201.1"


# ============================================================================
# GenericAdapter Tests
# ============================================================================


class TestGenericAdapter:
    """GenericAdapter 測試"""

    def test_supplier_id(self, generic_adapter: GenericAdapter):
        """測試供應商 ID"""
        assert generic_adapter.supplier_id == "_generic"

    def test_display_name(self, generic_adapter: GenericAdapter):
        """測試顯示名稱"""
        assert "Generic" in generic_adapter.display_name or "通用" in generic_adapter.display_name

    def test_implements_protocol(self, generic_adapter: GenericAdapter):
        """測試實作 SupplierAdapter Protocol"""
        assert isinstance(generic_adapter, SupplierAdapter)

    @pytest.mark.asyncio
    async def test_detect_file_role_with_llm(self, generic_adapter: GenericAdapter):
        """測試使用 LLM 判斷檔案角色"""
        generic_adapter._llm_client.chat = AsyncMock(return_value="QUANTITY_SHEET")

        role = await generic_adapter.detect_file_role_async(
            "Sample content with CODE and TOTAL QTY", []
        )
        assert role == FileRole.QUANTITY_SHEET

    def test_normalize_item_no_passthrough(self, generic_adapter: GenericAdapter):
        """測試通用適配器的 Item No. 正規化 (基本清理)"""
        result = generic_adapter.normalize_item_no("  ABC-123  ")
        assert result == "ABC-123"

    def test_is_fabric_item_default_false(self, generic_adapter: GenericAdapter):
        """測試通用適配器預設不判斷面料"""
        # GenericAdapter 無法自動判斷面料，預設返回 False
        assert generic_adapter.is_fabric_item("501") is False


# ============================================================================
# AdapterRegistry Tests
# ============================================================================


class TestAdapterRegistry:
    """AdapterRegistry 測試"""

    def test_register_adapter(self, registry: AdapterRegistry):
        """測試註冊適配器"""
        adapter = FairmontAdapter()
        registry.register(adapter)
        assert "fairmont" in registry.list_adapters()

    def test_get_adapter(self, registry: AdapterRegistry):
        """測試取得適配器"""
        adapter = FairmontAdapter()
        registry.register(adapter)
        retrieved = registry.get("fairmont")
        assert retrieved is adapter

    def test_get_nonexistent_adapter(self, registry: AdapterRegistry):
        """測試取得不存在的適配器"""
        with pytest.raises(KeyError):
            registry.get("nonexistent")

    def test_get_default_adapter(self, registry: AdapterRegistry):
        """測試取得預設適配器"""
        fairmont = FairmontAdapter()
        generic = GenericAdapter(llm_client=AsyncMock())
        registry.register(fairmont)
        registry.register(generic)
        registry.set_default("fairmont")

        default = registry.get_default()
        assert default.supplier_id == "fairmont"

    def test_list_adapters(self, registry: AdapterRegistry):
        """測試列出所有適配器"""
        registry.register(FairmontAdapter())
        registry.register(GenericAdapter(llm_client=AsyncMock()))

        adapters = registry.list_adapters()
        assert "fairmont" in adapters
        assert "_generic" in adapters

    def test_auto_discover_builtin(self, registry: AdapterRegistry):
        """測試自動發現內建適配器"""
        registry.auto_discover()
        adapters = registry.list_adapters()
        assert "fairmont" in adapters


# ============================================================================
# Integration Tests
# ============================================================================


class TestAdapterIntegration:
    """適配器整合測試"""

    def test_full_workflow(self, fairmont_adapter: FairmontAdapter):
        """測試完整工作流程"""
        # 1. 識別 PDF 角色
        tables = [
            ParsedTable(
                headers=["CODE", "DESCRIPTION", "TOTAL QTY"],
                rows=[["DLX-100", "Bedside Table", "50"]],
            )
        ]
        role = fairmont_adapter.detect_file_role("FURNITURE QUANTITY SCHEDULE", tables)
        assert role == FileRole.QUANTITY_SHEET

        # 2. 正規化 Item No.
        normalized = fairmont_adapter.normalize_item_no("DLX-201 .1")
        assert normalized == "DLX-201.1"

        # 3. 判斷是否為面料
        assert not fairmont_adapter.is_fabric_item(normalized)
        assert fairmont_adapter.is_fabric_item("501")

        # 4. 映射輸出
        raw_item = RawItem(
            item_no="DLX-100",
            description="Bedside Table",
            qty=50,
        )
        quote_item = fairmont_adapter.map_to_output(raw_item, sequence=1)
        assert quote_item.item_no == "DLX-100"
        assert quote_item.qty == 50
