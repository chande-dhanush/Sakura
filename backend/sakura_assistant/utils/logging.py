"""
Sakura V10 Structured Logging
=============================
Enterprise-grade logging with structured output.

Usage:
    from sakura_assistant.utils.logging import get_logger
    
    log = get_logger("module_name")
    log.info("user_query", query="hello", user_id="123")
"""
import sys
import os
from datetime import datetime, timedelta
from typing import Optional

try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    print("[WARN] structlog not installed - using basic logging")


def get_log_dir() -> str:
    """Get the logs directory path, creating if needed."""
    try:
        from .pathing import get_project_root
        log_dir = os.path.join(get_project_root(), "data", "logs")
    except ImportError:
        log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "logs")
    
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def cleanup_old_logs(max_days: int = 3):
    """Delete log files older than max_days."""
    log_dir = get_log_dir()
    cutoff = datetime.now() - timedelta(days=max_days)
    
    try:
        for filename in os.listdir(log_dir):
            if not filename.endswith(".log"):
                continue
            filepath = os.path.join(log_dir, filename)
            # Extract date from filename (sakura_YYYY-MM-DD.log)
            try:
                date_part = filename.replace("sakura_", "").replace(".log", "")
                file_date = datetime.strptime(date_part, "%Y-%m-%d")
                if file_date < cutoff:
                    os.remove(filepath)
                    print(f"[LOG] Deleted old log: {filename}")
            except (ValueError, OSError):
                continue
    except Exception as e:
        print(f"[WARN] Log cleanup failed: {e}")


def configure_logging(json_output: bool = False, level: str = "INFO"):
    """
    Configure structured logging for the application.
    
    Args:
        json_output: If True, output JSON (for production). If False, console format.
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    # Cleanup old logs on startup
    cleanup_old_logs(max_days=3)
    
    if not STRUCTLOG_AVAILABLE:
        # Configure basic file logging
        import logging
        log_dir = get_log_dir()
        log_file = os.path.join(log_dir, f"sakura_{datetime.now().strftime('%Y-%m-%d')}.log")
        
        logging.basicConfig(
            level=getattr(logging, level),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(log_file, encoding="utf-8")
            ]
        )
        return
    
    # Determine if we're in production
    is_production = os.getenv("SAKURA_ENV", "development") == "production"
    use_json = json_output or is_production
    
    # Configure processors
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    
    if use_json:
        # Production: JSON output
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: Colored console output
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    
    structlog.configure(
        processors=shared_processors + [
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Also configure file logging for structlog
    import logging
    log_dir = get_log_dir()
    log_file = os.path.join(log_dir, f"sakura_{datetime.now().strftime('%Y-%m-%d')}.log")
    
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(getattr(logging, level))
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    
    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)


def get_logger(name: str = "sakura"):
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (usually module name)
        
    Returns:
        Structured logger that can be used like:
            log.info("event_name", key1="value1", key2="value2")
    """
    if STRUCTLOG_AVAILABLE:
        return structlog.get_logger(name)
    else:
        # Fallback to basic print logging
        return BasicLogger(name)


class BasicLogger:
    """Fallback logger when structlog is not available."""
    
    def __init__(self, name: str):
        self.name = name
    
    def _log(self, level: str, event: str, **kwargs):
        extras = " ".join(f"{k}={v}" for k, v in kwargs.items())
        print(f"[{level}] [{self.name}] {event} {extras}")
    
    def debug(self, event: str, **kwargs):
        self._log("DEBUG", event, **kwargs)
    
    def info(self, event: str, **kwargs):
        self._log("INFO", event, **kwargs)
    
    def warning(self, event: str, **kwargs):
        self._log("WARN", event, **kwargs)
    
    def error(self, event: str, **kwargs):
        self._log("ERROR", event, **kwargs)
    
    def exception(self, event: str, **kwargs):
        self._log("ERROR", event, **kwargs)
        import traceback
        traceback.print_exc()


# Initialize logging on import
configure_logging()

