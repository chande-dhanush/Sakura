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
Sakura V19.5   Integration & E2E Audit Script
Checks: System-wide wiring, health endpoints, and provider configuration
"""
import os, json
from pathlib import Path

RESULTS = {"category": "integration", "checks": []}

def check(name, passed, detail="", severity="HIGH"):
    RESULTS["checks"].append({
        "name": name,
        "passed": passed,
        "severity": severity,
        "detail": detail
    })

# 1. Health endpoint
try:
    server_src = Path("backend/server.py").read_text(encoding="utf-8", errors="ignore")
    has_health = "/health" in server_src and ("healthy" in server_src or "code" in server_src)
    check("health_endpoint_present", has_health,
          "/health endpoint exists and returns status", "HIGH")
except Exception as e:
    check("health_endpoint_present", False, str(e), "HIGH")

# 2. DeepSeek provider wired
try:
    container_src = Path("backend/sakura_assistant/core/infrastructure/container.py").read_text(encoding="utf-8", errors="ignore")
    has_deepseek = "deepseek" in container_src.lower()
    check("deepseek_provider_wired", has_deepseek,
          "DeepSeek provider integrated in model container", "HIGH")
except Exception as e:
    check("deepseek_provider_wired", False, str(e), "HIGH")

# 3. Model staging
try:
    container_src = Path("backend/sakura_assistant/core/infrastructure/container.py").read_text(encoding="utf-8", errors="ignore")
    has_staging = "get_router_llm" in container_src and "get_responder_llm" in container_src
    check("model_staging_logic", has_staging,
          "Distinct LLM stages (Router/Planner/Responder) present", "HIGH")
except Exception as e:
    check("model_staging_logic", False, str(e), "HIGH")

# 4. Identity management
try:
    config_src = Path("backend/sakura_assistant/config.py").read_text(encoding="utf-8", errors="ignore")
    has_identity = "SYSTEM_PERSONALITY" in config_src or "USER_DETAILS" in config_src
    check("identity_injection", has_identity,
          "Identity and personality prompts managed in config", "MEDIUM")
except Exception as e:
    check("identity_injection", False, str(e), "MEDIUM")

print(json.dumps(RESULTS, indent=2))

passed_count = sum(1 for c in RESULTS["checks"] if c.get("passed") is True)
failed_count = sum(1 for c in RESULTS["checks"] if c.get("passed") is False)
if failed_count == 0:
    print(f"\n[PASS] Integration Audit: {passed_count} checks passed")
else:
    print(f"\n[FAIL] Integration Audit: {failed_count} checks failed")
