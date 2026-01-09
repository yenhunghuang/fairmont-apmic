"""
使用真實 PDF 測試 Adapter 角色識別功能
"""

import sys
from pathlib import Path

# 加入專案路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

import pdfplumber
from src.services.adapters.base import ParsedTable, FileRole
from src.services.adapters.fairmont import FairmontAdapter


def extract_pdf_content(pdf_path: Path) -> tuple[str, list[ParsedTable]]:
    """從 PDF 提取文字和表格"""
    text_content = []
    tables = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages[:5], 1):  # 只讀前 5 頁
            # 提取文字
            page_text = page.extract_text() or ""
            text_content.append(page_text)

            # 提取表格
            page_tables = page.extract_tables() or []
            for table in page_tables:
                if table and len(table) > 1:
                    headers = [str(h or "").strip() for h in table[0]]
                    rows = [[str(cell or "").strip() for cell in row] for row in table[1:]]
                    tables.append(ParsedTable(
                        headers=headers,
                        rows=rows[:10],  # 只取前 10 行
                        page_number=page_num
                    ))

    return "\n".join(text_content), tables


def main():
    docs_dir = Path(__file__).parent.parent / "docs"
    adapter = FairmontAdapter()

    print("=" * 70)
    print("Fairmont Adapter - 真實 PDF 角色識別測試")
    print("=" * 70)
    print()

    pdf_files = list(docs_dir.glob("*.pdf"))

    for pdf_path in pdf_files:
        print(f"📄 檔案: {pdf_path.name}")
        print("-" * 50)

        try:
            content, tables = extract_pdf_content(pdf_path)

            # 顯示提取的資訊
            print(f"   文字長度: {len(content)} 字元")
            print(f"   表格數量: {len(tables)}")

            if tables:
                print(f"   表格欄位: {tables[0].headers[:5]}...")

            # 使用 Adapter 識別角色
            role = adapter.detect_file_role(content, tables)

            role_emoji = {
                FileRole.QUANTITY_SHEET: "📊",
                FileRole.SPEC_SHEET: "📋",
                FileRole.FABRIC_SHEET: "🧵",
                FileRole.INDEX: "📑",
                FileRole.UNKNOWN: "❓",
            }

            print(f"   識別結果: {role_emoji.get(role, '❓')} {role.value}")

            # 如果是規格書，嘗試找出 Item No.
            if role == FileRole.SPEC_SHEET:
                import re
                item_nos = re.findall(r'[A-Z]{2,4}-\d{2,4}(?:\.\d+)?', content)
                unique_items = list(set(item_nos))[:5]
                if unique_items:
                    print(f"   找到 Item No.: {unique_items}")

            # 如果是面料表，嘗試找出 500 系列
            if role == FileRole.FABRIC_SHEET:
                import re
                fabric_nos = re.findall(r'\b5\d{2}\b', content)
                unique_fabrics = list(set(fabric_nos))[:5]
                if unique_fabrics:
                    print(f"   找到面料編號: {unique_fabrics}")

        except Exception as e:
            print(f"   ❌ 錯誤: {e}")

        print()

    # 測試 Item No. 正規化
    print("=" * 70)
    print("Item No. 正規化測試")
    print("=" * 70)

    test_items = [
        "DLX-201 .1",
        "DLX 100",
        "SUT-300",
        "dlx-150",
        "501",
        "BAY-1010",
    ]

    for item in test_items:
        normalized = adapter.normalize_item_no(item)
        is_fabric = adapter.is_fabric_item(item)
        fabric_mark = "🧵" if is_fabric else "🪑"
        print(f"   {item:15} → {normalized:15} {fabric_mark}")

    print()
    print("✅ 測試完成！")


if __name__ == "__main__":
    main()
