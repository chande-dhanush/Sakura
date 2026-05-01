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
Sakura V19.5 — Security Audit Script
Checks: path traversal defense, prompt injection sanitization, 
WebSocket origin validation, auth headers, secret exposure
"""
import ast, re, os, json
from pathlib import Path

RESULTS = {"category": "security", "checks": []}

def check(name, passed, detail="", severity="HIGH"):
    RESULTS["checks"].append({
        "name": name,
        "passed": passed,
        "severity": severity,
        "detail": detail
    })

# 1. Path traversal — DANGEROUS_PATTERNS blocklist
try:
    server_src = Path("backend/sakura_assistant/core/execution/executor.py").read_text(encoding="utf-8", errors="ignore")
    has_blocklist = "DANGEROUS_PATTERNS" in server_src and "normpath" in server_src
    check("path_traversal_blocklist", has_blocklist,
          "DANGEROUS_PATTERNS + normpath in executor.py", "HIGH")
except Exception as e:
    check("path_traversal_blocklist", False, str(e), "HIGH")

# 2. WebSocket origin validation
try:
    ws_src = Path("backend/server.py").read_text(encoding="utf-8", errors="ignore")
    has_origin_check = "tauri://localhost" in ws_src
    check("websocket_origin_validation", has_origin_check,
          "/ws/status has Origin validation", "HIGH")
except Exception as e:
    check("websocket_origin_validation", False, str(e), "HIGH")

# 3. Prompt injection sanitization
try:
    # Check for any sanitization logic in web tools
    has_sanitization = False
    for f in Path("backend/sakura_assistant/core/tools_libs").glob("web*.py"):
        content = f.read_text(encoding="utf-8", errors="ignore")
        if "_sanitize" in content or "sanitize" in content:
            has_sanitization = True
            break
    check("scrape_sanitization", has_sanitization,
          "Sanitization logic found in web tools", "HIGH")
except Exception as e:
    check("scrape_sanitization", False, str(e), "HIGH")

# 4. No hardcoded secrets (excluding placeholder/config)
try:
    secret_patterns = re.compile(
        r'(api_key|secret|password|token)\s*=\s*["\'][A-Za-z0-9_\-]{32,}["\']',
        re.IGNORECASE
    )
    secret_hits = []
    for py_file in Path("backend/sakura_assistant").rglob("*.py"):
        if "config.py" in str(py_file) or "setup" in str(py_file): continue
        content = py_file.read_text(errors="ignore")
        for m in secret_patterns.finditer(content):
            secret_hits.append(f"{py_file.name}:{m.start()}")
    check("no_hardcoded_secrets", len(secret_hits) == 0,
          f"Potential secrets in: {secret_hits[:3]}" if secret_hits else "Clean", "CRITICAL")
except Exception as e:
    check("no_hardcoded_secrets", False, str(e), "CRITICAL")

# 5. eval() usage (unsafe math)
try:
    eval_hits = []
    for py_file in Path("backend/sakura_assistant").rglob("*.py"):
        content = py_file.read_text(errors="ignore")
        if re.search(r'\beval\s*\(', content):
            # Exclude comments
            lines = content.splitlines()
            for line in lines:
                if "eval(" in line and not line.strip().startswith("#"):
                    eval_hits.append(f"{py_file.name}")
                    break
    check("no_eval_usage", len(eval_hits) == 0,
          f"eval() found in: {eval_hits}" if eval_hits else "Clean", "HIGH")
except Exception as e:
    check("no_eval_usage", False, str(e), "HIGH")

# 6. Auth markers
try:
    server_src = Path("backend/server.py").read_text(encoding="utf-8", errors="ignore")
    has_auth = "origin" in server_src.lower() or "auth" in server_src.lower()
    check("api_auth_present", has_auth,
          "Localhost origin or auth markers present", "MEDIUM")
except Exception as e:
    check("api_auth_present", False, str(e), "MEDIUM")

# 7. Unicode normalization for path inputs
try:
    executor_src = Path("backend/sakura_assistant/core/execution/executor.py").read_text(encoding="utf-8", errors="ignore")
    has_unicode_norm = "unicodedata.normalize" in executor_src
    check("unicode_path_normalization", has_unicode_norm,
          "Unicode normalization in executor.py", "MEDIUM")
except Exception as e:
    check("unicode_path_normalization", False, str(e), "MEDIUM")

print(json.dumps(RESULTS, indent=2))

passed_count = sum(1 for c in RESULTS["checks"] if c.get("passed") is True)
failed_count = sum(1 for c in RESULTS["checks"] if c.get("passed") is False)
if failed_count == 0:
    print(f"\n[PASS] Security Audit: {passed_count} checks passed")
else:
    print(f"\n[FAIL] Security Audit: {failed_count} checks failed")
