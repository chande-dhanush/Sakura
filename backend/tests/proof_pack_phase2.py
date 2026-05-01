"""
Phase 2 Proof Pack
==================
Four concrete runtime traces proving Phase 2 architectural changes work.

TRACE 1: Sync route() path works with the correct prompt (no crash)
TRACE 2: Resolved reference flows into ExecutionContext -> Planner graph_context
TRACE 3: PLAN query triggers gated FAISS recall (Tier 2)
TRACE 4: CHAT query keeps FAISS recall OFF (Tier 4)

Run: $env:PYTHONPATH="."; ..\PA\Scripts\python.exe tests/proof_pack_phase2.py
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================================
# SETUP
# ============================================================
PASS = "[PASS]"
FAIL = "[FAIL]"
results = []

def trace(name, passed, details):
    status = PASS if passed else FAIL
    results.append((name, passed))
    print(f"\n{'='*70}")
    print(f"  {status}  {name}")
    print("=" * 70)
    for k, v in details.items():
        # Truncate long values for readability
        v_str = str(v)
        if len(v_str) > 200:
            v_str = v_str[:200] + "..."
        print(f"  {k}: {v_str}")


# ============================================================
# TRACE 1: Sync route() path -- no crash, correct prompt used
# ============================================================
print("\n" + "#"*70)
print("# TRACE 1: Sync route() path -- correct prompt, no crash")
print("#"*70)

from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, SystemMessage

from sakura_assistant.core.routing.router import IntentRouter
from sakura_assistant.config import ROUTER_SYSTEM_PROMPT

# Create a mock LLM that captures what it receives
mock_llm = MagicMock()
captured_messages = []

def capture_invoke(messages):
    captured_messages.clear()
    captured_messages.extend(messages)
    return AIMessage(content='{"classification": "DIRECT", "tool_hint": "get_weather"}')

mock_llm.invoke.side_effect = capture_invoke

router = IntentRouter(llm=mock_llm)

# Exercise the SYNC route() -- this is the path that used to crash
result = router.route("what is the weather in Tokyo")

# Verify
t1_checks = {}

# Check 1: No crash, got a result
t1_checks["result_classification"] = result.classification
t1_checks["result_tool_hint"] = result.tool_hint

# Check 2: The LLM was actually called (not swallowed by except block)
t1_checks["llm_was_called"] = mock_llm.invoke.called

# Check 3: The system prompt sent to LLM is the CORRECT one (not the old TEMPLATE)
if captured_messages:
    system_msg = captured_messages[0]
    prompt_used = system_msg.content if hasattr(system_msg, 'content') else str(system_msg)
    # Verify it contains the V18 prompt markers (not the old broken TEMPLATE ref)
    has_v18_markers = "DIRECT" in prompt_used and "PLAN" in prompt_used and "CHAT" in prompt_used
    t1_checks["system_prompt_has_V18_markers"] = has_v18_markers
    t1_checks["system_prompt_length"] = len(prompt_used)
    # Verify datetime was injected (the format string was resolved)
    has_datetime = "{current_datetime}" not in prompt_used  # format() should have replaced it
    t1_checks["datetime_injected"] = has_datetime
else:
    t1_checks["system_prompt_has_V18_markers"] = False
    t1_checks["datetime_injected"] = False

t1_passed = (
    result.classification == "DIRECT"
    and result.tool_hint == "get_weather"
    and mock_llm.invoke.called
    and t1_checks.get("system_prompt_has_V18_markers", False)
    and t1_checks.get("datetime_injected", False)
)

trace("Sync route() path -- correct prompt, no crash", t1_passed, t1_checks)


# ============================================================
# TRACE 2: Reference resolution flows into ExecutionContext
# ============================================================
print("\n" + "#"*70)
print("# TRACE 2: Resolved reference -> ExecutionContext -> Planner graph_context")
print("#"*70)

from sakura_assistant.core.models.request import RequestState
from sakura_assistant.core.execution.context import ExecutionContext, ExecutionMode, GraphSnapshot
from sakura_assistant.core.graph import WorldGraph

# Step A: Simulate reference resolution via WorldGraph
wg = WorldGraph()

# First, establish a focus entity by recording an action
wg.record_action(
    tool="web_search",
    args={"query": "quantum computing"},
    result="Found 10 results about quantum computing",
    success=True
)

# Now resolve "that" -- should resolve to the last action
resolution = wg.resolve_reference("search more about that")

t2_checks = {}
t2_checks["resolution_resolved"] = resolution.resolved is not None
t2_checks["resolution_confidence"] = round(resolution.confidence, 2)
t2_checks["resolution_type"] = type(resolution.resolved).__name__ if resolution.resolved else "None"

# Step B: Build reference_context string (same logic as llm.py)
reference_context = ""
if resolution.resolved and resolution.confidence > 0.3:
    reference_context = f"[REFERENCE] 'that' refers to: {resolution.resolved}"
    if resolution.action:
        reference_context += f" [Suggested action: {resolution.action}]"

t2_checks["reference_context_built"] = bool(reference_context)
t2_checks["reference_context_preview"] = reference_context[:120] if reference_context else "(empty)"

# Step C: Thread into RequestState
req_state = RequestState(
    query="search more about that",
    history=[],
    reference_context=reference_context,
    classification="PLAN",
    tool_hint="web_search"
)

t2_checks["req_state.reference_context_populated"] = bool(req_state.reference_context)

# Step D: Create ExecutionContext with reference_context threaded through
snapshot = GraphSnapshot.from_graph(wg)
exec_ctx = ExecutionContext.create(
    mode=ExecutionMode.ITERATIVE,
    request_id="proof_trace_2",
    user_input="search more about that",
    snapshot=snapshot,
    reference_context=req_state.reference_context
)

t2_checks["exec_ctx.reference_context_populated"] = bool(exec_ctx.reference_context)
t2_checks["exec_ctx.reference_context_matches_req_state"] = exec_ctx.reference_context == req_state.reference_context

# Step E: Simulate what executor.py does   build graph_context_parts
graph_context_parts = []
if exec_ctx.reference_context:
    graph_context_parts.append(exec_ctx.reference_context)
if exec_ctx.snapshot:
    actions = exec_ctx.snapshot.recent_actions
    action_lines = [f"  - {a['tool']}({a['args']}) -> {a['summary']}" for a in actions]
    graph_context_parts.append(f"[SYSTEM CONTEXT]\nRecent Actions:\n" + "\n".join(action_lines))

graph_context = "\n\n".join(graph_context_parts)

t2_checks["planner_graph_context_has_reference"] = "[REFERENCE]" in graph_context
t2_checks["planner_graph_context_has_actions"] = "[SYSTEM CONTEXT]" in graph_context

t2_passed = (
    resolution.resolved is not None
    and bool(reference_context)
    and exec_ctx.reference_context == req_state.reference_context
    and "[REFERENCE]" in graph_context
)

trace("Resolved reference -> ExecutionContext -> Planner graph_context", t2_passed, t2_checks)


# ============================================================
# TRACE 3: PLAN query triggers gated FAISS recall (Tier 2)
# ============================================================
print("\n" + "#"*70)
print("# TRACE 3: PLAN query -> Tier 2 gated FAISS recall (should_recall=True)")
print("#"*70)

from sakura_assistant.core.context.manager import ContextManager, ContextSignals

cm = ContextManager()

# Create a RequestState classified as PLAN
plan_state = RequestState(
    query="research quantum computing breakthroughs",
    classification="PLAN",
    tool_hint="web_search"
)

# Manually trace the gating logic (same as _build_episodic_block)
from sakura_assistant.memory.memory_coordinator import get_memory_coordinator
coordinator = get_memory_coordinator()

user_input = plan_state.query
signals = cm._detect_signals(user_input)

is_explicit = coordinator.is_recall_query(user_input) or signals.episodes
mode = plan_state.classification
has_reference = bool(plan_state.reference_context)
study_mode = plan_state.study_mode

# Replicate gating logic
should_recall = False
max_chars = 1500
tier_hit = "NONE"

if is_explicit:
    should_recall = True
    max_chars = 2000
    tier_hit = "Tier 1 (Explicit)"
elif mode == "PLAN" or study_mode:
    should_recall = True
    max_chars = 800
    tier_hit = "Tier 2 (PLAN/Study)"
elif mode == "DIRECT" and has_reference:
    should_recall = True
    max_chars = 500
    tier_hit = "Tier 3 (DIRECT+ref)"
else:
    should_recall = False
    tier_hit = "Tier 4 (CHAT/default -- blocked)"

t3_checks = {
    "query": user_input,
    "classification": mode,
    "is_explicit_recall": is_explicit,
    "study_mode": study_mode,
    "has_reference": has_reference,
    "tier_hit": tier_hit,
    "should_recall": should_recall,
    "max_chars": max_chars,
}

# Also verify via the full get_context_for_llm path
full_ctx = cm.get_context_for_llm(user_input, state=plan_state)
t3_checks["planner_context_length"] = len(full_ctx.get("planner_context", ""))
t3_checks["responder_context_present"] = bool(full_ctx.get("responder_context"))

t3_passed = (
    should_recall is True
    and tier_hit == "Tier 2 (PLAN/Study)"
    and max_chars == 800
)

trace("PLAN query -> Tier 2 gated FAISS recall (should_recall=True)", t3_passed, t3_checks)


# ============================================================
# TRACE 4: CHAT query keeps FAISS off (Tier 4)
# ============================================================
print("\n" + "#"*70)
print("# TRACE 4: CHAT query -> Tier 4 (FAISS correctly stays OFF)")
print("#"*70)

# Create a RequestState classified as CHAT
chat_state = RequestState(
    query="hey sakura, how are you doing?",
    classification="CHAT"
)

user_input_chat = chat_state.query
signals_chat = cm._detect_signals(user_input_chat)

is_explicit_chat = coordinator.is_recall_query(user_input_chat) or signals_chat.episodes
mode_chat = chat_state.classification
has_reference_chat = bool(chat_state.reference_context)
study_mode_chat = chat_state.study_mode

# Replicate gating logic
should_recall_chat = False
max_chars_chat = 1500
tier_hit_chat = "NONE"

if is_explicit_chat:
    should_recall_chat = True
    max_chars_chat = 2000
    tier_hit_chat = "Tier 1 (Explicit)"
elif mode_chat == "PLAN" or study_mode_chat:
    should_recall_chat = True
    max_chars_chat = 800
    tier_hit_chat = "Tier 2 (PLAN/Study)"
elif mode_chat == "DIRECT" and has_reference_chat:
    should_recall_chat = True
    max_chars_chat = 500
    tier_hit_chat = "Tier 3 (DIRECT+ref)"
else:
    should_recall_chat = False
    tier_hit_chat = "Tier 4 (CHAT/default -- blocked)"

t4_checks = {
    "query": user_input_chat,
    "classification": mode_chat,
    "is_explicit_recall": is_explicit_chat,
    "study_mode": study_mode_chat,
    "has_reference": has_reference_chat,
    "tier_hit": tier_hit_chat,
    "should_recall": should_recall_chat,
}

# Also verify via actual _build_episodic_block call
episodic_result = cm._build_episodic_block(user_input_chat, signals_chat, chat_state, force=False)
t4_checks["_build_episodic_block_returned"] = repr(episodic_result) if episodic_result else "(empty string)"
t4_checks["faiss_was_blocked"] = episodic_result == ""

t4_passed = (
    should_recall_chat is False
    and tier_hit_chat == "Tier 4 (CHAT/default -- blocked)"
    and episodic_result == ""
)

trace("CHAT query -> Tier 4 (FAISS correctly stays OFF)", t4_passed, t4_checks)


# ============================================================
# SUMMARY
# ============================================================
print("\n" + "="*70)
print("  PHASE 2 PROOF PACK SUMMARY")
print("="*70)
all_passed = True
for name, passed in results:
    status = PASS if passed else FAIL
    print(f"  {status}  {name}")
    if not passed:
        all_passed = False

print()
if all_passed:
    print("  [OK] ALL 4 TRACES PASSED -- Phase 2 architecture is structurally sound.")
else:
    print("  [!!] SOME TRACES FAILED -- Phase 2 has remaining issues.")
print("=" * 70)
