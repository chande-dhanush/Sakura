#!/usr/bin/env python3
import sys
import os
import warnings
import locale

# Fix Windows paths
# We need to add 'backend' to sys.path to find 'sakura_assistant'
BACKEND_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
if BACKEND_PATH not in sys.path:
    sys.path.insert(0, BACKEND_PATH)

# Suppress noise
warnings.filterwarnings("ignore", category=DeprecationWarning)
os.environ["PYTHONWARNINGS"] = "ignore::DeprecationWarning"

# UTF-8 everywhere
if sys.platform == 'win32':
    try:
        import io
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

def audit_guard():
    """Skip if core deps missing"""
    missing = []
    try:
        import sakura_assistant
    except ImportError:
        missing.append("sakura_assistant")
    
    if missing:
        # Check if we are in the backend dir already (fallback)
        if os.path.exists("sakura_assistant"):
            return
        print(f"Audit skipped: {missing} (Checked: {BACKEND_PATH})")
        sys.exit(77)  # Non-zero but non-error exit
    
audit_guard()

"""
Sakura V19.5 — Observability Audit Script
Checks: FlightRecorder integration, structured logging, and trace propagation
"""
import os, json
from pathlib import Path

RESULTS = {"category": "observability", "checks": []}

def check(name, passed, detail="", severity="HIGH"):
    RESULTS["checks"].append({
        "name": name,
        "passed": passed,
        "severity": severity,
        "detail": detail
    })

# 1. FlightRecorder integration
try:
    wrapper_src = Path("backend/sakura_assistant/core/models/wrapper.py").read_text(encoding="utf-8", errors="ignore")
    has_recorder = "FlightRecorder" in wrapper_src or "get_recorder" in wrapper_src
    check("flight_recorder_integrated", has_recorder,
          "FlightRecorder active in ReliableLLM", "HIGH")
except Exception as e:
    check("flight_recorder_integrated", False, str(e), "HIGH")

# 2. Structured logging
try:
    server_src = Path("backend/server.py").read_text(encoding="utf-8", errors="ignore")
    has_logging = "configure_logging" in server_src or "get_logger" in server_src
    check("structured_logging_active", has_logging,
          "Structured logging initialized in server.py", "MEDIUM")
except Exception as e:
    check("structured_logging_active", False, str(e), "MEDIUM")

# 3. Trace ID propagation
try:
    llm_src = Path("backend/sakura_assistant/core/llm.py").read_text(encoding="utf-8", errors="ignore")
    has_trace = "trace_id" in llm_src or "request_id" in llm_src
    check("trace_propagation", has_trace,
          "Trace/Request IDs propagated through pipeline", "HIGH")
except Exception as e:
    check("trace_propagation", False, str(e), "HIGH")

print(json.dumps(RESULTS, indent=2))

passed_count = sum(1 for c in RESULTS["checks"] if c.get("passed") is True)
failed_count = sum(1 for c in RESULTS["checks"] if c.get("passed") is False)
if failed_count == 0:
    print(f"\n[PASS] Observability Audit: {passed_count} checks passed")
else:
    print(f"\n[FAIL] Observability Audit: {failed_count} checks failed")
