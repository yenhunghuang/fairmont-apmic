"""
FairmontAdapter - 惠而蒙 (Fairmont) 專用適配器

針對 Fairmont 供應商的 PDF 格式實作：
- PDF 角色識別 (數量總表、規格書、面料表、Index)
- Item No. 正規化 (DLX-XXX 格式)
- 面料判斷 (500 系列)
- LLM Prompt 模板
"""

import re
from pathlib import Path
from typing import Any

import yaml

from .base import (
    BaseAdapter,
    FileRole,
    ParsedTable,
    QuoteItem,
    RawItem,
)


class FairmontAdapter(BaseAdapter):
    """
    惠而蒙 (Fairmont) 供應商適配器

    專為 Fairmont 家具規格書格式設計，支援：
    - DLX-XXX 編號格式
    - 500 系列面料識別
    - CODE/TOTAL QTY 欄位識別數量總表
    """

    def __init__(self, config_path: Path | None = None):
        """
        初始化 Fairmont 適配器

        Args:
            config_path: YAML 配置檔路徑 (可選)
        """
        config = self._load_config(config_path) if config_path else {}
        super().__init__(config)

        # 預設配置 (可被 YAML 覆寫)
        self._role_detection = self._config.get(
            "role_detection",
            {
                "quantity_sheet": {
                    "must_contain": ["CODE", "TOTAL QTY"],
                },
                "spec_sheet": {
                    "must_contain_any": ["DIMENSION", "MATERIALS", "SPECIFICATION"],
                },
                "fabric_sheet": {
                    "must_contain_any": ["Brand", "Pattern", "Color", "Abrasion"],
                },
                "index": {
                    "must_contain": ["ROOM", "LOCATION"],
                },
            },
        )

        self._item_normalization = self._config.get(
            "item_normalization",
            {
                "pattern": r"^([A-Z]{2,4})\s*-?\s*(\d+)(?:\s*\.?\s*(\d+))?$",
            },
        )

        self._fabric_detection = self._config.get(
            "fabric_detection",
            {
                "series_range": [500, 599],
            },
        )

    def _load_config(self, config_path: Path) -> dict[str, Any]:
        """載入 YAML 配置"""
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    @property
    def supplier_id(self) -> str:
        return "fairmont"

    @property
    def display_name(self) -> str:
        return self._config.get("display_name", "惠而蒙 Fairmont")

    def detect_file_role(self, content: str, tables: list[ParsedTable]) -> FileRole:
        """
        根據 PDF 內容判斷檔案角色

        判斷邏輯 (優先順序)：
        1. 數量總表: 表格包含 CODE 和 TOTAL QTY 欄位
        2. 面料表: 包含 "500 Fabric" 或面料相關關鍵字
        3. 規格書: 包含 SPECIFICATION, ITEM NO., DIMENSION 等
        4. Index: 文件開頭有 "Index" 或包含 Room/Location 表格
        """
        content_upper = content.upper()

        # 取得所有表格標題
        all_headers: set[str] = set()
        for table in tables:
            all_headers.update(h.upper().strip() for h in table.headers)

        # 1. 檢查數量總表 (最優先 - 有明確的表格結構)
        qty_markers = self._role_detection["quantity_sheet"]["must_contain"]
        if all(
            marker.upper() in all_headers or marker.upper() in content_upper
            for marker in qty_markers
        ):
            return FileRole.QUANTITY_SHEET

        # 2. 檢查面料表 (優先於規格書 - 有 "500 Fabric" 特徵)
        # 檢查 "500 Fabric" 或 "Fabric & Leather" 關鍵字
        fabric_title_markers = ["500 FABRIC", "FABRIC & LEATHER", "FABRIC, VINYL"]
        if any(marker in content_upper for marker in fabric_title_markers):
            return FileRole.FABRIC_SHEET

        fabric_markers = self._role_detection["fabric_sheet"]["must_contain_any"]
        fabric_matches = sum(
            1
            for marker in fabric_markers
            if marker.upper() in all_headers or marker.upper() in content_upper
        )
        if fabric_matches >= 3:  # 至少匹配 3 個面料標記
            return FileRole.FABRIC_SHEET

        # 3. 檢查規格書 (有 SPECIFICATION 或 ITEM NO. 格式)
        spec_title_markers = ["FINAL SPECIFICATION", "SPECIFICATION", "100 SEATING"]
        if any(marker in content_upper for marker in spec_title_markers):
            # 確認有 ITEM NO. 格式
            if "ITEM NO" in content_upper or "ITEM:" in content_upper:
                return FileRole.SPEC_SHEET

        spec_markers = self._role_detection["spec_sheet"]["must_contain_any"]
        spec_matches = sum(1 for marker in spec_markers if marker.upper() in content_upper)
        if spec_matches >= 2:  # 至少匹配 2 個規格標記
            return FileRole.SPEC_SHEET

        # 4. 檢查 Index (文件開頭有 "Index" 或表格有 Item #/Room)
        # 檢查文件開頭是否為 Index
        first_100_chars = content[:100].upper()
        if "INDEX" in first_100_chars:
            return FileRole.INDEX

        # 檢查 Index 表格特徵
        index_table_markers = ["ITEM #", "ITEM#", "ROOM", "VENDOR", "QUANTITY"]
        index_matches = sum(
            1 for marker in index_table_markers if marker in all_headers or marker in content_upper
        )
        if index_matches >= 3:
            return FileRole.INDEX

        # 傳統 Index 檢查
        index_markers = self._role_detection["index"]["must_contain"]
        if all(
            marker.upper() in all_headers or marker.upper() in content_upper
            for marker in index_markers
        ):
            return FileRole.INDEX

        return FileRole.UNKNOWN

    def normalize_item_no(self, raw_item_no: str) -> str:
        """
        正規化 Item No. 格式

        規則：
        - 移除多餘空格
        - 統一破折號位置
        - 轉為大寫
        - 處理 "DLX-201 .1" → "DLX-201.1"

        Examples:
            "DLX-201 .1" → "DLX-201.1"
            "DLX 100" → "DLX-100"
            "dlx-100" → "DLX-100"
        """
        # 清理空白
        cleaned = raw_item_no.strip().upper()

        # 移除多餘空格
        cleaned = re.sub(r"\s+", " ", cleaned)

        # 嘗試匹配 Fairmont 格式
        pattern = self._item_normalization["pattern"]
        match = re.match(pattern, cleaned, re.IGNORECASE)

        if match:
            prefix = match.group(1).upper()
            number = match.group(2)
            suffix = match.group(3)

            if suffix:
                return f"{prefix}-{number}.{suffix}"
            return f"{prefix}-{number}"

        # 無法匹配時，做基本清理
        # 移除空格和多餘的破折號/點號
        cleaned = re.sub(r"\s*-\s*", "-", cleaned)
        cleaned = re.sub(r"\s*\.\s*", ".", cleaned)
        cleaned = re.sub(r"\s+", "", cleaned)

        return cleaned

    def is_fabric_item(self, item_no: str) -> bool:
        """
        判斷是否為面料項目

        Fairmont 規則: 500-599 系列為面料
        """
        # 正規化後取得數字部分
        normalized = self.normalize_item_no(item_no)

        # 嘗試提取數字
        match = re.search(r"(\d+)", normalized)
        if not match:
            return False

        number = int(match.group(1))
        series_range = self._fabric_detection["series_range"]

        return series_range[0] <= number <= series_range[1]

    def get_extraction_prompt(self, stage: str, context: str = "") -> str:
        """
        取得 LLM 提取 Prompt

        Args:
            stage: 處理階段
                - "item_detection": 項目偵測
                - "item_extraction": 項目詳細提取
                - "qty_extraction": 數量提取
            context: PDF 內容片段
        """
        prompts = {
            "item_detection": """
從以下 PDF 內容中找出所有家具項目編號 (item_no) 和所在頁碼。

輸出格式 (JSON 陣列):
[
  {{"item_no": "DLX-100", "source_page": 1}},
  {{"item_no": "DLX-101", "source_page": 2}}
]

PDF 內容:
{context}

請只輸出 JSON，不要任何解釋。
""",
            "item_extraction": """
從以下家具規格書內容中提取詳細資訊。

需要提取的欄位:
- item_no: 項目編號 (如 DLX-100)
- description: 品名描述 (如 Bedside Table)
- dimensions: 尺寸 (寬 x 深 x 高, mm)
- materials: 材料規格
- brand: 品牌/供應商
- uom: 單位 (ea, m, etc.)

輸出格式 (JSON):
{{
  "item_no": "...",
  "description": "...",
  "dimensions": "...",
  "materials": "...",
  "brand": "...",
  "uom": "ea"
}}

PDF 內容:
{context}

請只輸出 JSON，不要任何解釋。
""",
            "qty_extraction": """
從以下數量總表中提取項目編號和對應數量。

輸出格式 (JSON 陣列):
[
  {{"item_no": "DLX-100", "qty": 50}},
  {{"item_no": "DLX-101", "qty": 25}}
]

數量總表內容:
{context}

請只輸出 JSON，不要任何解釋。
""",
        }

        prompt_template = prompts.get(stage, prompts["item_extraction"])
        return prompt_template.format(context=context)

    def map_to_output(self, raw_item: RawItem, sequence: int) -> QuoteItem:
        """
        將原始項目映射到 15 欄位輸出

        Fairmont 特定映射：
        - item_no 會被正規化
        - 面料項目的 dimension 使用特定格式
        """
        normalized_item_no = self.normalize_item_no(raw_item.item_no)

        # 面料項目的特殊處理
        dimension = raw_item.dimensions
        if self.is_fabric_item(normalized_item_no):
            # 面料使用 Fairmont 預定格式
            dimension = dimension or "依面料規格"

        return QuoteItem(
            # 1-7: 核心欄位
            no=sequence,
            item_no=normalized_item_no,
            description=raw_item.description,
            photo_base64=None,  # 由後續處理填入
            dimension=dimension,
            qty=raw_item.qty,
            uom=raw_item.uom or "ea",
            # 8-12: 預留欄位
            unit_rate=None,
            amount=None,
            unit_cbm=None,
            total_cbm=None,
            note=None,
            # 13-15: 元資料欄位
            location=raw_item.location,
            materials_used=raw_item.materials,
            brand=raw_item.brand,
        )
