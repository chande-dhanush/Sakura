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
Sakura V19.5   Performance Audit Script
Checks: caching strategy, rate limiting, and execution timeouts
"""
import os, json
from pathlib import Path

RESULTS = {"category": "performance", "checks": []}

def check(name, passed, detail="", severity="HIGH"):
    RESULTS["checks"].append({
        "name": name,
        "passed": passed,
        "severity": severity,
        "detail": detail
    })

# 1. CACHE_TTL defined in config
try:
    config_src = Path("backend/sakura_assistant/config.py").read_text(encoding="utf-8", errors="ignore")
    has_cache = "CACHE_TTL" in config_src
    check("cache_ttl_active", has_cache,
          "CACHE_TTL defined in config.py", "MEDIUM")
except Exception as e:
    check("cache_ttl_active", False, str(e), "MEDIUM")

# 2. Rate limiting presence
try:
    server_src = Path("backend/server.py").read_text(encoding="utf-8", errors="ignore")
    # Check for rate limiter usage or markers
    has_rate_limit = "rate_limit" in server_src.lower() or "limiter" in server_src.lower()
    check("rate_limiting_present", has_rate_limit,
          "Rate limiting logic/markers in server.py", "HIGH")
except Exception as e:
    check("rate_limiting_present", False, str(e), "HIGH")

# 3. Timeout enforcement
try:
    wrapper_src = Path("backend/sakura_assistant/core/models/wrapper.py").read_text(encoding="utf-8", errors="ignore")
    has_timeout = "LLM_TIMEOUT" in wrapper_src or "timeout" in wrapper_src.lower()
    check("timeout_enforcement", has_timeout,
          "Timeout handling in model wrapper", "HIGH")
except Exception as e:
    check("timeout_enforcement", False, str(e), "HIGH")

# 4. Latency benchmarks (Static check for now)
try:
    container_src = Path("backend/sakura_assistant/core/infrastructure/container.py").read_text(encoding="utf-8", errors="ignore")
    has_planner_limit = "max_planner_iterations" in container_src
    check("planner_iteration_cap", has_planner_limit,
          "Hard cap on planner iterations present", "MEDIUM")
except Exception as e:
    check("planner_iteration_cap", False, str(e), "MEDIUM")

print(json.dumps(RESULTS, indent=2))

passed_count = sum(1 for c in RESULTS["checks"] if c.get("passed") is True)
failed_count = sum(1 for c in RESULTS["checks"] if c.get("passed") is False)
if failed_count == 0:
    print(f"\n[PASS] Performance Audit: {passed_count} checks passed")
else:
    print(f"\n[FAIL] Performance Audit: {failed_count} checks failed")
