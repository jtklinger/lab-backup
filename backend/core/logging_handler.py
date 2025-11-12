"""
Custom logging handler for storing logs in memory for web UI access.
"""
import logging
from collections import deque
from datetime import datetime
from threading import Lock
from typing import List, Dict, Any


class InMemoryLogHandler(logging.Handler):
    """
    Custom log handler that stores recent log entries in memory.
    Thread-safe circular buffer with a maximum size.
    """

    def __init__(self, max_records: int = 1000):
        """
        Initialize the in-memory log handler.

        Args:
            max_records: Maximum number of log records to keep in memory
        """
        super().__init__()
        self.max_records = max_records
        self.records = deque(maxlen=max_records)
        self.lock = Lock()

    def emit(self, record: logging.LogRecord):
        """
        Store a log record in memory.

        Args:
            record: LogRecord to store
        """
        try:
            # Format the record
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
                "module": record.module,
                "funcName": record.funcName,
                "lineno": record.lineno,
                "pathname": record.pathname,
            }

            # Add exception info if present
            if record.exc_info:
                log_entry["exception"] = self.formatter.formatException(record.exc_info) if self.formatter else str(record.exc_info)

            with self.lock:
                self.records.append(log_entry)

        except Exception:
            self.handleError(record)

    def get_logs(
        self,
        level: str = None,
        logger: str = None,
        search: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get filtered log entries.

        Args:
            level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            logger: Filter by logger name (partial match)
            search: Search in log messages (case-insensitive)
            limit: Maximum number of records to return
            offset: Number of records to skip from the end

        Returns:
            List of log entry dictionaries
        """
        with self.lock:
            # Convert deque to list for easier manipulation
            logs = list(self.records)

        # Apply filters
        if level:
            logs = [log for log in logs if log["level"] == level.upper()]

        if logger:
            logs = [log for log in logs if logger.lower() in log["logger"].lower()]

        if search:
            search_lower = search.lower()
            logs = [log for log in logs if search_lower in log["message"].lower()]

        # Reverse to show newest first
        logs.reverse()

        # Apply offset and limit
        start = offset
        end = offset + limit
        return logs[start:end]

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about stored logs.

        Returns:
            Dictionary with log statistics
        """
        with self.lock:
            logs = list(self.records)

        level_counts = {
            "DEBUG": 0,
            "INFO": 0,
            "WARNING": 0,
            "ERROR": 0,
            "CRITICAL": 0,
        }

        for log in logs:
            level = log["level"]
            if level in level_counts:
                level_counts[level] += 1

        return {
            "total": len(logs),
            "max_records": self.max_records,
            "by_level": level_counts,
        }

    def clear(self):
        """Clear all stored log records."""
        with self.lock:
            self.records.clear()


# Global instance
_log_handler = None


def get_log_handler() -> InMemoryLogHandler:
    """Get the global in-memory log handler instance."""
    global _log_handler
    if _log_handler is None:
        _log_handler = InMemoryLogHandler(max_records=2000)
        # Set a formatter
        formatter = logging.Formatter(
            '%(levelname)s - %(name)s - %(message)s'
        )
        _log_handler.setFormatter(formatter)
    return _log_handler


def setup_logging():
    """Setup application logging with in-memory handler."""
    log_handler = get_log_handler()

    # IMPORTANT: Do NOT modify root logger or uvicorn logger
    # Modifying these interferes with uvicorn's SSL socket binding
    # Only add handler to application-specific loggers

    # Add to backend logger (our application code)
    loggers_configured = []
    for logger_name in ['backend', 'sqlalchemy', 'fastapi']:
        logger = logging.getLogger(logger_name)
        if log_handler not in logger.handlers:
            logger.addHandler(log_handler)
            # Set level to INFO for our loggers
            if logger.level == logging.NOTSET:
                logger.setLevel(logging.INFO)
            loggers_configured.append(logger_name)

    print(f"✅ Logging handler attached to: {', '.join(loggers_configured) if loggers_configured else 'none (already configured)'}", flush=True)
