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


# V13: Model cost lookup (per 1M tokens)
MODEL_COSTS = {
    # Groq (free tier, but track for awareness)
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "llama3-8b-8192": {"input": 0.05, "output": 0.10},
    "gemma2-9b-it": {"input": 0.20, "output": 0.20},
    "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
    "OpenAI/OSS20b": {"input": 0.05, "output": 0.10},
    "OpenAI/OSS20b": {"input": 0.1, "output": 0.50},
    # OpenRouter / Others
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    # Default fallback
    "default": {"input": 0.50, "output": 1.00},
}


class FlightRecorder:
    """
    Structured tracing for the Sakura pipeline.
    
    Usage:
        recorder.start_trace("query text")
        recorder.log("Router", "Classified as DIRECT")
        recorder.log_llm_call("Responder", model="llama-3.3-70b", tokens={"prompt": 500, "completion": 200})
        recorder.end_trace()
    """
    
    def __init__(self):
        self.log_path = DATA_DIR / "flight_recorder.jsonl"
        self.trace_id: Optional[str] = None
        self.trace_start: float = 0
        self.spans: list = []
        self.callback = None  # V10.4: SSE bridge
        
        # V13: Token/Cost tracking per trace
        self.trace_tokens = {"prompt": 0, "completion": 0, "total": 0}
        self.trace_cost_usd = 0.0
        self.trace_llm_calls = 0
        self.trace_models_used = set()
        
    def set_callback(self, callback):
        """Set a real-time callback for SSE events."""
        self.callback = callback

        
    def start_trace(self, query: str) -> str:
        """Start a new trace for a request."""
        self.trace_id = f"trace_{int(time.time() * 1000)}"
        self.trace_start = time.perf_counter()
        self.spans = []
        
        # V13: Reset token accumulators
        self.trace_tokens = {"prompt": 0, "completion": 0, "total": 0}
        self.trace_cost_usd = 0.0
        self.trace_llm_calls = 0
        self.trace_models_used = set()
        
        self._write({
            "event": "trace_start",
            "trace_id": self.trace_id,
            "query": query[:200],  # Truncate long queries
            "timestamp": datetime.now().isoformat(),
        })
        
        return self.trace_id
    
    def log(self, stage: str, content: str, status: str = "INFO", 
            duration_ms: Optional[float] = None, metadata: Optional[Dict] = None):
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
            
        if metadata:
            entry["metadata"] = metadata
        
        self._write(entry)
        self.spans.append(entry)
        
        # Also print to console for immediate feedback
        status_icon = {"INFO": ".", "SUCCESS": "+", "ERROR": "!", "WARN": "?"}
        print(f"[{status_icon.get(status, '.')}] {stage}: {content[:60]}... ({elapsed:.0f}ms)")
    
    def log_llm_call(self, stage: str, model: str = "unknown", 
                     tokens: Optional[Dict[str, int]] = None,
                     duration_ms: Optional[float] = None,
                     success: bool = True):
        """
        V13: Log an LLM API call with token usage and cost calculation.
        
        Args:
            stage: Pipeline stage (Router, Planner, Responder, etc.)
            model: Model identifier (e.g., "llama-3.3-70b-versatile")
            tokens: Dict with "prompt", "completion", "total" keys
            duration_ms: Time taken for this LLM call
            success: Whether the call succeeded
        """
        # Default tokens if not provided
        if tokens is None:
            tokens = {"prompt": 0, "completion": 0, "total": 0}
        
        # Calculate cost
        costs = MODEL_COSTS.get(model, MODEL_COSTS["default"])
        prompt_cost = (tokens.get("prompt", 0) / 1_000_000) * costs["input"]
        completion_cost = (tokens.get("completion", 0) / 1_000_000) * costs["output"]
        call_cost = prompt_cost + completion_cost
        
        # Accumulate
        self.trace_tokens["prompt"] += tokens.get("prompt", 0)
        self.trace_tokens["completion"] += tokens.get("completion", 0)
        self.trace_tokens["total"] += tokens.get("total", tokens.get("prompt", 0) + tokens.get("completion", 0))
        self.trace_cost_usd += call_cost
        self.trace_llm_calls += 1
        self.trace_models_used.add(model)
        
        # Log as span with metadata
        self.log(
            stage=stage,
            content=f"LLM Call: {model} ({tokens.get('total', 0)} tokens, ${call_cost:.6f})",
            status="SUCCESS" if success else "ERROR",
            duration_ms=duration_ms,
            metadata={
                "type": "llm_call",
                "model": model,
                "tokens": tokens,
                "cost_usd": round(call_cost, 6),
            }
        )
    
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
            # V13: Token/Cost summary
            "tokens": self.trace_tokens.copy(),
            "cost_usd": round(self.trace_cost_usd, 6),
            "llm_calls": self.trace_llm_calls,
            "models_used": list(self.trace_models_used),
        })
        
        print(f"[=] TRACE COMPLETE: {total_ms:.0f}ms, {len(self.spans)} spans, {self.trace_tokens['total']} tokens, ${self.trace_cost_usd:.4f}")
        
        self.trace_id = None
        self.spans = []
        
        # V10.5: Auto-rotate old logs
        self._rotate_if_needed()
    
    def _rotate_if_needed(self):
        """Remove logs older than 7 days."""
        if not self.log_path.exists():
            return
        
        try:
            from datetime import timedelta
            cutoff = datetime.now() - timedelta(days=7)
            
            # Read all lines
            with open(self.log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Filter to recent logs
            recent_lines = []
            for line in lines:
                try:
                    entry = json.loads(line)
                    ts = entry.get('timestamp', '')
                    if ts:
                        entry_time = datetime.fromisoformat(ts)
                        if entry_time >= cutoff:
                            recent_lines.append(line)
                    else:
                        # Keep entries without timestamp (they're part of recent traces)
                        recent_lines.append(line)
                except (json.JSONDecodeError, ValueError):
                    continue
            
            # Only rewrite if we actually removed something
            if len(recent_lines) < len(lines):
                with open(self.log_path, 'w', encoding='utf-8') as f:
                    f.writelines(recent_lines)
                print(f"[*] Flight recorder rotated: {len(lines)} -> {len(recent_lines)} lines")
        except Exception as e:
            print(f"[!] Log rotation failed: {e}")
    
    def get_logs_for_api(self, limit: int = 100) -> dict:
        """
        Optimized log parser for API endpoint.
        Returns structured data ready for frontend consumption.
        """
        if not self.log_path.exists():
            return {"traces": [], "stats": {"total_queries": 0, "success_rate": 100, "avg_latency_s": 0}}
        
        traces = {}
        
        try:
            # Read file (optimized: reverse iteration not needed for stitching)
            with open(self.log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        tid = entry.get('trace_id')
                        if not tid:
                            continue
                        
                        if tid not in traces:
                            traces[tid] = {
                                'id': tid,
                                'date': '',
                                'time': '',
                                'query': '',
                                'response': '',
                                'total_ms': 0,
                                'success': True,
                                'phases': {'Router': [], 'Executor': [], 'Responder': []},
                                'error': None
                            }
                        
                        t = traces[tid]
                        event_type = entry.get('event')
                        
                        if event_type == 'trace_start':
                            t['query'] = entry.get('query', '')
                            ts = entry.get('timestamp', '')
                            try:
                                dt = datetime.fromisoformat(ts)
                                t['date'] = dt.strftime('%Y-%m-%d')
                                t['time'] = dt.strftime('%H:%M:%S')
                            except:
                                t['date'] = 'Unknown'
                                t['time'] = ts[11:19] if len(ts) > 19 else '??:??'
                        
                        elif event_type == 'trace_end':
                            t['total_ms'] = entry.get('total_ms', 0)
                            t['success'] = entry.get('success', True)
                            t['response'] = entry.get('response_preview', '')
                        
                        elif event_type == 'span':
                            stage = entry.get('stage', 'Other')
                            span_data = {
                                'elapsed_s': round(entry.get('elapsed_ms', 0) / 1000, 2),
                                'content': entry.get('content', ''),
                                'status': entry.get('status', 'INFO'),
                                'duration_s': round(entry.get('duration_ms', 0) / 1000, 2) if entry.get('duration_ms') else None,
                                'metadata': entry.get('metadata')
                            }
                            
                            if stage in t['phases']:
                                t['phases'][stage].append(span_data)
                            else:
                                if 'Other' not in t['phases']:
                                    t['phases']['Other'] = []
                                t['phases']['Other'].append(span_data)
                            
                            # Capture first error
                            if entry.get('status') == 'ERROR' and not t['error']:
                                t['error'] = entry.get('content', 'Unknown error')
                    
                    except json.JSONDecodeError:
                        continue
            
            # Convert to list, sort by date/time (newest first), limit
            result = [t for t in traces.values() if t['date']]
            result.sort(key=lambda x: f"{x['date']} {x['time']}", reverse=True)
            result = result[:limit]
            
            # Calculate stats
            total = len(result)
            success = sum(1 for t in result if t['success'])
            avg_latency = sum(t['total_ms'] for t in result) / total if total else 0
            
            return {
                "traces": result,
                "stats": {
                    "total_queries": total,
                    "success_rate": round((success / total) * 100, 1) if total else 100,
                    "avg_latency_s": round(avg_latency / 1000, 2)
                }
            }
        
        except Exception as e:
            print(f"[!] get_logs_for_api failed: {e}")
            return {"traces": [], "stats": {"total_queries": 0, "success_rate": 100, "avg_latency_s": 0}}
    
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


def log_llm_call(stage: str, model: str = "unknown", tokens: dict = None,
                 duration_ms: float = None, success: bool = True):
    """V13: Log an LLM API call with token/cost tracking."""
    return get_recorder().log_llm_call(stage, model, tokens, duration_ms, success)
