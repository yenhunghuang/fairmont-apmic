"""多階段處理管線 (7 stages)"""

import json
import time

from src.models.database import get_connection
from src.models.entities import (
    STAGE_NUMBER_MAP,
    TOTAL_STAGES,
    BatchStatus,
    FileRole,
    ProcessingStage,
    StageName,
    StageStatus,
)
from src.models.schemas import QuoteItem, QuoteResponse
from src.services.llm_client import get_llm
from src.services.pdf_parser import detect_file_role, encode_image_base64, get_pdf_parser
from src.utils.fabric_formatter import (
    format_fabric_description,
    format_fabric_dimension,
    is_pattern_fabric,
)
from src.utils.item_normalizer import is_fabric_item, normalize_item_no
from src.utils.logger import PipelineLogger

# ============================================================================
# Checkpoint Functions (FR-007, FR-008, T040-T042)
# ============================================================================


def save_checkpoint(stage_id: int, checkpoint_data: dict) -> None:
    """儲存檢查點資料 (FR-007)

    Args:
        stage_id: 階段 ID
        checkpoint_data: 檢查點資料
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE processing_stages
            SET checkpoint_data = ?
            WHERE stage_id = ?
            """,
            (json.dumps(checkpoint_data, ensure_ascii=False), stage_id),
        )
        conn.commit()


def load_checkpoint(batch_uuid: str, stage_name: StageName) -> dict | None:
    """載入檢查點資料 (FR-008)

    Args:
        batch_uuid: 批次 UUID
        stage_name: 階段名稱

    Returns:
        檢查點資料，若無則返回 None
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ps.checkpoint_data
            FROM processing_stages ps
            JOIN processing_batches pb ON ps.batch_id = pb.batch_id
            WHERE pb.batch_uuid = ? AND ps.stage_name = ?
            """,
            (batch_uuid, stage_name.value),
        )
        row = cursor.fetchone()

        if row and row["checkpoint_data"]:
            return json.loads(row["checkpoint_data"])
        return None


def find_last_completed_stage(batch_uuid: str) -> ProcessingStage | None:
    """找出最後完成的階段 (FR-008)

    Args:
        batch_uuid: 批次 UUID

    Returns:
        最後完成的階段，若無則返回 None
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ps.*
            FROM processing_stages ps
            JOIN processing_batches pb ON ps.batch_id = pb.batch_id
            WHERE pb.batch_uuid = ? AND ps.status = ?
            ORDER BY ps.stage_number DESC
            LIMIT 1
            """,
            (batch_uuid, StageStatus.COMPLETED.value),
        )
        row = cursor.fetchone()

        if row:
            return ProcessingStage.from_row(row)
        return None


def can_resume(batch_uuid: str) -> bool:
    """檢查批次是否可以恢復

    Args:
        batch_uuid: 批次 UUID

    Returns:
        是否可以恢復
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT pb.status
            FROM processing_batches pb
            WHERE pb.batch_uuid = ?
            """,
            (batch_uuid,),
        )
        row = cursor.fetchone()

        if not row:
            return False

        # 只有失敗的批次可以恢復
        return row["status"] == BatchStatus.FAILED.value


def get_resume_stage(batch_uuid: str) -> StageName | None:
    """取得應該恢復的階段

    Args:
        batch_uuid: 批次 UUID

    Returns:
        應該恢復的階段名稱
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        # 找出第一個失敗或待處理的階段
        cursor.execute(
            """
            SELECT ps.stage_name
            FROM processing_stages ps
            JOIN processing_batches pb ON ps.batch_id = pb.batch_id
            WHERE pb.batch_uuid = ? AND ps.status IN (?, ?)
            ORDER BY ps.stage_number ASC
            LIMIT 1
            """,
            (batch_uuid, StageStatus.FAILED.value, StageStatus.PENDING.value),
        )
        row = cursor.fetchone()

        if row:
            return StageName(row["stage_name"])
        return None


def create_batch_stages(batch_id: int) -> list[dict]:
    """建立批次的所有階段記錄

    Args:
        batch_id: 批次 ID

    Returns:
        階段記錄列表
    """
    stages = []
    for stage_name in StageName:
        stage_number = STAGE_NUMBER_MAP[stage_name]
        stages.append(
            {
                "batch_id": batch_id,
                "stage_number": stage_number,
                "stage_name": stage_name.value,
                "status": StageStatus.PENDING.value,
                "progress_percent": 0,
            }
        )
    return stages


def calculate_progress_percent(stage_number: int) -> int:
    """計算進度百分比 (FR-011)

    Args:
        stage_number: 當前階段編號

    Returns:
        進度百分比 (0-100)
    """
    return int((stage_number / TOTAL_STAGES) * 100)


def get_next_stage(current_stage: StageName) -> StageName | None:
    """取得下一階段

    Args:
        current_stage: 當前階段

    Returns:
        下一階段，若為最後階段則返回 None
    """
    current_num = STAGE_NUMBER_MAP[current_stage]
    next_num = current_num + 1

    if next_num > TOTAL_STAGES:
        return None

    for stage_name, num in STAGE_NUMBER_MAP.items():
        if num == next_num:
            return stage_name

    return None


class Pipeline:
    """7 階段處理管線"""

    def __init__(self, batch_uuid: str, supplier_id: str = "fairmont"):
        self.batch_uuid = batch_uuid
        self.supplier_id = supplier_id
        self.logger = PipelineLogger(batch_uuid)
        self.pdf_parser = get_pdf_parser()
        self.llm = get_llm()

        # 處理過程中的資料
        self.parsed_files: list[dict] = []
        self.extracted_items: list[dict] = []
        self.normalized_items: list[dict] = []
        self.merged_items: list[dict] = []
        self.furniture_items: list[dict] = []
        self.fabric_items: list[dict] = []
        self.final_items: list[dict] = []
        self.location_map: dict[str, str] = {}  # item_no → location (從 Index 提取)

    async def run(
        self,
        files: list[tuple[str, bytes]],  # (filename, content)
    ) -> QuoteResponse:
        """執行完整管線

        Args:
            files: 上傳的檔案列表 (檔名, 內容)

        Returns:
            處理結果
        """
        start_time = time.time()
        batch_id = self._create_batch(len(files))

        try:
            # Stage 1: PDF 解析
            await self._stage_pdf_parsing(files)

            # Stage 2: 資料擷取
            await self._stage_extraction()

            # Stage 3: 正規化
            await self._stage_normalization()

            # Stage 4: 合併
            await self._stage_merging()

            # Stage 5: 家具擷取
            await self._stage_furniture_extraction()

            # Stage 6: 面料關聯
            await self._stage_fabric_linking()

            # Stage 7: 匯出
            result = await self._stage_export()

            # 更新批次狀態
            self._update_batch_status(batch_id, BatchStatus.COMPLETED)

            processing_time_ms = int((time.time() - start_time) * 1000)

            return QuoteResponse(
                batch_id=self.batch_uuid,
                supplier_id=self.supplier_id,
                status="completed",
                processing_time_ms=processing_time_ms,
                cached=False,
                items=result,
                errors=[],
            )

        except Exception as e:
            self.logger.error(f"管線處理失敗: {e}")
            self._update_batch_status(batch_id, BatchStatus.FAILED, str(e))
            raise

    def _create_batch(self, file_count: int) -> int:
        """建立批次記錄"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO processing_batches (batch_uuid, supplier_id, status, total_files)
                VALUES (?, ?, ?, ?)
                """,
                (self.batch_uuid, self.supplier_id, BatchStatus.RUNNING.value, file_count),
            )
            conn.commit()
            batch_id = cursor.lastrowid

            # 建立階段記錄
            stages = create_batch_stages(batch_id)
            for stage in stages:
                cursor.execute(
                    """
                    INSERT INTO processing_stages
                    (batch_id, stage_number, stage_name, status, progress_percent)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        stage["batch_id"],
                        stage["stage_number"],
                        stage["stage_name"],
                        stage["status"],
                        stage["progress_percent"],
                    ),
                )
            conn.commit()

            return batch_id

    def _update_batch_status(
        self, batch_id: int, status: BatchStatus, error_message: str | None = None
    ):
        """更新批次狀態"""
        with get_connection() as conn:
            cursor = conn.cursor()
            if status == BatchStatus.COMPLETED:
                cursor.execute(
                    """
                    UPDATE processing_batches
                    SET status = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE batch_id = ?
                    """,
                    (status.value, batch_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE processing_batches
                    SET status = ?, error_message = ?
                    WHERE batch_id = ?
                    """,
                    (status.value, error_message, batch_id),
                )
            conn.commit()

    async def _stage_pdf_parsing(self, files: list[tuple[str, bytes]]):
        """Stage 1: PDF 解析"""
        self.logger.stage_start("PDF_PARSING", 1)
        start = time.time()

        for filename, content in files:
            try:
                # 擷取文字
                text = self.pdf_parser.extract_text_from_bytes(content)

                # 擷取圖片
                images = self.pdf_parser.extract_images_from_bytes(content)

                # 偵測檔案角色
                role = detect_file_role(filename, text[:2000])

                self.parsed_files.append(
                    {
                        "filename": filename,
                        "role": role,
                        "text": text,
                        "images": images,
                    }
                )

                self.logger.debug(f"解析完成: {filename}", role=role.value)
            except Exception as e:
                self.logger.warning(f"解析失敗: {filename}", error=str(e))

        duration_ms = int((time.time() - start) * 1000)
        self.logger.stage_complete("PDF_PARSING", 1, duration_ms)

    async def _stage_extraction(self):
        """Stage 2: 資料擷取 (LLM)"""
        self.logger.stage_start("EXTRACTION", 2)
        start = time.time()

        # 找出規格表
        spec_files = [f for f in self.parsed_files if f["role"] == FileRole.SPEC_SHEET]

        for spec_file in spec_files:
            system_prompt = """你是專業的家具報價單解析助手。
從 PDF 內容中提取所有家具項目。

只輸出 JSON 陣列，格式：
[{
  "item_no": "DLX-100",
  "description": "Bedside Table",
  "dimension": "600 x 450 x 550",
  "uom": "ea",
  "materials": "Solid Oak",
  "brand": "Custom"
}, ...]

不要輸出任何其他說明文字。"""

            try:
                items = await self.llm.call_chunked(system_prompt, spec_file["text"])
                self.extracted_items.extend(items)
                self.logger.debug(f"擷取項目: {len(items)}", file=spec_file["filename"])
            except Exception as e:
                self.logger.warning("擷取失敗", error=str(e))

        # 從 Index PDF 提取 Location (@ 之後文字)
        index_files = [f for f in self.parsed_files if f["role"] == FileRole.INDEX]
        if index_files:
            index_prompt = """從 Index 檔案中提取項目編號與位置資訊。

只輸出 JSON 陣列，格式：
[{
  "item_no": "DLX-100",
  "location": "Deluxe Room"
}, ...]

注意：location 應該是 description 中 @ 符號之後的文字。
不要輸出任何其他說明文字。"""

            try:
                for index_file in index_files:
                    items = await self.llm.call_chunked(index_prompt, index_file["text"])
                    for item in items:
                        if "item_no" in item and "location" in item:
                            item_no = normalize_item_no(item["item_no"])
                            self.location_map[item_no] = item["location"]
                    self.logger.debug(
                        f"Index Location 提取: {len(self.location_map)} 筆",
                        file=index_file["filename"],
                    )
            except Exception as e:
                self.logger.warning("Index 解析失敗", error=str(e))

        duration_ms = int((time.time() - start) * 1000)
        self.logger.stage_complete("EXTRACTION", 2, duration_ms)

    async def _stage_normalization(self):
        """Stage 3: 正規化"""
        self.logger.stage_start("NORMALIZATION", 3)
        start = time.time()

        for item in self.extracted_items:
            normalized = dict(item)
            if "item_no" in normalized:
                normalized["item_no"] = normalize_item_no(normalized["item_no"])
            self.normalized_items.append(normalized)

        duration_ms = int((time.time() - start) * 1000)
        self.logger.stage_complete("NORMALIZATION", 3, duration_ms)

    async def _stage_merging(self):
        """Stage 4: 資料合併 (FR-006: qty 以數量總表為準)"""
        self.logger.stage_start("MERGING", 4)
        start = time.time()

        # 找出數量總表
        qty_files = [f for f in self.parsed_files if f["role"] == FileRole.QUANTITY_SHEET]

        # 從數量總表擷取數量 (簡化版)
        qty_map: dict[str, int] = {}
        if qty_files:
            system_prompt = """從數量總表中提取項目編號和數量。

只輸出 JSON 陣列，格式：
[{"item_no": "DLX-100", "qty": 10}, ...]

不要輸出任何其他說明文字。"""

            try:
                for qty_file in qty_files:
                    items = await self.llm.call_chunked(system_prompt, qty_file["text"])
                    for item in items:
                        if "item_no" in item and "qty" in item:
                            item_no = normalize_item_no(item["item_no"])
                            qty_map[item_no] = item.get("qty", 0)
            except Exception as e:
                self.logger.warning("數量總表解析失敗", error=str(e))

        # 合併數量與 Location
        for item in self.normalized_items:
            merged = dict(item)
            item_no = merged.get("item_no", "")
            # 合併數量 (FR-006: 以數量總表為準)
            if item_no in qty_map:
                merged["qty"] = qty_map[item_no]
            # 合併 Location (從 Index PDF 提取)
            if item_no in self.location_map:
                merged["location"] = self.location_map[item_no]
            self.merged_items.append(merged)

        duration_ms = int((time.time() - start) * 1000)
        self.logger.stage_complete("MERGING", 4, duration_ms)

    async def _stage_furniture_extraction(self):
        """Stage 5: 家具詳情擷取"""
        self.logger.stage_start("FURNITURE", 5)
        start = time.time()

        # 過濾非面料項目
        for item in self.merged_items:
            item_no = item.get("item_no", "")
            if not is_fabric_item(item_no):
                self.furniture_items.append(item)

        duration_ms = int((time.time() - start) * 1000)
        self.logger.stage_complete("FURNITURE", 5, duration_ms)

    async def _stage_fabric_linking(self):
        """Stage 6: 面料關聯 (FR-016)"""
        self.logger.stage_start("FABRIC_LINKING", 6)
        start = time.time()

        # 找出面料表
        fabric_files = [f for f in self.parsed_files if f["role"] == FileRole.FABRIC_SHEET]

        if fabric_files:
            system_prompt = """從面料規格表中提取所有面料項目。PDF 格式如下：
- ITEM NO.: 面料編號 (如 DLX-505)
- ITEM: 面料描述，包含關聯家具 (如 "Fabric @ DLX-102 and DLX-106 Sofa")
- VENDOR: 供應商名稱 (如 "Sankon Interior Limited")
- DESCRIPTION 區塊包含:
  - Brand: 品牌名稱
  - Pattern Name / Pattern Code: 花色編號
  - Width: 幅寬
  - Content: 材質成分

只輸出 JSON 陣列，格式：
[{
  "item_no": "DLX-505",
  "description": "Fabric @ DLX-102 and DLX-106 Sofa",
  "vendor": "Sankon Interior Limited",
  "brand": "Bravo Collection",
  "pattern": "BV106-05M084C",
  "width": "140 cm",
  "content": "55% cotton , 40% viscose , 5% linen",
  "materials": "Abrasion: 40,000 Double Rubs",
  "furniture_com": "DLX-102 AND DLX-106",
  "has_repeat": true
}, ...]

欄位說明：
- item_no: ITEM NO. 欄位的值
- description: ITEM 欄位的完整文字
- vendor: VENDOR 欄位的供應商名稱
- brand: DESCRIPTION 中 Brand 的值
- pattern: DESCRIPTION 中 Pattern Name / Pattern Code 的值
- width: DESCRIPTION 中 Width 的值
- content: DESCRIPTION 中 Content 的值 (材質成分)
- materials: DESCRIPTION 中其他規格 (如 Abrasion)
- furniture_com: 從 ITEM 欄位提取關聯家具編號 (@ 後的 DLX-xxx)
- has_repeat: 是否有重複圖案 (預設 true)

不要輸出任何其他說明文字。"""

            try:
                for fabric_file in fabric_files:
                    items = await self.llm.call_chunked(system_prompt, fabric_file["text"])
                    self.logger.info(f"面料 LLM 回傳 {len(items)} 項")
                    for item in items:
                        if "item_no" in item:
                            item["item_no"] = normalize_item_no(item["item_no"])
                        # 正規化 furniture_com
                        if "furniture_com" in item and item["furniture_com"]:
                            item["furniture_com"] = normalize_item_no(item["furniture_com"])
                        # 日誌記錄面料項目詳情 (INFO 級別)
                        self.logger.info(
                            f"面料項目: {item.get('item_no')} | "
                            f"furniture_com={item.get('furniture_com')} | "
                            f"brand={item.get('brand')}"
                        )
                        self.fabric_items.append(item)
            except Exception as e:
                self.logger.warning("面料表解析失敗", error=str(e))

        duration_ms = int((time.time() - start) * 1000)
        self.logger.stage_complete("FABRIC_LINKING", 6, duration_ms)

    async def _stage_export(self) -> list[QuoteItem]:
        """Stage 7: 匯出 15 欄位 JSON (Fabric-Follows-Furniture)"""
        self.logger.stage_start("EXPORT", 7)
        start = time.time()

        result = []

        # 建立圖片映射
        furniture_image_map = self._build_image_map()
        fabric_image_map = self._build_fabric_image_map()

        # 建立 furniture item_no → [fabric items] 映射
        furniture_to_fabrics = self._build_furniture_fabric_map()

        # 序號從 1 開始
        seq_no = 1

        # Fabric-Follows-Furniture 排序
        for furniture in self.furniture_items:
            furniture_item_no = furniture.get("item_no", "")

            # 1. 輸出家具項目
            furniture_quote = self._format_furniture_item(
                furniture, seq_no, furniture_image_map
            )
            result.append(furniture_quote)
            seq_no += 1

            # 2. 緊接輸出關聯面料
            associated_fabrics = furniture_to_fabrics.get(furniture_item_no, [])
            for fabric in associated_fabrics:
                fabric_quote = self._format_fabric_item(
                    fabric, seq_no, fabric_image_map, furniture_item_no
                )
                result.append(fabric_quote)
                seq_no += 1

        # 3. 輸出孤立面料 (無關聯家具)
        orphan_fabrics = self._get_orphan_fabrics(furniture_to_fabrics)
        for fabric in orphan_fabrics:
            fabric_quote = self._format_fabric_item(
                fabric, seq_no, fabric_image_map, None
            )
            result.append(fabric_quote)
            seq_no += 1

        duration_ms = int((time.time() - start) * 1000)
        self.logger.stage_complete("EXPORT", 7, duration_ms)

        return result

    def _build_furniture_fabric_map(self) -> dict[str, list[dict]]:
        """建立 furniture item_no → [fabric items] 映射

        處理 furniture_com 可能包含 "AND" 連接多個家具項目的情況
        例如: "DLX-102 AND DLX-106" → 同時關聯到 DLX-102 和 DLX-106
        """
        mapping: dict[str, list[dict]] = {}

        for fabric in self.fabric_items:
            furniture_com = fabric.get("furniture_com", "")
            if furniture_com:
                # 分割 "AND" 連接的多個家具項目
                furniture_items = [
                    normalize_item_no(item.strip())
                    for item in furniture_com.upper().split("AND")
                ]
                for furniture_item_no in furniture_items:
                    if furniture_item_no:
                        if furniture_item_no not in mapping:
                            mapping[furniture_item_no] = []
                        mapping[furniture_item_no].append(fabric)

        return mapping

    def _get_orphan_fabrics(self, furniture_to_fabrics: dict[str, list[dict]]) -> list[dict]:
        """取得無關聯家具的面料

        孤立面料定義：
        1. 沒有 furniture_com 的面料
        2. 有 furniture_com 但對應的家具不在 furniture_items 中的面料
        """
        # 建立現有家具項目編號集合
        existing_furniture_nos = {
            normalize_item_no(f.get("item_no", ""))
            for f in self.furniture_items
        }

        # 收集已輸出的面料 item_no (只有當對應家具存在時才算已輸出)
        output_fabric_nos = set()
        for furniture_no, fabrics in furniture_to_fabrics.items():
            if furniture_no in existing_furniture_nos:
                for fabric in fabrics:
                    output_fabric_nos.add(fabric.get("item_no", ""))

        # 找出孤立面料
        orphans = []
        for fabric in self.fabric_items:
            fabric_item_no = fabric.get("item_no", "")
            if fabric_item_no not in output_fabric_nos:
                orphans.append(fabric)

        return orphans

    def _format_furniture_item(
        self, item: dict, seq_no: int, image_map: dict[str, str]
    ) -> QuoteItem:
        """格式化家具項目 (brand 強制 Null)"""
        item_no = item.get("item_no", "")

        return QuoteItem(
            # 1-7: 核心欄位
            no=seq_no,
            item_no=item_no,
            description=item.get("description"),
            photo_base64=image_map.get(item_no),
            dimension=item.get("dimension") or item.get("dimensions"),
            qty=item.get("qty"),
            uom=item.get("uom") or "ea",
            # 8-12: 預留欄位
            unit_rate=None,
            amount=None,
            unit_cbm=None,
            total_cbm=None,
            note=None,
            # 13-15: 元資料欄位
            location=item.get("location"),
            materials_used=item.get("materials"),
            brand=None,  # 家具 brand 強制 Null
        )

    def _format_fabric_item(
        self,
        fabric: dict,
        seq_no: int,
        image_map: dict[str, str],
        furniture_item_no: str | None,
    ) -> QuoteItem:
        """格式化面料項目 (使用 EXCEL_OUTPUT_SPECIFICATION.md 規格)"""
        item_no = fabric.get("item_no", "")
        brand = fabric.get("brand")
        pattern = fabric.get("pattern")
        color = fabric.get("color")
        width = fabric.get("width")
        content = fabric.get("content")
        vendor = fabric.get("vendor")
        has_repeat = fabric.get("has_repeat", True)

        # 格式化 Dimension: {材質}-{供應商}-{品牌}-{花色}-{寬度} pattern/plain
        dimension = format_fabric_dimension(
            content=content,
            vendor=vendor,
            brand=brand,
            pattern=pattern or color,
            width=width,
            has_repeat=is_pattern_fabric(has_repeat),
        )

        # 格式化 Description: {material_type} to {furniture_item_no}
        # 根據 EXCEL_OUTPUT_SPECIFICATION.md 規格
        original_desc = fabric.get("description", "")

        # 從原始描述中提取材質類型 (@ 之前的部分)
        material_type = None
        if original_desc and "@" in original_desc:
            # "Fabric @ DLX-102 Sofa" → "Fabric"
            material_type = original_desc.split("@")[0].strip()
        elif original_desc:
            material_type = original_desc

        # 若無法提取，根據 content 推斷
        if not material_type:
            if content:
                first_part = content.split("-")[0].strip()
                if not any(char.isdigit() for char in first_part[:3]):
                    material_type = first_part
            if not material_type:
                if "vinyl" in (content or "").lower():
                    material_type = "Vinyl"
                elif "leather" in (content or "").lower():
                    material_type = "Leather"
                else:
                    material_type = "Fabric"

        # 優先使用 furniture_com (完整的關聯家具編號，如 "DLX-102 AND DLX-106")
        # 若 furniture_com 為空，則使用傳入的 furniture_item_no
        target_furniture = fabric.get("furniture_com") or furniture_item_no
        description = format_fabric_description(material_type, target_furniture)

        return QuoteItem(
            # 1-7: 核心欄位
            no=seq_no,
            item_no=item_no,
            description=description,
            photo_base64=image_map.get(item_no),
            dimension=dimension,
            qty=None,  # 面料 qty 留空
            uom=fabric.get("uom") or "m",
            # 8-12: 預留欄位
            unit_rate=None,
            amount=None,
            unit_cbm=None,
            total_cbm=None,
            note=None,
            # 13-15: 元資料欄位
            location=None,  # 面料通常無 location
            materials_used=fabric.get("materials"),
            brand=brand,  # 面料 brand 必填
        )

    def _build_image_map(self) -> dict[str, str]:
        """建立家具 item_no 到 Base64 圖片的對照"""
        spec_files = [f for f in self.parsed_files if f["role"] == FileRole.SPEC_SHEET]

        image_map = {}
        for spec_file in spec_files:
            images = spec_file.get("images", [])
            for i, img in enumerate(images):
                if i < len(self.furniture_items):
                    item = self.furniture_items[i]
                    item_no = item.get("item_no", "")
                    if item_no and item_no not in image_map:
                        ext = img.get("ext", "png")
                        mime = f"image/{ext}"
                        image_map[item_no] = encode_image_base64(img["data"], mime)

        return image_map

    def _build_fabric_image_map(self) -> dict[str, str]:
        """建立面料 item_no 到 Base64 圖片的對照"""
        fabric_files = [f for f in self.parsed_files if f["role"] == FileRole.FABRIC_SHEET]

        image_map = {}
        for fabric_file in fabric_files:
            images = fabric_file.get("images", [])
            for i, img in enumerate(images):
                if i < len(self.fabric_items):
                    fabric = self.fabric_items[i]
                    item_no = fabric.get("item_no", "")
                    if item_no and item_no not in image_map:
                        ext = img.get("ext", "png")
                        mime = f"image/{ext}"
                        image_map[item_no] = encode_image_base64(img["data"], mime)

        return image_map


async def run_pipeline(
    batch_uuid: str,
    files: list[tuple[str, bytes]],
    supplier_id: str = "fairmont",
) -> QuoteResponse:
    """執行管線處理

    Args:
        batch_uuid: 批次 UUID
        files: 檔案列表 (檔名, 內容)
        supplier_id: 供應商 ID

    Returns:
        處理結果
    """
    pipeline = Pipeline(batch_uuid, supplier_id)
    return await pipeline.run(files)
