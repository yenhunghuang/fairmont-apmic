"""結構化日誌基礎設施 (繁體中文訊息)"""

import logging
import sys
from pathlib import Path
from typing import Any

# 預設日誌格式
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(
    name: str = "fairmont",
    level: str = "INFO",
    log_file: str | None = None,
) -> logging.Logger:
    """設定日誌器"""
    logger = logging.getLogger(name)

    # 避免重複設定
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "fairmont") -> logging.Logger:
    """取得日誌器"""
    return logging.getLogger(name)


class PipelineLogger:
    """管線處理專用日誌器 (繁體中文訊息)"""

    def __init__(self, batch_uuid: str, logger: logging.Logger | None = None):
        self.batch_uuid = batch_uuid
        self.logger = logger or get_logger("fairmont.pipeline")

    def _format_msg(self, msg: str, **kwargs: Any) -> str:
        """格式化訊息"""
        extra = " | ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
        return f"[{self.batch_uuid[:8]}] {msg}" + (f" | {extra}" if extra else "")

    def stage_start(self, stage_name: str, stage_number: int) -> None:
        """記錄階段開始"""
        self.logger.info(self._format_msg(f"階段 {stage_number}/7 開始: {stage_name}"))

    def stage_complete(self, stage_name: str, stage_number: int, duration_ms: int) -> None:
        """記錄階段完成"""
        self.logger.info(
            self._format_msg(
                f"階段 {stage_number}/7 完成: {stage_name}",
                duration_ms=duration_ms,
            )
        )

    def stage_error(self, stage_name: str, stage_number: int, error: str) -> None:
        """記錄階段錯誤"""
        self.logger.error(
            self._format_msg(
                f"階段 {stage_number}/7 失敗: {stage_name}",
                error=error,
            )
        )

    def item_processed(self, item_no: str, status: str) -> None:
        """記錄項目處理"""
        self.logger.debug(self._format_msg(f"項目已處理: {item_no}", status=status))

    def llm_call(self, purpose: str, tokens: int | None = None) -> None:
        """記錄 LLM 呼叫"""
        extra = {"tokens": tokens} if tokens else {}
        self.logger.debug(self._format_msg(f"LLM 呼叫: {purpose}", **extra))

    def cache_hit(self, file_hash: str) -> None:
        """記錄快取命中"""
        self.logger.info(self._format_msg(f"快取命中: {file_hash[:16]}..."))

    def cache_miss(self, file_hash: str) -> None:
        """記錄快取未命中"""
        self.logger.debug(self._format_msg(f"快取未命中: {file_hash[:16]}..."))

    def info(self, msg: str, **kwargs: Any) -> None:
        """一般資訊"""
        self.logger.info(self._format_msg(msg, **kwargs))

    def warning(self, msg: str, **kwargs: Any) -> None:
        """警告"""
        self.logger.warning(self._format_msg(msg, **kwargs))

    def error(self, msg: str, **kwargs: Any) -> None:
        """錯誤"""
        self.logger.error(self._format_msg(msg, **kwargs))

    def debug(self, msg: str, **kwargs: Any) -> None:
        """除錯"""
        self.logger.debug(self._format_msg(msg, **kwargs))
