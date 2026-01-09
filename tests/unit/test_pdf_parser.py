"""PDF 解析單元測試 (T019)"""

from pathlib import Path

import pytest


class TestPdfParser:
    """PDF 解析器測試"""

    @pytest.fixture
    def sample_pdf_content(self) -> bytes:
        """模擬 PDF 內容"""
        # 簡單的 PDF 結構 (用於測試)
        return b"%PDF-1.4 test content"

    def test_extract_text_from_pdf(self, tmp_path: Path, sample_pdf_content: bytes):
        """測試從 PDF 擷取文字"""
        # 需要實際 PDF 才能測試
        pass

    def test_extract_tables_from_pdf(self):
        """測試從 PDF 擷取表格"""
        pass

    def test_detect_file_role_quantity_sheet(self):
        """測試偵測檔案角色：數量總表"""
        from src.models.entities import FileRole
        from src.services.pdf_parser import detect_file_role

        # 根據檔名和內容特徵判斷
        result = detect_file_role("Bay Tower Furniture - Overall Qty.pdf", "QTY TOTAL 100")
        assert result == FileRole.QUANTITY_SHEET

    def test_detect_file_role_spec_sheet(self):
        """測試偵測檔案角色：規格表"""
        from src.models.entities import FileRole
        from src.services.pdf_parser import detect_file_role

        result = detect_file_role("Casegoods & Seatings-1-9.pdf", "Item No. DLX-100")
        assert result == FileRole.SPEC_SHEET

    def test_detect_file_role_fabric_sheet(self):
        """測試偵測檔案角色：面料表"""
        from src.models.entities import FileRole
        from src.services.pdf_parser import detect_file_role

        result = detect_file_role("Fabric & Leather-11-20.pdf", "500-001 Vinyl")
        assert result == FileRole.FABRIC_SHEET

    def test_detect_file_role_index(self):
        """測試偵測檔案角色：Index"""
        from src.models.entities import FileRole
        from src.services.pdf_parser import detect_file_role

        result = detect_file_role("index.pdf", "INDEX TABLE OF CONTENTS")
        assert result == FileRole.INDEX


class TestImageExtractor:
    """圖片擷取器測試"""

    def test_extract_images_from_pdf(self):
        """測試從 PDF 擷取圖片"""
        # 需要實際 PDF 才能測試
        pass

    def test_deduplicate_images(self):
        """測試圖片去重 (FR-005)"""
        from src.services.pdf_parser import deduplicate_images

        # 模擬圖片資料
        images = [
            {"hash": "abc123", "data": b"image1", "width": 100, "height": 100},
            {"hash": "abc123", "data": b"image1_copy", "width": 50, "height": 50},  # 重複
            {"hash": "def456", "data": b"image2", "width": 200, "height": 200},
        ]

        result = deduplicate_images(images)
        assert len(result) == 2
        # 應該保留解析度較高的版本
        assert any(img["hash"] == "abc123" and img["width"] == 100 for img in result)

    def test_select_best_resolution(self):
        """測試選擇最佳解析度 (FR-005)"""
        from src.services.pdf_parser import select_best_resolution

        candidates = [
            {"width": 100, "height": 100, "data": b"small"},
            {"width": 500, "height": 500, "data": b"large"},
            {"width": 200, "height": 200, "data": b"medium"},
        ]

        result = select_best_resolution(candidates)
        assert result["width"] == 500
        assert result["height"] == 500
