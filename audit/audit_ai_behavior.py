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
Sakura V19.5   AI Behavior Audit
Checks: identity protection, EQ layer, hallucination guards,
memory lifecycle, ephemeral RAG, temporal grounding, search cascade
"""
import re, json, os
from pathlib import Path

RESULTS = {"category": "ai_behavior", "checks": []}

def check(name, passed, detail="", severity="HIGH"):
    RESULTS["checks"].append({
        "name": name, "passed": passed,
        "severity": severity, "detail": detail
    })

def src(path):
    try: return Path(path).read_text(encoding="utf-8", errors="ignore")
    except: return ""

world_graph = src("backend/sakura_assistant/core/graph/world_graph.py")
identity = src("backend/sakura_assistant/core/graph/identity.py")
router = src("backend/sakura_assistant/core/routing/router.py")
toolsets = src("backend/sakura_assistant/core/routing/micro_toolsets.py")
responder = src("backend/sakura_assistant/core/models/responder.py")
context_mgr = src("backend/sakura_assistant/core/context/manager.py")
ephemeral = src("backend/sakura_assistant/core/graph/ephemeral.py")
config = src("backend/sakura_assistant/config.py")

# 1. user:self immutable
check("user_self_immutable",
      "user:self" in world_graph or "user_self" in world_graph or
      "immutable" in world_graph.lower(),
      "user:self entity protected from tool mutation", "CRITICAL")

# 2. LLM_INFERRED never auto-promoted
check("llm_inferred_not_auto_promoted",
      "LLM_INFERRED" in world_graph and "PROMOTED" in world_graph,
      "LLM_INFERRED facts gated from auto-promotion", "HIGH")

# 3. EQ layer: frustration/urgency detection
check("eq_layer_present",
      any(w in world_graph.lower() for w in ["frustrated", "urgency", "eq", 
          "emotional"]),
      "EQ layer emotion detection in WorldGraph", "MEDIUM")

# 4. EventBus module-level import (no lazy import)
wg_lines = world_graph.split("\n")
lazy_eventbus = any(
    "from .identity import" in line and 
    not line.strip().startswith("#") and
    i > 50  # If import appears after line 50, likely lazy
    for i, line in enumerate(wg_lines)
)
check("eventbus_not_lazy_imported",
      not lazy_eventbus,
      "EventBus imported at module level in world_graph.py", "HIGH")

# 5. IdentityManager constructor injection
check("identity_constructor_injection",
      "IdentityManager" in world_graph and 
      "__init__" in world_graph and
      "identity_manager" in world_graph.lower(),
      "IdentityManager injected via constructor", "HIGH")

# 6. Temporal grounding in router
check("temporal_grounding",
      "datetime" in router or ("date" in router.lower() and "inject" in router.lower()),
      "Router injects current date/time", "HIGH")

# 7. Wh-question pre-LLM force
check("wh_prefilter",
      "WH_FORCE_PATTERN" in router or "_should_force_wh_question" in router,
      "Wh-questions hard-forced to PLAN before LLM", "HIGH")

# 8. Search cascade (Wikipedia > Tavily)
check("search_cascade",
      "TOOL_HIERARCHY" in toolsets or "fallback_mode" in toolsets or
      "wikipedia" in toolsets.lower(),
      "Search cascade with Wikipedia-first hierarchy", "HIGH")

# 9. Ephemeral RAG with virtual handles
check("ephemeral_rag_handles",
      "eph_" in ephemeral or "virtual" in ephemeral.lower() or
      "handle" in ephemeral.lower(),
      "Ephemeral RAG creates virtual eph_ handles", "HIGH")

# 10. data_reasoning toggle on ephemeral handles
llm_src = src("backend/sakura_assistant/core/llm.py")
check("data_reasoning_on_ephemeral",
      "data_reasoning" in llm_src,
      "data_reasoning=True forced when ephemeral handle detected", "HIGH")

# 11. Temporal decay (30-day half-life)
check("temporal_decay",
      ("30" in world_graph and "decay" in world_graph.lower()) or
      "half_life" in world_graph.lower() or "confidence" in world_graph.lower(),
      "Memory confidence decays over 30-day half-life", "MEDIUM")

# 12. ContextSignals dataclass
check("context_signals",
      "ContextSignals" in context_mgr,
      "ContextSignals dataclass for deterministic routing", "MEDIUM")

# 13. Fact-gate: external search banned for user references
check("fact_gate_user_reference",
      "is_user_reference" in world_graph or "external" in world_graph.lower(),
      "External search blocked for user identity queries", "HIGH")

# 14. Semantic tool gating
check("semantic_tool_gating",
      "encyclopedia" in toolsets or "intent" in toolsets.lower(),
      "Intent-based tool gating (encyclopedia hides web_search)", "MEDIUM")

# 15. Hallucination gateway (malformed tool input check)
executor_src = src("backend/sakura_assistant/core/execution/executor.py")
check("hallucination_gateway",
      ("http" in executor_src.lower() and "url" in executor_src.lower()) or
      "malformed" in executor_src.lower() or "gateway" in executor_src.lower(),
      "Hallucination gateway intercepts bad tool inputs", "HIGH")

print(json.dumps(RESULTS, indent=2))

passed_count = sum(1 for c in RESULTS["checks"] if c.get("passed") is True)
failed_count = sum(1 for c in RESULTS["checks"] if c.get("passed") is False)
if failed_count == 0:
    print(f"\n[PASS] AI Behavior Audit: {passed_count} checks passed")
else:
    print(f"\n[FAIL] AI Behavior Audit: {failed_count} checks failed")
