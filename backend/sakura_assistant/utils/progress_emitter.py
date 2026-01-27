"""
V17.5: Progress Emitter for Real-Time Tool Streaming
=====================================================
Provides a centralized way for tools to send progress updates to the frontend
via SSE streaming.

Usage:
    from sakura_assistant.utils.progress_emitter import get_progress_emitter
    
    emitter = get_progress_emitter()
    emitter.emit("Tool:web_search", "PROGRESS", "🔍 Searching web...")
    emitter.emit("Tool:web_search", "SUCCESS", "✅ Found 5 results")
"""

import time
from typing import Optional, Dict, Any, Callable
from contextlib import contextmanager


class ProgressEmitter:
    """
    Centralized utility for tools to emit progress updates.
    
    Progress events flow:
    1. Tool calls emitter.emit()
    2. Emitter logs to FlightRecorder (for persistence)
    3. FlightRecorder callback pushes to SSE queue (if registered)
    4. Frontend receives real-time updates
    """
    
    _instance = None
    
    def __init__(self):
        self._enabled = True
        self._trace_id: Optional[str] = None
        self._callback: Optional[Callable] = None
    
    @classmethod
    def get_instance(cls) -> "ProgressEmitter":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def set_trace_id(self, trace_id: str):
        """Set current trace ID for event routing."""
        self._trace_id = trace_id
    
    def set_enabled(self, enabled: bool):
        """Enable/disable progress emission (e.g., for non-streaming contexts)."""
        self._enabled = enabled
    
    def set_callback(self, callback: Optional[Callable]):
        """Set callback for direct SSE push (bypasses FlightRecorder)."""
        self._callback = callback
    
    def emit(
        self,
        stage: str,
        status: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Emit a progress event.
        
        Args:
            stage: Component reporting progress (e.g., "Tool:web_search", "Executor")
            status: Event type - "PROGRESS", "INFO", "WARNING", "SUCCESS", "ERROR"
            message: Human-readable status message (e.g., "🔍 Searching...")
            metadata: Optional dict with extra data (e.g., {"result_count": 5})
        """
        if not self._enabled:
            return
        
        event = {
            "event": "progress",
            "trace_id": self._trace_id,
            "stage": stage,
            "status": status,
            "message": message,
            "timestamp": time.time(),
            "metadata": metadata or {}
        }
        
        # Log to FlightRecorder (for persistence and SSE callback)
        try:
            from .flight_recorder import get_recorder
            recorder = get_recorder()
            
            # Use span with progress metadata
            recorder.span(
                stage=stage,
                content=message,
                status=status,
                metadata={
                    "type": "progress",
                    **(metadata or {})
                }
            )
        except Exception as e:
            print(f"⚠️ [ProgressEmitter] FlightRecorder log failed: {e}")
        
        # Also call direct callback if set (for SSE bypass)
        if self._callback:
            try:
                self._callback(event)
            except Exception as e:
                print(f"⚠️ [ProgressEmitter] Callback failed: {e}")
        
        # Console output for debugging
        status_icons = {
            "PROGRESS": "⏳",
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "SUCCESS": "✅",
            "ERROR": "❌"
        }
        icon = status_icons.get(status, "📡")
        print(f"{icon} [Progress] {stage}: {message}")
    
    @contextmanager
    def context(self, stage: str):
        """
        Context manager for wrapping tool execution.
        
        Usage:
            with emitter.context("Tool:web_search"):
                results = do_search()
        
        Automatically emits ERROR if exception occurs.
        """
        start_time = time.time()
        try:
            yield self
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.emit(
                stage=stage,
                status="ERROR",
                message=f"❌ Failed: {str(e)[:100]}",
                metadata={"duration_ms": duration_ms, "error": str(e)}
            )
            raise
    
    def tool_start(self, tool_name: str, args: Optional[Dict] = None):
        """Convenience: Emit tool start event."""
        args_preview = str(args)[:50] if args else ""
        self.emit(
            stage=f"Tool:{tool_name}",
            status="PROGRESS",
            message=f"🔧 Executing {tool_name}..." + (f" ({args_preview}...)" if args_preview else ""),
            metadata={"tool": tool_name, "args": args}
        )
    
    def tool_progress(self, tool_name: str, message: str, metadata: Optional[Dict] = None):
        """Convenience: Emit tool progress update."""
        self.emit(
            stage=f"Tool:{tool_name}",
            status="PROGRESS",
            message=message,
            metadata=metadata
        )
    
    def tool_success(self, tool_name: str, message: str, metadata: Optional[Dict] = None):
        """Convenience: Emit tool success event."""
        self.emit(
            stage=f"Tool:{tool_name}",
            status="SUCCESS",
            message=message,
            metadata=metadata
        )
    
    def tool_error(self, tool_name: str, error: str, metadata: Optional[Dict] = None):
        """Convenience: Emit tool error event."""
        self.emit(
            stage=f"Tool:{tool_name}",
            status="ERROR",
            message=f"❌ {error}",
            metadata={"error": error, **(metadata or {})}
        )


def get_progress_emitter() -> ProgressEmitter:
    """Get the global ProgressEmitter singleton."""
    return ProgressEmitter.get_instance()


# Optional: Enable/disable via config
def configure_progress_emitter(enabled: bool = True):
    """Enable or disable progress emission globally."""
    get_progress_emitter().set_enabled(enabled)
