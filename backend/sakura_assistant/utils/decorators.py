"""
Sakura V9: Utility Decorators
=============================

Standardized decorators for common patterns across the codebase.
"""
from functools import wraps


def safe_tool(func):
    """
    Standardized error handling for tool execution.
    Catches exceptions, logs tracebacks, and returns user-friendly error strings.
    
    Usage:
        @tool
        @safe_tool
        def my_tool(arg: str) -> str:
            # No need for try/except - decorator handles it
            return do_something(arg)
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Print full error to console for debugging
            print(f"❌ [TOOL ERROR] in {func.__name__}: {e}")
            # Return safe string to LLM
            return f"❌ Tool '{func.__name__}' failed: {str(e)}"
    return wrapper
