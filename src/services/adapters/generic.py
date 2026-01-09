"""
GenericAdapter - 通用適配器 (LLM 動態判斷)

使用 LLM 動態判斷未知供應商格式：
- PDF 角色識別由 LLM 判斷
- Item No. 格式自動推測
- 適用於無預設配置的供應商
"""

import re
from typing import Any

from .base import (
    BaseAdapter,
    FileRole,
    ParsedTable,
    QuoteItem,
    RawItem,
)


class GenericAdapter(BaseAdapter):
    """
    通用適配器 - LLM 動態判斷

    適用於未知供應商格式，使用 LLM 進行：
    - PDF 角色識別
    - 結構分析
    - 欄位提取

    注意：此適配器的 Token 消耗較高。
    """

    def __init__(self, llm_client=None, config: dict[str, Any] | None = None):
        """
        初始化通用適配器

        Args:
            llm_client: LLM 客戶端 (支援 async chat 方法)
            config: 配置字典
        """
        super().__init__(config)
        self._llm_client = llm_client

    @property
    def supplier_id(self) -> str:
        return "_generic"

    @property
    def display_name(self) -> str:
        return self._config.get("display_name", "通用適配器 (Generic)")

    def detect_file_role(self, content: str, tables: list[ParsedTable]) -> FileRole:
        """
        同步版本的角色偵測 (使用啟發式規則)

        對於簡單情況使用規則判斷，複雜情況返回 UNKNOWN
        建議使用 detect_file_role_async 以獲得更準確的結果
        """
        content_upper = content.upper()

        # 取得所有表格標題
        all_headers: set[str] = set()
        for table in tables:
            all_headers.update(h.upper().strip() for h in table.headers)

        # 簡單啟發式判斷
        qty_keywords = {"QTY", "QUANTITY", "TOTAL", "CODE", "數量"}
        spec_keywords = {"DIMENSION", "MATERIAL", "SPECIFICATION", "SIZE", "規格", "尺寸"}
        fabric_keywords = {"BRAND", "PATTERN", "COLOR", "FABRIC", "VINYL", "面料"}
        index_keywords = {"ROOM", "LOCATION", "INDEX", "房型", "位置"}

        # 計算每種類型的匹配分數
        scores = {
            FileRole.QUANTITY_SHEET: sum(
                1 for kw in qty_keywords if kw in content_upper or kw in all_headers
            ),
            FileRole.SPEC_SHEET: sum(1 for kw in spec_keywords if kw in content_upper),
            FileRole.FABRIC_SHEET: sum(
                1 for kw in fabric_keywords if kw in content_upper or kw in all_headers
            ),
            FileRole.INDEX: sum(
                1 for kw in index_keywords if kw in content_upper or kw in all_headers
            ),
        }

        # 選擇最高分數的類型
        max_score = max(scores.values())
        if max_score >= 2:
            for role, score in scores.items():
                if score == max_score:
                    return role

        return FileRole.UNKNOWN

    async def detect_file_role_async(self, content: str, tables: list[ParsedTable]) -> FileRole:
        """
        使用 LLM 判斷 PDF 角色

        Args:
            content: PDF 文字內容
            tables: 解析出的表格列表

        Returns:
            FileRole: 檔案角色類型
        """
        if not self._llm_client:
            return self.detect_file_role(content, tables)

        # 準備表格資訊
        table_info = ""
        if tables:
            headers = [", ".join(t.headers) for t in tables[:3]]
            table_info = f"\n表格欄位: {'; '.join(headers)}"

        prompt = f"""
分析以下 PDF 內容，判斷它的角色類型。

可能的類型:
- QUANTITY_SHEET: 數量總表（包含項目編號和數量列表）
- SPEC_SHEET: 規格書（包含詳細尺寸、材質說明）
- FABRIC_SHEET: 面料表（包含面料品牌、花紋、成分）
- INDEX: 索引表（包含房型、位置資訊）
- UNKNOWN: 無法判斷

PDF 內容（前 1500 字元）:
{content[:1500]}
{table_info}

只輸出角色類型（如 QUANTITY_SHEET），不要解釋。
"""

        try:
            response = await self._llm_client.chat(prompt)
            role_str = response.strip().upper()

            # 映射 LLM 回應到 FileRole
            role_map = {
                "QUANTITY_SHEET": FileRole.QUANTITY_SHEET,
                "SPEC_SHEET": FileRole.SPEC_SHEET,
                "FABRIC_SHEET": FileRole.FABRIC_SHEET,
                "INDEX": FileRole.INDEX,
            }
            return role_map.get(role_str, FileRole.UNKNOWN)

        except Exception:
            # LLM 呼叫失敗時使用啟發式判斷
            return self.detect_file_role(content, tables)

    def normalize_item_no(self, raw_item_no: str) -> str:
        """
        基本的 Item No. 正規化

        通用規則:
        - 移除前後空白
        - 移除多餘空格
        """
        cleaned = raw_item_no.strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = cleaned.strip()
        return cleaned

    def is_fabric_item(self, item_no: str) -> bool:
        """
        通用適配器無法自動判斷面料項目

        Returns:
            bool: 預設返回 False
        """
        # 通用適配器無法自動判斷，需要 LLM 輔助或人工標記
        return False

    async def is_fabric_item_async(self, item_no: str, context: str = "") -> bool:
        """
        使用 LLM 判斷是否為面料項目

        Args:
            item_no: 項目編號
            context: 額外上下文

        Returns:
            bool: 是否為面料項目
        """
        if not self._llm_client:
            return False

        prompt = f"""
判斷以下項目編號是否為面料/布料/皮革項目。

項目編號: {item_no}
{f"上下文: {context}" if context else ""}

只回答 YES 或 NO。
"""

        try:
            response = await self._llm_client.chat(prompt)
            return response.strip().upper() == "YES"
        except Exception:
            return False

    def get_extraction_prompt(self, stage: str, context: str = "") -> str:
        """
        取得通用 LLM 提取 Prompt

        與 FairmontAdapter 不同，通用 Prompt 更加開放
        """
        prompts = {
            "item_detection": """
從以下 PDF 內容中識別所有項目。

請找出:
1. 項目編號 (item_no) - 任何看起來像產品編號的文字
2. 所在頁碼 (如果可識別)

輸出格式 (JSON 陣列):
[
  {{"item_no": "...", "source_page": 1}},
  ...
]

PDF 內容:
{context}

請只輸出 JSON，不要任何解釋。
""",
            "item_extraction": """
從以下內容中提取產品詳細資訊。

盡可能提取以下欄位:
- item_no: 項目/產品編號
- description: 品名描述
- dimensions: 尺寸 (如有)
- materials: 材料/材質
- brand: 品牌/供應商
- qty: 數量 (如有)
- uom: 單位

輸出格式 (JSON):
{{
  "item_no": "...",
  "description": "...",
  "dimensions": "...",
  "materials": "...",
  "brand": "...",
  "qty": null,
  "uom": "ea"
}}

內容:
{context}

請只輸出 JSON，不要任何解釋。
""",
            "structure_analysis": """
分析以下 PDF 內容的結構。

請識別:
1. 文件類型 (報價單、規格書、數量表等)
2. 主要欄位和其位置
3. 重複模式 (如多個產品)

內容:
{context}

請簡潔描述發現的結構。
""",
        }

        prompt_template = prompts.get(stage, prompts["item_extraction"])
        return prompt_template.format(context=context)

    def map_to_output(self, raw_item: RawItem, sequence: int) -> QuoteItem:
        """
        通用欄位映射

        直接映射，不做供應商特定處理
        """
        return QuoteItem(
            # 1-7: 核心欄位
            no=sequence,
            item_no=self.normalize_item_no(raw_item.item_no),
            description=raw_item.description,
            photo_base64=None,
            dimension=raw_item.dimensions,
            qty=raw_item.qty,
            uom=raw_item.uom,
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
