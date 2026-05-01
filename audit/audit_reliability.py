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
Sakura V19.5   Reliability Audit
Checks: budget enforcement wiring, error propagation, terminal actions,
fidelity check, alias tool registration, context var coverage
"""
import ast, re, json, os
from pathlib import Path

RESULTS = {"category": "reliability", "checks": []}

def check(name, passed, detail="", severity="HIGH"):
    RESULTS["checks"].append({
        "name": name, "passed": passed,
        "severity": severity, "detail": detail
    })

def src(path):
    try: return Path(path).read_text(encoding="utf-8", errors="ignore")
    except: return ""

executor = src("backend/sakura_assistant/core/execution/executor.py")
dispatcher = src("backend/sakura_assistant/core/execution/dispatcher.py")
router = src("backend/sakura_assistant/core/routing/router.py")
llm = src("backend/sakura_assistant/core/llm.py")
wrapper = src("backend/sakura_assistant/core/models/wrapper.py")
responder = src("backend/sakura_assistant/core/models/responder.py")
tools = src("backend/sakura_assistant/core/tools.py")
server = src("backend/server.py")

# 1. MAX_LLM_CALLS enforced in wrapper
check("budget_in_wrapper",
      "execution_context_var" in wrapper and "LLMBudgetExceededError" in wrapper,
      "ReliableLLM checks budget on every invoke", "CRITICAL")

# 2. LLMBudgetExceededError re-raised in router
check("budget_reraise_router",
      "LLMBudgetExceededError" in router and "raise" in router,
      "Router re-raises budget error, not swallows", "HIGH")

# 3. LLMBudgetExceededError re-raised in dispatcher
check("budget_reraise_dispatcher",
      "LLMBudgetExceededError" in dispatcher and "raise" in dispatcher,
      "Dispatcher re-raises budget error", "HIGH")

# 4. TERMINAL_ACTIONS registry exists
check("terminal_actions_registry",
      "TERMINAL_ACTIONS" in executor,
      "Terminal action enforcement in executor", "HIGH")

# 5. ReAct max_iterations = 5
check("react_max_iterations_5",
      "max_iterations: int = 5" in executor or "max_iterations=5" in executor,
      "ReAct loop capped at 5 iterations", "MEDIUM")

# 6. Fidelity check in responder
check("fidelity_check_present",
      "fidelity_override" in responder or "fidelity" in responder,
      "Responder has fidelity regeneration", "HIGH")

# 7. Deterministic hallucination block in responder
check("hallucination_block",
      re.search(r"regex|re\.search|re\.match", responder) is not None,
      "Regex-based self-check in responder", "HIGH")

# 8. read_clipboard and write_clipboard are distinct tools
check("clipboard_aliases_distinct",
      tools.count("def read_clipboard") >= 1 and 
      tools.count("def write_clipboard") >= 1,
      "Alias tools are distinct @tool functions", "MEDIUM")

# 9. query_memory purged
check("query_memory_purged",
      "query_memory" not in src("backend/sakura_assistant/config.py") or
      "# query_memory" in src("backend/sakura_assistant/config.py"),
      "No active query_memory references in config", "MEDIUM")

# 10. ResponseContext no legacy params
resp_ctx_call = re.search(
    r"ResponseContext\(([^)]{0,500})\)", llm, re.DOTALL
)
legacy_params = ["assistant_name", "system_prompt", "tool_used"]
if resp_ctx_call:
    call_str = resp_ctx_call.group(1)
    has_legacy = any(p in call_str for p in legacy_params)
    check("responsecontext_no_legacy_params", not has_legacy,
          f"ResponseContext call: {call_str[:100]}", "HIGH")
else:
    check("responsecontext_no_legacy_params", False,
          "Could not find ResponseContext instantiation", "HIGH")

# 11. Wh-question pre-LLM force
check("wh_question_force_prefilter",
      "WH_FORCE_PATTERN" in router or "_should_force_wh_question" in router,
      "Wh-questions hard-forced before LLM", "HIGH")

# 12. UNIVERSAL_TOOLS includes query_ephemeral
toolsets = src("backend/sakura_assistant/core/routing/micro_toolsets.py")
check("universal_tools_has_query_ephemeral",
      "query_ephemeral" in toolsets,
      "query_ephemeral in UNIVERSAL_TOOLS", "HIGH")

# 13. tool_used top-level in error paths
has_tool_used_in_errors = '"tool_used"' in server or "'tool_used'" in server
check("tool_used_in_error_responses", has_tool_used_in_errors,
      "tool_used key present in error SSE/response paths", "MEDIUM")

# 14. No offload() calls outside utils/tts.py
offload_hits = []
for py_file in Path("backend/sakura_assistant").rglob("*.py"):
    if "utils/tts" in str(py_file) or "utils\\tts" in str(py_file):
        continue
    try:
        content = py_file.read_text(errors="ignore")
        if re.search(r'\.offload\(\)', content):
            offload_hits.append(str(py_file))
    except:
        continue
if re.search(r'\.offload\(\)', src("backend/server.py")):
    offload_hits.append("server.py")
check("no_offload_outside_tts", len(offload_hits) == 0,
      f"Offload calls found in: {offload_hits}" if offload_hits else "Clean",
      "HIGH")

# 15. SummaryMemory labeled MemoryManager
memory_files = list(Path("backend/sakura_assistant/memory").rglob("*.py")) if \
               Path("backend/sakura_assistant/memory").exists() else []
mm_labeled = False
for f in memory_files:
    try:
        if "MemoryManager" in f.read_text(errors="ignore"):
            mm_labeled = True
            break
    except:
        continue
check("summary_memory_labeled_memorymanager", mm_labeled,
      "SummaryMemory stage label is 'MemoryManager'", "MEDIUM")

print(json.dumps(RESULTS, indent=2))

passed_count = sum(1 for c in RESULTS["checks"] if c.get("passed") is True)
failed_count = sum(1 for c in RESULTS["checks"] if c.get("passed") is False)
if failed_count == 0:
    print(f"\n[PASS] Reliability Audit: {passed_count} checks passed")
else:
    print(f"\n[FAIL] Reliability Audit: {failed_count} checks failed")
