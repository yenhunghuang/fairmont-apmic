"""
AdapterRegistry - 供應商適配器註冊表

負責：
- 註冊與管理供應商適配器
- 自動發現內建適配器
- 從 YAML 配置載入適配器
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import SupplierAdapter


class AdapterRegistry:
    """
    供應商適配器註冊表

    管理所有已註冊的適配器，支援：
    - 手動註冊適配器
    - 自動發現內建適配器
    - 設定預設適配器
    """

    def __init__(self, config_dir: Path | None = None):
        """
        初始化註冊表

        Args:
            config_dir: 供應商配置目錄 (configs/suppliers/)
        """
        self._adapters: dict[str, SupplierAdapter] = {}
        self._default_id: str | None = None
        self._config_dir = config_dir

    def register(self, adapter: "SupplierAdapter") -> None:
        """
        註冊適配器

        Args:
            adapter: 實作 SupplierAdapter 的適配器實例
        """
        self._adapters[adapter.supplier_id] = adapter

    def get(self, supplier_id: str) -> "SupplierAdapter":
        """
        取得指定供應商的適配器

        Args:
            supplier_id: 供應商識別符

        Returns:
            SupplierAdapter: 適配器實例

        Raises:
            KeyError: 找不到指定的適配器
        """
        if supplier_id not in self._adapters:
            raise KeyError(f"找不到供應商適配器: {supplier_id}")
        return self._adapters[supplier_id]

    def get_or_default(self, supplier_id: str | None = None) -> "SupplierAdapter":
        """
        取得指定或預設的適配器

        Args:
            supplier_id: 供應商識別符 (可選)

        Returns:
            SupplierAdapter: 適配器實例
        """
        if supplier_id:
            return self.get(supplier_id)
        return self.get_default()

    def get_default(self) -> "SupplierAdapter":
        """
        取得預設適配器

        Returns:
            SupplierAdapter: 預設適配器

        Raises:
            ValueError: 未設定預設適配器
        """
        if not self._default_id:
            raise ValueError("未設定預設適配器")
        return self.get(self._default_id)

    def set_default(self, supplier_id: str) -> None:
        """
        設定預設適配器

        Args:
            supplier_id: 供應商識別符
        """
        if supplier_id not in self._adapters:
            raise KeyError(f"無法設定預設: 找不到供應商適配器 {supplier_id}")
        self._default_id = supplier_id

    def list_adapters(self) -> list[str]:
        """
        列出所有已註冊的適配器 ID

        Returns:
            list[str]: 適配器 ID 列表
        """
        return list(self._adapters.keys())

    def has(self, supplier_id: str) -> bool:
        """
        檢查適配器是否已註冊

        Args:
            supplier_id: 供應商識別符

        Returns:
            bool: 是否已註冊
        """
        return supplier_id in self._adapters

    def auto_discover(self, llm_client=None) -> None:
        """
        自動發現並註冊內建適配器

        Args:
            llm_client: LLM 客戶端 (GenericAdapter 需要)
        """
        from .fairmont import FairmontAdapter
        from .generic import GenericAdapter

        # 註冊 Fairmont 適配器
        if not self.has("fairmont"):
            self.register(FairmontAdapter())

        # 註冊 Generic 適配器
        if not self.has("_generic") and llm_client is not None:
            self.register(GenericAdapter(llm_client=llm_client))

        # 設定預設適配器
        if not self._default_id and self.has("fairmont"):
            self.set_default("fairmont")

    def clear(self) -> None:
        """清除所有已註冊的適配器"""
        self._adapters.clear()
        self._default_id = None


# 全域註冊表實例
_global_registry: AdapterRegistry | None = None


def get_registry() -> AdapterRegistry:
    """
    取得全域註冊表實例

    Returns:
        AdapterRegistry: 全域註冊表
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = AdapterRegistry()
    return _global_registry


def init_registry(config_dir: Path | None = None, llm_client=None) -> AdapterRegistry:
    """
    初始化全域註冊表

    Args:
        config_dir: 供應商配置目錄
        llm_client: LLM 客戶端

    Returns:
        AdapterRegistry: 初始化後的註冊表
    """
    global _global_registry
    _global_registry = AdapterRegistry(config_dir=config_dir)
    _global_registry.auto_discover(llm_client=llm_client)
    return _global_registry
