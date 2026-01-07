"""
多供應商適配器模組

提供 SupplierAdapter 介面與各供應商實作，支援：
- FairmontAdapter: Fairmont (惠而蒙) 專用適配器
- GenericAdapter: LLM 動態判斷適配器 (兜底)
"""

from .base import FileRole, SupplierAdapter
from .registry import AdapterRegistry

__all__ = [
    "SupplierAdapter",
    "FileRole",
    "AdapterRegistry",
]
