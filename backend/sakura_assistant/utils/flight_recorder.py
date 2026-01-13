"""
Sakura V10.4: Flight Recorder
=============================
Live observability layer for debugging latency and pipeline issues.

Writes structured JSONL to data/flight_recorder.jsonl
Each request gets a unique trace_id for correlation.
"""
import json
import time
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from contextlib import contextmanager

# Get project root
try:
    from ..config import get_project_root
    DATA_DIR = Path(get_project_root()) / "data"
except ImportError:
    DATA_DIR = Path(__file__).parent.parent.parent / "data"

DATA_DIR.mkdir(exist_ok=True)


class FlightRecorder:
    """
    Structured tracing for the Sakura pipeline.
    
    Usage:
        recorder.start_trace("query text")
        recorder.log("Router", "Classified as DIRECT")
        recorder.log("Tool:spotify", "Playing Neon Blade")
        recorder.end_trace()
    """
    
    def __init__(self):
        self.log_path = DATA_DIR / "flight_recorder.jsonl"
        self.trace_id: Optional[str] = None
        self.trace_start: float = 0
        self.spans: list = []
        self.callback = None  # V10.4: SSE bridge
        
    def set_callback(self, callback):
        """Set a real-time callback for SSE events."""
        self.callback = callback
        
    def start_trace(self, query: str) -> str:
        """Start a new trace for a request."""
        self.trace_id = f"trace_{int(time.time() * 1000)}"
        self.trace_start = time.perf_counter()
        self.spans = []
        
        self._write({
            "event": "trace_start",
            "trace_id": self.trace_id,
            "query": query[:200],  # Truncate long queries
            "timestamp": datetime.now().isoformat(),
        })
        
        return self.trace_id
    
    def log(self, stage: str, content: str, status: str = "INFO", 
            duration_ms: Optional[float] = None):
        """Log an event within the current trace."""
        elapsed = (time.perf_counter() - self.trace_start) * 1000
        
        entry = {
            "event": "span",
            "trace_id": self.trace_id,
            "stage": stage,
            "status": status,
            "content": content[:500],  # Truncate long content
            "elapsed_ms": round(elapsed, 2),
        }
        
        if duration_ms is not None:
            entry["duration_ms"] = round(duration_ms, 2)
        
        self._write(entry)
        self.spans.append(entry)
        
        # Also print to console for immediate feedback
        status_icon = {"INFO": ".", "SUCCESS": "+", "ERROR": "!", "WARN": "?"}
        print(f"[{status_icon.get(status, '.')}] {stage}: {content[:60]}... ({elapsed:.0f}ms)")
    
    def end_trace(self, success: bool = True, response_preview: str = ""):
        """End the current trace."""
        total_ms = (time.perf_counter() - self.trace_start) * 1000
        
        self._write({
            "event": "trace_end",
            "trace_id": self.trace_id,
            "success": success,
            "total_ms": round(total_ms, 2),
            "response_preview": response_preview[:100],
            "span_count": len(self.spans),
        })
        
        print(f"[=] TRACE COMPLETE: {total_ms:.0f}ms total, {len(self.spans)} spans")
        
        self.trace_id = None
        self.spans = []
    
    @contextmanager
    def span(self, stage: str):
        """Context manager for timing a span."""
        start = time.perf_counter()
        try:
            yield
            duration = (time.perf_counter() - start) * 1000
            self.log(stage, "completed", "SUCCESS", duration_ms=duration)
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            self.log(stage, f"error: {e}", "ERROR", duration_ms=duration)
            raise
    
    def _write(self, entry: Dict[str, Any]):
        """Append entry to JSONL file and notify callback."""
        # 1. Write to file
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[!] Flight recorder write failed: {e}")
            
        # 2. Notify callback (SSE)
        if self.callback:
            try:
                self.callback(entry)
            except Exception as e:
                print(f"[!] Flight recorder callback failed: {e}")
    
    def get_recent_traces(self, limit: int = 10) -> list:
        """Get the most recent traces for debugging."""
        traces = []
        
        if not self.log_path.exists():
            return traces
        
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-limit * 10:]  # Read more lines to find complete traces
            
            for line in lines:
                try:
                    entry = json.loads(line)
                    if entry.get("event") == "trace_end":
                        traces.append(entry)
                except json.JSONDecodeError:
                    continue
            
            return traces[-limit:]
        except Exception:
            return []
    
    def get_latency_breakdown(self, trace_id: str) -> Dict[str, float]:
        """Get per-stage latency for a specific trace."""
        breakdown = {}
        
        if not self.log_path.exists():
            return breakdown
        
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("trace_id") == trace_id and entry.get("event") == "span":
                            stage = entry.get("stage", "unknown")
                            duration = entry.get("duration_ms", 0)
                            breakdown[stage] = duration
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        
        return breakdown


# Global singleton
_recorder: Optional[FlightRecorder] = None


def get_recorder() -> FlightRecorder:
    """Get the global flight recorder instance."""
    global _recorder
    if _recorder is None:
        _recorder = FlightRecorder()
    return _recorder


# Convenience exports
def start_trace(query: str) -> str:
    return get_recorder().start_trace(query)


def log(stage: str, content: str, status: str = "INFO", duration_ms: float = None):
    return get_recorder().log(stage, content, status, duration_ms)


def end_trace(success: bool = True, response_preview: str = ""):
    return get_recorder().end_trace(success, response_preview)


def span(stage: str):
    return get_recorder().span(stage)
