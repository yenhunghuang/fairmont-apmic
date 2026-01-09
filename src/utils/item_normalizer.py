"""Item No. 正規化工具 (FR-015)"""

import re

# 各種 dash 字元的 Unicode
DASH_CHARS = [
    "\u2010",  # HYPHEN
    "\u2011",  # NON-BREAKING HYPHEN
    "\u2012",  # FIGURE DASH
    "\u2013",  # EN DASH
    "\u2014",  # EM DASH
    "\u2015",  # HORIZONTAL BAR
    "\u2212",  # MINUS SIGN
    "\ufe58",  # SMALL EM DASH
    "\ufe63",  # SMALL HYPHEN-MINUS
    "\uff0d",  # FULLWIDTH HYPHEN-MINUS
]

# 編譯正則表達式
DASH_PATTERN = re.compile(f"[{''.join(DASH_CHARS)}]")
SPACE_AROUND_DASH_PATTERN = re.compile(r"\s*-\s*")
MULTIPLE_SPACES_PATTERN = re.compile(r"\s{2,}")


def normalize_item_no(item_no: str | None) -> str:
    """正規化 Item No.

    規則 (FR-015):
    1. 去除首尾空白
    2. 轉為大寫
    3. 統一各種 dash 字元為標準 hyphen (-)
    4. 移除 dash 周圍的空格
    5. 移除多餘空格

    Args:
        item_no: 原始 Item No.

    Returns:
        正規化後的 Item No.

    Examples:
        >>> normalize_item_no("DLX-201 .1")
        'DLX-201.1'
        >>> normalize_item_no("  dlx–100  ")
        'DLX-100'
    """
    if item_no is None:
        return ""

    result = item_no.strip()

    if not result:
        return ""

    # 轉為大寫
    result = result.upper()

    # 統一各種 dash 字元為標準 hyphen
    result = DASH_PATTERN.sub("-", result)

    # 移除 dash 周圍的空格
    result = SPACE_AROUND_DASH_PATTERN.sub("-", result)

    # 移除點號前的空格 (如 "DLX-201 .1" → "DLX-201.1")
    result = re.sub(r"\s+\.", ".", result)

    # 移除多餘空格
    result = MULTIPLE_SPACES_PATTERN.sub(" ", result)

    return result.strip()


def is_fabric_item(item_no: str) -> bool:
    """判斷是否為面料項目 (500 系列)

    Args:
        item_no: Item No.

    Returns:
        True 如果是 500 系列面料

    Examples:
        >>> is_fabric_item("500-001")
        True
        >>> is_fabric_item("DLX-100")
        False
    """
    if not item_no:
        return False

    normalized = normalize_item_no(item_no)

    # 500 系列開頭
    return normalized.startswith("50") and normalized[2:3].isdigit()


def extract_base_item_no(item_no: str) -> str:
    """提取基礎編號 (去除子編號)

    Args:
        item_no: 完整 Item No.

    Returns:
        基礎編號

    Examples:
        >>> extract_base_item_no("DLX-100.1")
        'DLX-100'
        >>> extract_base_item_no("ABC-200A")
        'ABC-200'
    """
    if not item_no:
        return ""

    normalized = normalize_item_no(item_no)

    # 移除 .N 子編號
    if "." in normalized:
        normalized = normalized.split(".")[0]

    # 移除尾部字母 (如 A, B, C)
    match = re.match(r"^([A-Z]+-\d+)", normalized)
    if match:
        return match.group(1)

    return normalized


def fuzzy_match_item_no(item_no_a: str, item_no_b: str) -> bool:
    """模糊比對兩個 Item No. 是否相同

    用於 FR-017: Item No. 不一致時的備援匹配

    Args:
        item_no_a: 第一個 Item No.
        item_no_b: 第二個 Item No.

    Returns:
        True 如果兩者匹配
    """
    base_a = extract_base_item_no(item_no_a)
    base_b = extract_base_item_no(item_no_b)

    return base_a == base_b
