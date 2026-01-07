"""PDF 解析服務"""

import base64
import hashlib
import io
from pathlib import Path

from src.models.entities import FileRole


def detect_file_role(filename: str, content_preview: str = "") -> FileRole:
    """偵測 PDF 檔案角色 (FR-002)

    根據檔名和內容特徵判斷檔案類型

    Args:
        filename: 檔案名稱
        content_preview: 內容預覽 (前幾頁文字)

    Returns:
        FileRole: 檔案角色
    """
    filename_lower = filename.lower()
    content_lower = content_preview.lower()

    # 優先根據檔名判斷
    if "qty" in filename_lower or "quantity" in filename_lower or "overall" in filename_lower:
        return FileRole.QUANTITY_SHEET

    # Fabric/Leather 檔名判斷 (必須是專門的面料表)
    if "fabric" in filename_lower and "leather" in filename_lower:
        return FileRole.FABRIC_SHEET
    if filename_lower.startswith("fabric") or filename_lower.startswith("leather"):
        return FileRole.FABRIC_SHEET

    if "index" in filename_lower:
        return FileRole.INDEX

    # Casegoods, Seatings, Furniture 等為規格表
    if any(kw in filename_lower for kw in ["casegood", "seating", "furniture", "spec"]):
        return FileRole.SPEC_SHEET

    # 根據內容判斷 (更嚴格的條件)
    if "qty" in content_lower and "total" in content_lower:
        return FileRole.QUANTITY_SHEET

    # 面料表的判斷：開頭是 "500 Fabric" 或內容主要是面料描述
    if content_lower.startswith("500 fabric") or "500 fabric, vinyl" in content_lower:
        return FileRole.FABRIC_SHEET

    if "index" in content_lower and "project name" in content_lower:
        return FileRole.INDEX

    # 規格表特徵：包含 "100 Seating" 或 "ITEM NO.:" 等
    if "100 seating" in content_lower or "item no.:" in content_lower:
        return FileRole.SPEC_SHEET

    # 預設為規格表
    return FileRole.SPEC_SHEET


def deduplicate_images(images: list[dict]) -> list[dict]:
    """圖片去重 (FR-005)

    相同 hash 的圖片保留解析度最高的版本

    Args:
        images: 圖片列表，每個包含 hash, width, height, data

    Returns:
        去重後的圖片列表
    """
    if not images:
        return []

    # 按 hash 分組
    by_hash: dict[str, list[dict]] = {}
    for img in images:
        img_hash = img.get("hash", "")
        if img_hash not in by_hash:
            by_hash[img_hash] = []
        by_hash[img_hash].append(img)

    # 每組選擇最佳解析度
    result = []
    for candidates in by_hash.values():
        best = select_best_resolution(candidates)
        result.append(best)

    return result


def select_best_resolution(candidates: list[dict]) -> dict:
    """選擇最佳解析度的圖片 (FR-005)

    Args:
        candidates: 同一圖片的不同版本

    Returns:
        解析度最高的版本
    """
    if not candidates:
        return {}

    return max(candidates, key=lambda x: x.get("width", 0) * x.get("height", 0))


def compute_image_hash(image_data: bytes) -> str:
    """計算圖片 hash

    Args:
        image_data: 圖片二進位資料

    Returns:
        SHA256 hash
    """
    return hashlib.sha256(image_data).hexdigest()


def encode_image_base64(image_data: bytes, mime_type: str = "image/png") -> str:
    """將圖片編碼為 Base64

    Args:
        image_data: 圖片二進位資料
        mime_type: MIME 類型

    Returns:
        Data URI 格式的 Base64 字串
    """
    encoded = base64.b64encode(image_data).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


class PdfParser:
    """PDF 解析器"""

    def __init__(self):
        self._pdfplumber = None
        self._fitz = None

    def _get_pdfplumber(self):
        """延遲載入 pdfplumber"""
        if self._pdfplumber is None:
            import pdfplumber

            self._pdfplumber = pdfplumber
        return self._pdfplumber

    def _get_fitz(self):
        """延遲載入 PyMuPDF"""
        if self._fitz is None:
            import fitz

            self._fitz = fitz
        return self._fitz

    def extract_text(self, pdf_path: Path | str) -> str:
        """從 PDF 擷取文字

        Args:
            pdf_path: PDF 檔案路徑

        Returns:
            擷取的文字內容
        """
        pdfplumber = self._get_pdfplumber()
        text_parts = []

        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    text_parts.append(page_text)
        except Exception as e:
            raise ValueError(f"無法解析 PDF: {e}")

        return "\n\n".join(text_parts)

    def extract_text_from_bytes(self, pdf_bytes: bytes) -> str:
        """從 PDF 二進位資料擷取文字

        Args:
            pdf_bytes: PDF 二進位資料

        Returns:
            擷取的文字內容
        """
        pdfplumber = self._get_pdfplumber()
        text_parts = []

        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    text_parts.append(page_text)
        except Exception as e:
            raise ValueError(f"無法解析 PDF: {e}")

        return "\n\n".join(text_parts)

    def extract_tables(self, pdf_path: Path | str) -> list[list[list[str]]]:
        """從 PDF 擷取表格

        Args:
            pdf_path: PDF 檔案路徑

        Returns:
            表格列表 (每頁的表格列表)
        """
        pdfplumber = self._get_pdfplumber()
        all_tables = []

        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables() or []
                    all_tables.extend(tables)
        except Exception as e:
            raise ValueError(f"無法擷取表格: {e}")

        return all_tables

    def extract_images(self, pdf_path: Path | str) -> list[dict]:
        """從 PDF 擷取圖片

        使用 PyMuPDF (fitz) 擷取圖片

        Args:
            pdf_path: PDF 檔案路徑

        Returns:
            圖片列表，每個包含 page, data, width, height, hash
        """
        fitz = self._get_fitz()
        images = []

        try:
            doc = fitz.open(str(pdf_path))
            for page_num, page in enumerate(doc):
                image_list = page.get_images()

                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    try:
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        img_hash = compute_image_hash(image_bytes)

                        images.append(
                            {
                                "page": page_num + 1,
                                "index": img_index,
                                "data": image_bytes,
                                "width": base_image.get("width", 0),
                                "height": base_image.get("height", 0),
                                "ext": base_image.get("ext", "png"),
                                "hash": img_hash,
                            }
                        )
                    except Exception:
                        continue  # 跳過無法擷取的圖片

            doc.close()
        except Exception as e:
            raise ValueError(f"無法擷取圖片: {e}")

        return deduplicate_images(images)

    def extract_images_from_bytes(self, pdf_bytes: bytes) -> list[dict]:
        """從 PDF 二進位資料擷取圖片

        Args:
            pdf_bytes: PDF 二進位資料

        Returns:
            圖片列表
        """
        fitz = self._get_fitz()
        images = []

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page_num, page in enumerate(doc):
                image_list = page.get_images()

                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    try:
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        img_hash = compute_image_hash(image_bytes)

                        images.append(
                            {
                                "page": page_num + 1,
                                "index": img_index,
                                "data": image_bytes,
                                "width": base_image.get("width", 0),
                                "height": base_image.get("height", 0),
                                "ext": base_image.get("ext", "png"),
                                "hash": img_hash,
                            }
                        )
                    except Exception:
                        continue

            doc.close()
        except Exception as e:
            raise ValueError(f"無法擷取圖片: {e}")

        return deduplicate_images(images)


# 全域單例
_parser: PdfParser | None = None


def get_pdf_parser() -> PdfParser:
    """取得 PDF 解析器單例"""
    global _parser
    if _parser is None:
        _parser = PdfParser()
    return _parser
