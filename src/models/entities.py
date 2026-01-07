"""資料庫實體定義 (Enums and Data Classes)"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

# === Enums ===


class BatchStatus(str, Enum):
    """處理批次狀態"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FileRole(str, Enum):
    """檔案角色"""

    QUANTITY_SHEET = "QUANTITY_SHEET"  # 數量總表
    SPEC_SHEET = "SPEC_SHEET"  # 明細規格表
    FABRIC_SHEET = "FABRIC_SHEET"  # 面料表
    INDEX = "INDEX"  # Index 檔案


class FileStatus(str, Enum):
    """檔案處理狀態"""

    PENDING = "PENDING"
    CACHED = "CACHED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StageName(str, Enum):
    """處理階段名稱"""

    PDF_PARSING = "PDF_PARSING"  # 階段 1: PDF 解析
    EXTRACTION = "EXTRACTION"  # 階段 2: 資料擷取
    NORMALIZATION = "NORMALIZATION"  # 階段 3: 正規化
    MERGING = "MERGING"  # 階段 4: 資料合併
    FURNITURE = "FURNITURE"  # 階段 5: 家具擷取
    FABRIC_LINKING = "FABRIC_LINKING"  # 階段 6: 面料關聯
    EXPORT = "EXPORT"  # 階段 7: 匯出


class StageStatus(str, Enum):
    """階段處理狀態"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class FurnitureStatus(str, Enum):
    """家具項目狀態"""

    SUCCESS = "SUCCESS"
    FAILED_EXTRACTION = "FAILED_EXTRACTION"
    PENDING_REVIEW = "PENDING_REVIEW"


class FabricStatus(str, Enum):
    """面料項目狀態"""

    SUCCESS = "SUCCESS"
    PENDING_LINK = "PENDING_LINK"
    ORPHAN = "ORPHAN"


# 階段編號對照
STAGE_NUMBER_MAP = {
    StageName.PDF_PARSING: 1,
    StageName.EXTRACTION: 2,
    StageName.NORMALIZATION: 3,
    StageName.MERGING: 4,
    StageName.FURNITURE: 5,
    StageName.FABRIC_LINKING: 6,
    StageName.EXPORT: 7,
}

# 階段中文名稱對照
STAGE_DISPLAY_NAME = {
    StageName.PDF_PARSING: "PDF 解析中",
    StageName.EXTRACTION: "資料擷取中",
    StageName.NORMALIZATION: "正規化處理中",
    StageName.MERGING: "資料合併中",
    StageName.FURNITURE: "家具詳情擷取中",
    StageName.FABRIC_LINKING: "面料關聯中",
    StageName.EXPORT: "匯出中",
}

TOTAL_STAGES = 7


# === Data Classes ===


@dataclass
class ProcessingBatch:
    """處理批次"""

    batch_id: int | None = None
    batch_uuid: str = ""
    supplier_id: str = "fairmont"
    status: BatchStatus = BatchStatus.PENDING
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_files: int = 0
    processed_files: int = 0
    error_message: str | None = None

    @classmethod
    def from_row(cls, row: Any) -> "ProcessingBatch":
        """從 sqlite3.Row 建立實例"""
        return cls(
            batch_id=row["batch_id"],
            batch_uuid=row["batch_uuid"],
            supplier_id=row["supplier_id"] or "fairmont",
            status=BatchStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=(
                datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
            ),
            total_files=row["total_files"] or 0,
            processed_files=row["processed_files"] or 0,
            error_message=row["error_message"],
        )


@dataclass
class UploadedFile:
    """上傳檔案"""

    file_id: int | None = None
    batch_id: int = 0
    file_hash: str = ""
    original_filename: str = ""
    file_role: FileRole = FileRole.SPEC_SHEET
    file_size_bytes: int | None = None
    status: FileStatus = FileStatus.PENDING
    uploaded_at: datetime | None = None
    cached_result_path: str | None = None

    @classmethod
    def from_row(cls, row: Any) -> "UploadedFile":
        """從 sqlite3.Row 建立實例"""
        return cls(
            file_id=row["file_id"],
            batch_id=row["batch_id"],
            file_hash=row["file_hash"],
            original_filename=row["original_filename"],
            file_role=FileRole(row["file_role"]),
            file_size_bytes=row["file_size_bytes"],
            status=FileStatus(row["status"]),
            uploaded_at=datetime.fromisoformat(row["uploaded_at"]) if row["uploaded_at"] else None,
            cached_result_path=row["cached_result_path"],
        )


@dataclass
class ProcessingStage:
    """處理階段"""

    stage_id: int | None = None
    batch_id: int = 0
    stage_number: int = 1
    stage_name: StageName = StageName.PDF_PARSING
    status: StageStatus = StageStatus.PENDING
    progress_percent: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    execution_time_ms: int | None = None
    error_message: str | None = None
    retry_count: int = 0
    checkpoint_data: str | None = None

    @classmethod
    def from_row(cls, row: Any) -> "ProcessingStage":
        """從 sqlite3.Row 建立實例"""
        return cls(
            stage_id=row["stage_id"],
            batch_id=row["batch_id"],
            stage_number=row["stage_number"],
            stage_name=StageName(row["stage_name"]),
            status=StageStatus(row["status"]),
            progress_percent=row["progress_percent"] or 0,
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=(
                datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
            ),
            execution_time_ms=row["execution_time_ms"],
            error_message=row["error_message"],
            retry_count=row["retry_count"] or 0,
            checkpoint_data=row["checkpoint_data"],
        )


@dataclass
class FurnitureItem:
    """家具項目"""

    item_id: int | None = None
    batch_id: int = 0
    item_no: str = ""
    description: str | None = None
    dimensions: str | None = None
    qty: int | None = None
    uom: str | None = None
    materials: str | None = None
    location: str | None = None
    photo_path: str | None = None
    brand: str | None = None
    status: FurnitureStatus = FurnitureStatus.SUCCESS
    related_fabric_ids: str | None = None  # JSON array
    created_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Any) -> "FurnitureItem":
        """從 sqlite3.Row 建立實例"""
        return cls(
            item_id=row["item_id"],
            batch_id=row["batch_id"],
            item_no=row["item_no"],
            description=row["description"],
            dimensions=row["dimensions"],
            qty=row["qty"],
            uom=row["uom"],
            materials=row["materials"],
            location=row["location"],
            photo_path=row["photo_path"],
            brand=row["brand"],
            status=FurnitureStatus(row["status"]) if row["status"] else FurnitureStatus.SUCCESS,
            related_fabric_ids=row["related_fabric_ids"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )


@dataclass
class FabricItem:
    """面料項目"""

    fabric_id: int | None = None
    batch_id: int = 0
    item_no: str = ""
    brand: str | None = None
    pattern: str | None = None
    color: str | None = None
    width: float | None = None
    content: str | None = None
    abrasion: str | None = None
    vendor: str | None = None
    furniture_com: str | None = None  # 關聯家具 Item No.
    status: FabricStatus = FabricStatus.PENDING_LINK
    created_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Any) -> "FabricItem":
        """從 sqlite3.Row 建立實例"""
        return cls(
            fabric_id=row["fabric_id"],
            batch_id=row["batch_id"],
            item_no=row["item_no"],
            brand=row["brand"],
            pattern=row["pattern"],
            color=row["color"],
            width=row["width"],
            content=row["content"],
            abrasion=row["abrasion"],
            vendor=row["vendor"],
            furniture_com=row["furniture_com"],
            status=FabricStatus(row["status"]) if row["status"] else FabricStatus.PENDING_LINK,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )


@dataclass
class CacheRecord:
    """快取記錄"""

    cache_id: int | None = None
    file_hash: str = ""
    result_path: str = ""
    created_at: datetime | None = None
    expires_at: datetime | None = None
    hit_count: int = 0

    @classmethod
    def from_row(cls, row: Any) -> "CacheRecord":
        """從 sqlite3.Row 建立實例"""
        return cls(
            cache_id=row["cache_id"],
            file_hash=row["file_hash"],
            result_path=row["result_path"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            hit_count=row["hit_count"] or 0,
        )
