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
from typing import Optional

try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    print("⚠️ structlog not installed - using basic logging")


def configure_logging(json_output: bool = False, level: str = "INFO"):
    """
    Configure structured logging for the application.
    
    Args:
        json_output: If True, output JSON (for production). If False, console format.
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    if not STRUCTLOG_AVAILABLE:
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
