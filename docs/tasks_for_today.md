# Sakura V17 Implementation Tasks (v2.1)

> Production-hardened with 8-point review corrections + de-bloating

---

## Phase 1: v2.1 Core Corrections (Day 1 - BLOCKERS)

### 1.1 ExecutionContext Threading
- [ ] Create `ExecutionContext` dataclass
  - New file: `core/execution_context.py`
  - Fields: `mode`, `budget_ms`, `start_time`, `request_id`, `snapshot`
  - Methods: `remaining_budget_ms()`, `is_expired()`
- [ ] Pass `ExecutionContext` to:
  - `ExecutionDispatcher.dispatch()`
  - `ReActLoop.run()` / `arun()`
  - `OneShotRunner.execute()`
  - Terminal check functions
- [ ] Remove implicit mode inference from ReActLoop

### 1.2 ResponseEmitter with State Guard
- [ ] Create `ResponseEmitter` class
  - New file: `core/response_emitter.py`
  - Fields: `_request_id`, `_emitted` (bool), `_lock`
  - Methods: `emit()` (returns bool), `was_emitted` property
- [ ] Integrate into `SmartAssistant.arun()`
  - Initialize emitter at request start
  - Use in finally block
  - Log duplicate emission attempts

### 1.3 ExecutionStatus Enum
- [ ] Create `ExecutionStatus` enum
  - Values: `SUCCESS`, `PARTIAL`, `FAILED`, `SKIPPED`
- [ ] Update `ExecutionResult` dataclass
  - Replace `success: bool` with `status: ExecutionStatus`
  - Add `succeeded` and `is_partial` properties
- [ ] Propagate status to:
  - Responder context
  - Flight recorder
  - API response

### 1.4 GraphSnapshot at Dispatcher
- [ ] Create `GraphSnapshot` frozen dataclass
  - Fields: `entities`, `recent_actions`, `focus_entity`, `timestamp`
  - Method: `from_graph(graph)` (thread-safe copy)
- [ ] Take snapshot in `ExecutionDispatcher.dispatch()` at request start
- [ ] Pass snapshot in `ExecutionContext`
- [ ] Update `ReferenceResolver` to use snapshot, not live graph

### 1.5 Async-Only Core
- [ ] Remove all `run_until_complete` wrappers from:
  - `llm.py`
  - `executor.py`
  - `execution_dispatcher.py`
- [ ] Keep sync at HTTP boundary only (`server.py`)
- [ ] Create `sync_test_wrapper()` for tests only

---

## Phase 2: Fix Immediate Bugs (Day 1)
- [ ] Fix ToolMessage validation error in `executor.py`
  - Lines 632-637, 718-723
  - Ensure `status` is never `None`
- [ ] Restore terminal action break in ReAct loop
  - Lines 537-538, 591-592
  - Make terminal plan-relative (see Phase 3)
- [ ] Cap ReAct to 3 iterations
  - Line 485: `max_iterations: int = 3`

---

## Phase 3: Execution Modes (Day 2-3)

### 3.1 ExecutionDispatcher
- [ ] Create `ExecutionDispatcher` class
  - New file: `core/execution_dispatcher.py`
  - Methods: `async dispatch()` (async-only, no sync wrapper)
  - Use deterministic mode selection (no confidence gating)
  - Check: tool_hint exists AND tool in EXTRACTABLE_TOOLS

### 3.2 OneShotRunner (Regex-Only)
- [ ] Create `OneShotRunner` class
  - New file: `core/oneshot_runner.py`
  - **NO LLM FALLBACK** - regex-only
  - If args incomplete → raise `OneShotArgsIncomplete`
  - Dispatcher catches and downgrades to ITERATIVE
- [ ] Define `EXTRACTABLE_TOOLS` set
  - Only tools with known regex patterns
  - `open_app`, `spotify_control`, `play_youtube`, `get_weather`, `set_timer`

### 3.3 Plan-Relative Terminal
- [ ] Update Planner output schema
  - Add `final: bool` field to step schema
  - Default last step to `final: true`
- [ ] Update `_is_terminal()` in ReActLoop
  - Check `step.get("final", False)` instead of tool name
  - Keep `HARD_TERMINALS` for unconditional stops

### 3.4 Integration
- [ ] Update `SmartAssistant` to use dispatcher
  - Replace `self.executor.execute()` with `self.dispatcher.dispatch(ctx)`
  - Thread `ExecutionContext` through

---

## Phase 4: Latency Budget (Day 3)

- [ ] Update ReAct latency budgets
  - Default: **8s** (was 30s)
  - Research: **20s**
  - Per-iteration timeout: **5s**
- [ ] Add `_get_budget()` method
  - Detect research keywords → 20s budget
- [ ] Use `asyncio.wait_for()` for planner calls
- [ ] Implement `_build_partial_result()` for timeout cases
  - Set `status = ExecutionStatus.PARTIAL`

---

## Phase 5: Router Improvements (Day 3)
- [ ] Add `_is_complex_multi_step()` method
  - Count action verbs (≥2 = complex)
  - Detect sequential connectors
  - Detect research indicators
- [ ] Update route logic
  - Call complexity check before action command check
  - **Remove confidence field** - deterministic only
- [ ] Define routing invariants:
  - CHAT: No tools needed
  - DIRECT: Single obvious tool with extractable args
  - PLAN: Everything else

---

## Phase 6: WorldGraph Split (Day 4-5)

- [ ] Extract `IdentityStore` class
  - New file: `core/identity_store.py`
  - Move: identity-related methods
  - Merge with `identity_manager.py` logic
- [ ] Extract `ReferenceResolver` class
  - New file: `core/reference_resolver.py`
  - **Must operate on GraphSnapshot, not live graph**
- [ ] Extract `ContextBuilder` class
  - New file: `core/context_builder.py`
  - **PURE READ-ONLY - zero side effects**
- [ ] Make WorldGraph thin coordinator
  - Delegate to new components
  - Maintain thread-safety

---

## Phase 7: De-Bloating (Day 5-7)

### 7.1 Extract Prompts from config.py
- [ ] Create `prompts/` directory
- [ ] Move prompts to `.txt` files:
  - `system.txt`
  - `responder.txt`
  - `router.txt`
  - `verifier.txt`
  - `memory_judger.txt`
- [ ] Create `prompts/__init__.py` with `load_prompt()`
- [ ] Update config.py to use loader (427 LOC → ~150 LOC)

### 7.2 De-duplicate scheduler.py
- [ ] Move calendar tools to `tools_libs/calendar.py`
  - `CalendarTool`, `SmartCalendarResolver`
- [ ] Move `memory_maintenance()` to `memory/maintenance.py`
- [ ] Keep only `Scheduler` class in `scheduler.py` (763 LOC → ~300 LOC)

### 7.3 Split faiss_store/store.py
- [ ] Create `faiss_store/conversation_store.py`
  - Move: `_load_conversation()`, `append_to_history()`, `get_full_history()`
- [ ] Keep only vector ops in `store.py` (635 LOC → ~400 LOC)

### 7.4 Audit and Clean Memory Layer
- [x] `chroma_store/` - **USED** (ephemeral_manager, memory_tools, research)
- [x] `summary_memory.py` - **USED** (context_manager, llm.py)
- [ ] `memory/router.py` - **CHECK IF DUPLICATE** of memory_coordinator
- [ ] `micro_toolsets.py` - **ONLY USED IN TESTS** - consider removal

---

## Phase 8: Verification

### Latency Tests
- [ ] CHAT queries: target <1s
- [ ] ONE_SHOT queries: target <2s
- [ ] ITERATIVE queries: target <8s default, <20s research

### Correctness Tests
- [ ] Unknown tool_hint → downgrades to ITERATIVE
- [ ] Incomplete regex args → downgrades to ITERATIVE
- [ ] Terminal actions stop the loop
- [ ] Multi-tool chains work in ITERATIVE mode
- [ ] `final: true` respected on last step

### Reliability Tests
- [ ] Frontend ALWAYS shows responses (0% silent failures)
- [ ] No duplicate message emissions (check logs)
- [ ] Partial execution marked as PARTIAL, not SUCCESS
- [ ] Reference resolution stable across request lifetime

---

## Success Metrics (v2.1)

| Metric | Current | Target |
|--------|---------|--------|
| CHAT latency | 1-2s | <1s |
| ONE_SHOT latency | 3-6s | <2s |
| ITERATIVE latency | 30-80s | <8s (default) |
| Research query latency | N/A | <20s |
| ReAct iterations (simple) | 1-5 | 0 (ONE_SHOT) |
| Frontend render rate | ~80% | 100% |
| Double-emission rate | Unknown | 0% |
| Partial marked as success | Yes | No (PARTIAL enum) |

---

## Priority Order

### Day 1: PRODUCTION BLOCKERS
1. ExecutionContext threading (1.1)
2. ResponseEmitter (1.2)
3. ExecutionStatus enum (1.3)
4. GraphSnapshot (1.4)
5. Async-only core (1.5)
6. Immediate bug fixes (Phase 2)

### Day 2-3: CORE ARCHITECTURE
7. ExecutionDispatcher (3.1)
8. OneShotRunner regex-only (3.2)
9. Plan-relative terminal (3.3)
10. Latency budgets (Phase 4)
11. Router improvements (Phase 5)

### Day 4-5: ORGANIZATION
12. WorldGraph split (Phase 6)
13. De-bloating (Phase 7)

### Day 6-7: VERIFICATION
14. All tests (Phase 8)
