# Sakura Fix Log

## Phase 1: Immediate Stabilization — Stop the Bleeding
**Date:** 2026-04-14
**Operator:** Antigravity (Principal Engineer Mode)

### Phase Goal
Fix three confirmed runtime-critical bugs that compromise Sakura's routing, memory continuity, and autonomy at the foundation level.

---

### Issues Fixed

#### BUG-01: Router Argument Mismatch (CRITICAL CRASH)
- **Root Cause:** `llm.py:248` called `aroute(user_input, history, study_mode_active)` but the `aroute` signature is `(query, context, history)`. This put `history` (List) into the `context` (str) parameter and `study_mode_active` (bool) into the `history` (List) parameter.
- **Failure Mode:** When `study_mode_active=True` and router tried `history[-3:]`, Python raised `TypeError: 'bool' object is not subscriptable`. Any query with educational keywords ("explain", "teach me") could crash.
- **Fix Applied:** Switched to keyword arguments: `aroute(query=user_input, history=history)`. Removed `study_mode_active` from the router call entirely (the router never uses it — study mode is correctly used downstream in `ResponseContext`).
- **Files Changed:** `core/llm.py` (lines 235-280)
- **Verified:** ✅ 7 passing tests including regression test proving `bool[-3:]` crashes

#### BUG-02: Reference Resolution Ghosting (GHOST FEATURE)
- **Root Cause:** `llm.py:239` called `self.world_graph.resolve_reference(user_input)` but discarded the return value. The `ResolutionResult` was computed (with entity/action resolution, confidence scores, ban flags) then thrown away before reaching any LLM context.
- **Failure Mode:** Follow-up queries like "that file", "play it again", "the meeting" never benefited from WorldGraph reference resolution. The system could resolve internally but the LLM never saw the result.
- **Fix Applied:** Captured `ResolutionResult`, formatted it into a structured `[REFERENCE RESOLVED]` context block with entity/action info, confidence, and ban flags. Injected into `responder_context` between mood prompt and graph context so the LLM sees it just before the response generation.
- **Files Changed:** `core/llm.py` (lines 237-268, 330-337)
- **Verified:** ✅ 6 passing tests covering entity resolution, action resolution, empty resolution, ban flags, and context injection positioning

#### BUG-03: Scheduler Import Path Silent Death (SILENT FAILURE)
- **Root Cause:** `scheduler.py:759,771,669` used `from .cognitive.desire` and `from .cognitive.proactive` (relative to `infrastructure/`). But `cognitive/` is a sibling of `infrastructure/` under `core/`, not a child. The correct path is `from ..cognitive.*`.
- **Failure Mode:** `ImportError` silently swallowed by try/except. The desire hourly tick and proactive check never ran. Loneliness never increased, social battery never recharged, proactive messages never fired from the scheduler.
- **Fix Applied:** Changed all three imports from `from .cognitive.*` to `from ..cognitive.*`. Split the blanket `except Exception` into separate `except ImportError` (loud failure) and `except Exception` (operational failure) handlers. Added import verification at schedule time to fail-loud during startup.
- **Files Changed:** `core/infrastructure/scheduler.py` (lines 669, 759, 771, 813-823)
- **Verified:** ✅ 5 passing import and initialization tests + runtime import verification

---

### Files Changed
| File | Change Summary |
|------|---------------|
| `core/llm.py` | V19-FIX-01: Keyword args for router. V19-FIX-02: Capture + inject reference resolution. Hot-path diagnostics via FlightRecorder. |
| `core/infrastructure/scheduler.py` | V19-FIX-03: Fixed 3 broken relative imports `.cognitive` → `..cognitive`. Added import verification at schedule time. Split error handlers. |
| `tests/test_phase1_stabilization.py` | NEW: 21 tests covering all three bug fixes plus integration paths. |

### Tests Run
| Test Suite | Result |
|-----------|--------|
| `test_phase1_stabilization.py` | **21/21 passed** ✅ |
| `test_router.py` | 19/20 passed (1 pre-existing failure: stale fallback assumption) |
| `test_router_fallback.py` | 9/9 passed ✅ |
| `test_router_safety.py` | 17/17 passed ✅ |
| `test_world_graph.py` | 14/19 passed (5 pre-existing: IdentityManager config dependency) |

### Outcome
All three critical bugs are **FIXED and VERIFIED**. No regressions introduced by these changes. All pre-existing test failures are documented and unrelated to Phase 1.

### Follow-Up Items
1. **Pre-existing:** `test_router_bias.py` imports `ROUTER_SYSTEM_PROMPT_TEMPLATE` which doesn't exist (should be `ROUTER_SYSTEM_PROMPT` from config). Needs fixing.
2. **Pre-existing:** `test_router.py:test_parse_response_fallback` expects `CHAT` fallback but V18 changed it to `PLAN`. Test needs updating.
3. **Pre-existing:** `test_world_graph.py` tests hardcode "Dhanush" as identity but IdentityManager loads from config files. These tests need fixture setup.
4. **Windows encoding:** `desire.py` uses emoji (⏰) in print statements that fail on Windows cp1252 console. Non-blocking but noisy.
5. **Sync `route()` path:** `router.py:153` references `ROUTER_SYSTEM_PROMPT_TEMPLATE` (undefined). The sync path has a different bug than the async path — it always falls through to the except handler. Should be `ROUTER_SYSTEM_PROMPT`.

## Phase 2: Cognitive Pipeline Stabilization
**Date:** 2026-04-14
**Operator:** Antigravity (Principal Engineer Mode)

### Phase Goal
Unify state handling, wire reference resolution into planning/execution, and implement tiered memory gating.

---

### Issues Fixed

#### 1. Sync Router Path Failure
- **Root Cause:** `router.py:153` referenced `ROUTER_SYSTEM_PROMPT_TEMPLATE` (undefined), causing sync `route()` to always fail and return a fallback value.
- **Fix Applied:** Replaced with `ROUTER_SYSTEM_PROMPT`.

#### 2. RequestState Inversion
- **Root Cause:** Pipeline relied on positional arguments and scattered context building.
- **Fix Applied:** Introduced `RequestState` as the single source of truth for every turn. Threaded through `llm.py`, `Router`, and `Executor`.

#### 3. Tiered Memory Gating
- **Root Cause:** FAISS semantic recall was potentially unconditional or noisy.
- **Fix Applied:** Implemented 4-Tier policy in `ContextManager`. Semantic recall now strictly gated (e.g., CHAT queries block FAISS by default).

#### 4. Reference Continuity
- **Root Cause:** Resolved references from `WorldGraph` weren't reaching the `ReActLoop` planner.
- **Fix Applied:** Threaded `reference_context` through `ExecutionContext` into `ExecutionPlan`.

---

## Phase 3: Version Truth & Contract Hardening
**Date:** 2026-04-14
**Operator:** Antigravity (Principal Engineer Mode)

### Phase Goal
Align system identity to V19.0, harden data contracts, and prune dead dependencies.

---

### Issues Fixed

#### 1. Version Drift
- **Root Cause:** Version markers varied between V10 and V18.
- **Fix Applied:** Introduced canonical `sakura_assistant/version.py`. Updated `server.py`, health endpoint, and top-level doc headers to V19.0.

#### 2. Soft Data Contracts
- **Root Cause:** `RequestState` and `ResponseContext` were loose dataclasses.
- **Fix Applied:** Added `__slots__` and `__post_init__` validation for critical fields. Hardened `RouteResult` to prevent invalid classification propagation.

#### 3. Stale Test Fixtures
- **Root Cause:** `test_world_graph.py` relied on hardcoded "Dhanush" strings and default identity.
- **Fix Applied:** Implemented JSON fixtures and pytest mock-identity injection.

#### 4. Dependency Rot
- **Root Cause:** `requirements.txt` contained unused packages (e.g., `prometheus_client`, `plyer`).
- **Fix Applied:** Performed comprehensive usage audit. Removed 5 verified-dead packages.

### Outcome
Sakura V19.0 is now structurally honest, contract-hardened, and deployment-ready.

### Follow-Up Items
1. **Confidence Gating:** Implement true threshold-based routing in `dispatcher.py` (Currently heuristic only).
2. **Behavioral Impact:** Wire Desire system state deeper into tool selection and timing.
3. **Multi-monitor mapping:** Fix monitor index mapping in `read_screen` tool.

## Phase 4: Responder Pipeline & Context Synchronization
**Date:** 2026-04-28
**Operator:** Antigravity (Principal Engineer Mode)

### Phase Goal
Resolve `ResponseContext` dataclass instantiation crashes during the response generation phase caused by schema drift from recent refactoring.

---

### Issues Fixed

#### 1. ResponseContext Signature Drift (CRITICAL CRASH)
- **Root Cause:** `ResponseContext` was refactored in `models/responder.py` to remove `assistant_name`, `system_prompt`, and `tool_used`, while renaming fields like `mood_prompt` to `intent_adjustment`. The calling site in `llm.py:410` was never updated to match this new signature.
- **Failure Mode:** Any execution reaching the Responder phase triggered `TypeError: ResponseContext.__init__() got an unexpected keyword argument 'assistant_name'`, halting final response synthesis.
- **Fix Applied:** Updated the `ResponseContext(...)` instantiation in `llm.py` to perfectly map to the new dataclass fields.

#### 2. Ephemeral RAG "data_reasoning" Dropped (SILENT FAILURE)
- **Root Cause:** The `has_ephemeral` flag, triggered when massive text output falls into Ephemeral RAG, was correctly calculated in `llm.py` but never passed into the `ResponseContext` constructor.
- **Failure Mode:** `data_reasoning` remained False incorrectly. The LLM would ignore the "data reasoning" prompt instructions, causing it to hallucinate or summarize poorly on massive data queries instead of applying analytical judgment.
- **Fix Applied:** Mapped `data_reasoning=has_ephemeral` directly into the `ResponseContext` instantiation.

#### 3. Identity Disconnection
- **Root Cause:** With `assistant_name` stripped from the ResponseContext constructor, any custom renamed identity (e.g., `sakura_name="Bob"`) loaded from user settings was silently discarded before reaching the responder system prompt.
- **Fix Applied:** Injected the `sakura_name` dynamically into `base_personality` directly inside `llm.py` prior to assigning it to the `ResponseGenerator`, preserving user-defined assistant identity logic structurally without cluttering the context dataclasses.

### Outcome
The Responder phase is fully synchronized with V19 dataclass schemas.

## Phase 5: Execution Stability & Tool Hardening
**Date:** 2026-04-29
**Operator:** Antigravity (Principal Engineer Mode)

### Phase Goal
Resolve "ghosting" tool failures where specific actions (like clipboard reading) were misrouted or entered infinite loops, and harden structured error reporting.

---

### Issues Fixed

#### 1. Clipboard Routing Regression
- **Root Cause:** `router.py` misclassified "read my clipboard" as `PLAN` due to aggressive reference triggers ("my ") and a tool name mismatch (`read_clipboard` vs registry `clipboard_read`).
- **Failure Mode:** User requests for clipboard data either went to a generic memory search (hallucinating "I found no memory of that") or failed with `ToolNotFound`.
- **Fix Applied:** 
    - Updated `router.py` to explicitly detect "clipboard" and "read" keywords as action verbs.
    - Added an exception to reference triggers: "my clipboard" is now allowed to bypass the Planner and go `DIRECT`.
    - Corrected the tool mapping to `clipboard_read`.
- **Verified:** ✅ `test_router.py` passes. End-to-end trace confirms `DIRECT` route for "read my clipboard".

#### 2. ReAct Loop Terminal Action Hallucination
- **Root Cause:** `clipboard_read` was not marked as a terminal action in `ExecutionPolicy`.
- **Failure Mode:** The Planner would successfully read the clipboard, but because it wasn't terminal, it would generate a "Next Step" to read it again, entering a 3-iteration loop that consumed the entire LLM budget.
- **Fix Applied:** Added `clipboard_read` and `clipboard_write` (and their aliases) to `TERMINAL_ACTIONS` in `executor.py`.
- **Verified:** ✅ Loop now terminates immediately after the first successful clipboard read.

#### 3. Silent Budget Degradation (mode="unknown")
- **Root Cause:** When `LLMBudgetExceededError` was raised, the exception handler in `llm.py` returned a dictionary without `tool_used` or `tools_used` metadata, and sometimes failed to resolve the `mode`.
- **Failure Mode:** Downstream audit scripts and UI components reported `mode="unknown"`, making it impossible to diagnose why a request failed.
- **Fix Applied:** 
    - Hardened the exception blocks in `llm.py` to return consistent metadata (`tool_used="None"`, `tools_used=[]`, `execution_status="failed"`).
    - Fixed `ReActLoop.arun` to return `status=FAILED` if the budget is hit before any tool succeeds.
- **Verified:** ✅ Audit traces now show clear `failed` status with accurate mode labels during budget hits.

#### 4. Tool Registry Alias Resilience
- **Root Cause:** The Planner frequently hallucinated `read_clipboard` (snake_case) while the registry only had `clipboard_read`.
- **Fix Applied:** Added explicit aliases `read_clipboard` and `write_clipboard` to `tools.py` as first-class tool exports.
- **Verified:** ✅ ToolRunner now resolves both naming conventions successfully.

---

### Outcome
Sakura V19.2 is now resilient to common naming hallucinations and correctly handles system-level direct actions without budget-draining loops.
