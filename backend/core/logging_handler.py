"""
Custom logging handlers for storing logs in memory, database, and files.
"""
import logging
import asyncio
import os
from collections import deque
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import List, Dict, Any, Optional
from queue import Queue
from logging.handlers import RotatingFileHandler as BaseRotatingFileHandler
from pathlib import Path


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


class DatabaseLogHandler(logging.Handler):
    """
    Async log handler that writes logs to the database.
    Uses a queue to avoid blocking the logging thread.
    """

    def __init__(self, queue_size: int = 10000):
        """
        Initialize the database log handler.

        Args:
            queue_size: Maximum size of the log queue
        """
        super().__init__()
        self.queue = Queue(maxsize=queue_size)
        self.worker_thread = None
        self._stop_event = None

    def emit(self, record: logging.LogRecord):
        """
        Queue a log record for async database writing.

        Args:
            record: LogRecord to store
        """
        try:
            # Extract context from record if available
            context = getattr(record, 'context', {})

            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record) if self.formatter else record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line_number": record.lineno,
                "pathname": record.pathname,
                "exception": self.formatter.formatException(record.exc_info) if record.exc_info and self.formatter else None,
                "job_id": context.get('job_id'),
                "backup_id": context.get('backup_id'),
                "user_id": context.get('user_id'),
                "request_id": context.get('request_id'),
            }

            # Try to add to queue (non-blocking)
            try:
                self.queue.put_nowait(log_entry)
            except:
                # Queue is full, drop the log (avoid blocking)
                pass

        except Exception:
            self.handleError(record)

    def start_worker(self):
        """Start the background worker thread that processes the queue."""
        if self.worker_thread is None or not self.worker_thread.is_alive():
            import threading
            self._stop_event = threading.Event()
            self.worker_thread = Thread(target=self._process_queue, daemon=True)
            self.worker_thread.start()
            print("✅ Database log worker thread started", flush=True)

    def stop_worker(self):
        """Stop the background worker thread."""
        if self._stop_event:
            self._stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=5)

    def _process_queue(self):
        """Process log records from queue and write to database."""
        # Import here to avoid circular imports
        from backend.models.base import AsyncSessionLocal
        from backend.models.logs import ApplicationLog

        async def write_logs():
            while not self._stop_event.is_set():
                try:
                    # Get a batch of logs from queue (with timeout)
                    logs_to_write = []
                    try:
                        # Get first log with timeout
                        log_entry = self.queue.get(timeout=1)
                        logs_to_write.append(log_entry)

                        # Try to get more logs (up to 100) without blocking
                        while len(logs_to_write) < 100:
                            try:
                                log_entry = self.queue.get_nowait()
                                logs_to_write.append(log_entry)
                            except:
                                break
                    except:
                        # Timeout or no logs, continue
                        continue

                    # Write batch to database
                    if logs_to_write:
                        async with AsyncSessionLocal() as db:
                            try:
                                for log_data in logs_to_write:
                                    log_record = ApplicationLog(**log_data)
                                    db.add(log_record)
                                await db.commit()
                            except Exception as e:
                                await db.rollback()
                                # Log to stderr (avoid infinite loop)
                                print(f"Error writing logs to database: {e}", flush=True)

                except Exception as e:
                    print(f"Error in log processing loop: {e}", flush=True)

        # Run async event loop in this thread
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(write_logs())
        except Exception as e:
            print(f"Database log worker error: {e}", flush=True)
        finally:
            loop.close()


# Global database handler instance
_db_log_handler = None


def get_db_log_handler() -> DatabaseLogHandler:
    """Get the global database log handler instance."""
    global _db_log_handler
    if _db_log_handler is None:
        _db_log_handler = DatabaseLogHandler(queue_size=10000)
        # Set a simple formatter
        formatter = logging.Formatter('%(message)s')
        _db_log_handler.setFormatter(formatter)
        # Start the worker thread
        _db_log_handler.start_worker()
    return _db_log_handler


def setup_database_logging():
    """Setup database logging handler (can be called independently of in-memory logging)."""
    try:
        db_handler = get_db_log_handler()

        # Only attach to backend logger to avoid SSL issues
        loggers_configured = []
        for logger_name in ['backend']:
            logger = logging.getLogger(logger_name)
            if db_handler not in logger.handlers:
                logger.addHandler(db_handler)
                if logger.level == logging.NOTSET:
                    logger.setLevel(logging.INFO)
                loggers_configured.append(logger_name)

        print(f"✅ Database logging handler attached to: {', '.join(loggers_configured) if loggers_configured else 'none (already configured)'}", flush=True)
        return True
    except Exception as e:
        print(f"⚠️  Failed to setup database logging: {e}", flush=True)
        return False


# Global file handler instance
_file_log_handler = None


def get_file_log_handler(
    log_dir: str = "/var/log/lab-backup",
    max_bytes: int = 100 * 1024 * 1024,  # 100 MB
    backup_count: int = 10
) -> BaseRotatingFileHandler:
    """Get the global file log handler instance."""
    global _file_log_handler
    if _file_log_handler is None:
        # Ensure log directory exists
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # Create rotating file handler
        log_file = log_path / "application.log"
        _file_log_handler = BaseRotatingFileHandler(
            filename=str(log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )

        # Set detailed formatter for file logs
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        _file_log_handler.setFormatter(formatter)

    return _file_log_handler


def setup_file_logging(
    log_dir: str = "/var/log/lab-backup",
    max_bytes: int = 100 * 1024 * 1024,
    backup_count: int = 10
):
    """Setup file logging with rotation."""
    try:
        file_handler = get_file_log_handler(log_dir, max_bytes, backup_count)

        # Attach to backend logger
        loggers_configured = []
        for logger_name in ['backend']:
            logger = logging.getLogger(logger_name)
            if file_handler not in logger.handlers:
                logger.addHandler(file_handler)
                if logger.level == logging.NOTSET:
                    logger.setLevel(logging.INFO)
                loggers_configured.append(logger_name)

        print(f"✅ File logging handler attached to: {', '.join(loggers_configured) if loggers_configured else 'none (already configured)'}", flush=True)
        print(f"   Log directory: {log_dir}", flush=True)
        print(f"   Max file size: {max_bytes / (1024*1024):.1f} MB", flush=True)
        print(f"   Backup count: {backup_count}", flush=True)
        return True
    except Exception as e:
        print(f"⚠️  Failed to setup file logging: {e}", flush=True)
        return False
