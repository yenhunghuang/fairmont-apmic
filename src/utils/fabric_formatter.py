"""面料項目格式化工具函式

符合 EXCEL_OUTPUT_SPECIFICATION.md 規格
"""


def format_fabric_dimension(
    content: str | None,
    vendor: str | None,
    brand: str | None,
    pattern: str | None,
    width: float | str | None,
    has_repeat: bool = True,
) -> str:
    """格式化面料 Dimension 字串

    格式: {材質}-{供應商}-{品牌}-{花色}-{寬度} pattern/plain

    Args:
        content: 材質成分 (如 "100% Polyester")
        vendor: 供應商名稱
        brand: 品牌名稱 (如 "JAB", "Kvadrat")
        pattern: 花色/圖案名稱
        width: 幅寬 (如 140, "140cm", "137cmW")
        has_repeat: 是否有重複圖案 (True=pattern, False=plain)

    Returns:
        格式化後的 Dimension 字串
    """
    parts = []

    if content:
        parts.append(str(content).strip())
    if vendor:
        parts.append(str(vendor).strip())
    if brand:
        parts.append(str(brand).strip())
    if pattern:
        parts.append(str(pattern).strip())
    if width:
        width_str = str(width).strip()
        # 若已包含單位則直接使用，否則加上 cmW
        if not any(unit in width_str.lower() for unit in ["cm", "mm", "in"]):
            width_str = f"{width_str}cmW"
        parts.append(width_str)

    base = "-".join(parts) if parts else ""
    suffix = "pattern" if has_repeat else "plain"

    return f"{base} {suffix}" if base else suffix


def format_fabric_description(
    material_type: str | None,
    target_item_no: str | None,
) -> str:
    """格式化面料 Description 字串

    格式: {material_type} to {target_item_no}

    Args:
        material_type: 材料類型 (如 "Vinyl", "Fabric", "Leather")
        target_item_no: 關聯的家具 Item No.

    Returns:
        格式化後的 Description 字串
    """
    if not material_type:
        material_type = "Fabric"

    if not target_item_no:
        return material_type

    return f"{material_type} to {target_item_no}"


def extract_location_from_description(description: str | None) -> str | None:
    """從 Description 中提取 Location (@ 之後的文字)

    Args:
        description: 原始描述文字 (如 "Bedside Table @ Deluxe Room")

    Returns:
        Location 字串，若無 @ 符號則返回 None
    """
    if not description or "@" not in description:
        return None

    # 取 @ 之後的部分
    parts = description.split("@", 1)
    if len(parts) > 1:
        location = parts[1].strip()
        return location if location else None

    return None


def is_pattern_fabric(has_repeat: bool | None) -> bool:
    """判斷面料是 pattern 還是 plain

    Args:
        has_repeat: 從 PDF 中判斷是否有 repeat (重複圖案)
                   若為 None 則預設為 False (plain)

    Returns:
        True = pattern, False = plain
    """
    if has_repeat is None:
        return False  # 預設為 plain
    return bool(has_repeat)
