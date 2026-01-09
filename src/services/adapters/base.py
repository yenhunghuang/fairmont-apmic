"""
SupplierAdapter Protocol - 供應商適配器介面

定義所有供應商適配器必須實作的方法，用於：
- PDF 角色識別
- LLM Prompt 取得
- Item No. 正規化
- 面料判斷
- 欄位映射
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class FileRole(str, Enum):
    """PDF 檔案角色類型"""

    QUANTITY_SHEET = "QUANTITY_SHEET"  # 數量總表
    SPEC_SHEET = "SPEC_SHEET"  # 明細規格表
    FABRIC_SHEET = "FABRIC_SHEET"  # 面料表
    INDEX = "INDEX"  # Index 檔案 (房型/位置)
    UNKNOWN = "UNKNOWN"  # 無法識別


class ItemStatus(str, Enum):
    """項目處理狀態"""

    SUCCESS = "SUCCESS"
    FAILED_EXTRACTION = "FAILED_EXTRACTION"
    PENDING_REVIEW = "PENDING_REVIEW"


@dataclass
class ParsedTable:
    """解析後的表格資料"""

    headers: list[str]
    rows: list[list[str]]
    page_number: int = 0


@dataclass
class ParsedPDF:
    """解析後的 PDF 內容"""

    text: str
    tables: list[ParsedTable] = field(default_factory=list)
    page_count: int = 0
    images: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class QuoteItem:
    """17 欄位報價單項目 (符合 EXCEL_OUTPUT_SPECIFICATION.md)"""

    # 1-7: 核心解析欄位
    no: int  # 序號
    item_no: str  # 項目編號
    description: str | None = None  # 品名描述
    photo_base64: str | None = None  # 產品圖片 (Base64)
    dimension: str | None = None  # 家具:尺寸; 面料:規格字串
    qty: int | None = None  # 數量 (面料留空)
    uom: str | None = None  # 單位 (ea/m)
    # 8-12: 預留欄位 (空白，供採購填寫)
    unit_rate: float | None = None  # 單價 (預留)
    amount: float | None = None  # 總價 (預留)
    unit_cbm: float | None = None  # 單位材積 (預留)
    total_cbm: float | None = None  # 總材積 (預留)
    note: str | None = None  # 備註 (預留)
    # 13-15: 元資料欄位
    location: str | None = None  # 房型/位置 (@ 之後文字)
    materials_used: str | None = None  # 材料規格
    brand: str | None = None  # 品牌 (家具:Null, 面料:必填)
    # 16-17: 分類與關聯欄位
    category: int = 1  # 產品分類 (1=家具, 5=面料)
    affiliate: str | None = None  # 所屬家具 (面料專用)


@dataclass
class RawItem:
    """從 PDF 提取的原始項目資料"""

    item_no: str
    description: str | None = None
    dimensions: str | None = None
    qty: int | None = None
    uom: str | None = None
    materials: str | None = None
    location: str | None = None
    brand: str | None = None
    photo_path: str | None = None
    source_page: int | None = None
    confidence: float = 1.0  # LLM 提取信心度


@runtime_checkable
class SupplierAdapter(Protocol):
    """
    供應商適配器介面 (Protocol)

    所有供應商適配器必須實作此介面的方法。
    使用 Protocol 而非 ABC 以支援結構性子類型。
    """

    @property
    def supplier_id(self) -> str:
        """供應商識別符 (如 'fairmont', '_generic')"""
        ...

    @property
    def display_name(self) -> str:
        """供應商顯示名稱 (如 '惠而蒙 Fairmont')"""
        ...

    def detect_file_role(self, content: str, tables: list[ParsedTable]) -> FileRole:
        """
        根據 PDF 內容判斷檔案角色

        Args:
            content: PDF 文字內容
            tables: 解析出的表格列表

        Returns:
            FileRole: 檔案角色類型
        """
        ...

    def get_extraction_prompt(self, stage: str, context: str = "") -> str:
        """
        取得 LLM 提取 Prompt

        Args:
            stage: 處理階段 (item_detection, item_extraction, etc.)
            context: 額外上下文 (如 PDF 內容片段)

        Returns:
            str: 完整的 LLM Prompt
        """
        ...

    def normalize_item_no(self, raw_item_no: str) -> str:
        """
        正規化 Item No. 格式

        Args:
            raw_item_no: 原始 Item No. (如 "DLX-201 .1")

        Returns:
            str: 正規化後的 Item No. (如 "DLX-201.1")
        """
        ...

    def is_fabric_item(self, item_no: str) -> bool:
        """
        判斷是否為面料項目

        Args:
            item_no: 項目編號

        Returns:
            bool: True 如果是面料項目 (如 500 系列)
        """
        ...

    def get_merge_key(self, item: RawItem) -> str:
        """
        取得用於合併數量總表與規格表的鍵值

        Args:
            item: 原始項目資料

        Returns:
            str: 合併鍵值 (通常是正規化後的 item_no)
        """
        ...

    def map_to_output(self, raw_item: RawItem, sequence: int) -> QuoteItem:
        """
        將原始項目映射到統一 17 欄位輸出

        Args:
            raw_item: 從 PDF 提取的原始項目
            sequence: 序號

        Returns:
            QuoteItem: 17 欄位報價單項目
        """
        ...


class BaseAdapter(ABC):
    """
    供應商適配器基礎類別

    提供共用的預設實作，子類別可覆寫特定方法。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化適配器

        Args:
            config: 供應商配置 (從 YAML 載入)
        """
        self._config = config or {}

    @property
    @abstractmethod
    def supplier_id(self) -> str:
        """供應商識別符"""
        ...

    @property
    def display_name(self) -> str:
        """供應商顯示名稱"""
        return self._config.get("display_name", self.supplier_id)

    def get_merge_key(self, item: RawItem) -> str:
        """預設使用正規化後的 item_no 作為合併鍵值"""
        return self.normalize_item_no(item.item_no)

    def map_to_output(self, raw_item: RawItem, sequence: int) -> QuoteItem:
        """預設欄位映射"""
        return QuoteItem(
            no=sequence,
            item_no=self.normalize_item_no(raw_item.item_no),
            description=raw_item.description,
            dimension=raw_item.dimensions,
            qty=raw_item.qty,
            uom=raw_item.uom,
            materials_used=raw_item.materials,
            location=raw_item.location,
            brand=raw_item.brand,
        )

    @abstractmethod
    def detect_file_role(self, content: str, tables: list[ParsedTable]) -> FileRole:
        """子類別必須實作"""
        ...

    @abstractmethod
    def get_extraction_prompt(self, stage: str, context: str = "") -> str:
        """子類別必須實作"""
        ...

    @abstractmethod
    def normalize_item_no(self, raw_item_no: str) -> str:
        """子類別必須實作"""
        ...

    @abstractmethod
    def is_fabric_item(self, item_no: str) -> bool:
        """子類別必須實作"""
        ...
