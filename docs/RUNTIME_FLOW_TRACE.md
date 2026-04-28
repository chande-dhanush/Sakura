# Sakura Runtime Flow Trace
**Updated:** 2026-04-28 (V19 DeepSeek Integration)

## Request Lifecycle (Post-V19-FIX)

```
POST /chat → server.py:840
  ├─ Parse JSON → extract query, image_data
  ├─ Create event_generator() async generator
  │   ├─ Setup FlightRecorder callback
  │   └─ Start run_pipeline() task
  │       ├─ Get conversation history from FAISS store
  │       ├─ Instantiate RequestState(query, history, ...)  ← SINGLE SOURCE OF TRUTH [Phase 2]
  │       └─ assistant.arun(req_state, llm_overrides=data.get('llm_overrides'))  ← CORE PIPELINE [V19]
  │
  └─ arun() Pipeline (llm.py:169)
      │
      ├─ 0. Contract Validation (RequestState.__post_init__)  ← [Phase 3]
      │
      ├─ 1. Vision Short-Circuit (if image_data)
      │    └─ Delegates to _handle_vision → Returns early
      │
      ├─ 2. Settings Load (V18.3)
      │    ├─ Load user_settings.json
      │    ├─ Apply sakura_name, response_style, system_prompt_override
      │    └─ Update self.responder.personality
      │
      ├─ 3. Graph & Context
      │    ├─ detect_study_mode(user_input) → bool
      │    ├─ ★ resolve_reference(user_input) → ResolutionResult  [V19-FIX-02: NOW CAPTURED]
      │    │    └─ Formats into reference_context string if confidence > 0.4
      │    ├─ infer_user_intent(user_input, history)
      │    └─ FlightRecorder.log("ReferenceResolution", ...)
      │
      ├─ 4. Routing (Async)  [V19 stabilized]
      │    ├─ ★ router.aroute(req_state, llm_override=container.get_router_llm(overrides)) [V19]
      │    │    ├─ _is_action_command() → DIRECT (bypasses LLM)
      │    │    └─ LLM classification → DIRECT/PLAN/CHAT
      │    ├─ _apply_safety_checks() → Greeting/Tavily guard
      │    └─ Capture classification/tool_hint into req_state
      │
      ├─ 5. Execution (V17 Executor Layer)
      │    ├─ executor_layer.dispatch(req_state, llm_overrides) [V19]
      │    │    ├─ Create ExecutionContext (threads ref_context) [Phase 2]
      │    │    ├─ ONE_SHOT → OneShotRunner (fast lane)
      │    │    └─ ITERATIVE → ReActLoop (multi-step)
      │    │         └─ ★ planner_llm=container.get_planner_llm(overrides) [V19]
      │    ├─ record_action() → World Graph
      │    └─ PlanVerifier (for PLAN mode only)
      │         └─ ★ verifier_llm=container.get_verifier_llm(overrides) [V19]
      │
      ├─ 6. Response Generation (Async)
      │    ├─ context_manager.get_context_for_llm(req_state)
      │    │    ├─ Tiered Memory Gating (_build_episodic_block) [Phase 2]
      │    │    │    └─ T1: Explicit, T2: PLAN, T3: DIRECT+ref, T4: CHAT
      │    │    ├─ planner_context (identity, episodic, actions)
      │    │    ├─ responder_context (World Graph)
      │    │    └─ summary_context (SummaryMemory)
      │    ├─ desire_system.get_mood_prompt() → mood string
      │    ├─ Inject reference_context into responder_context
      │    ├─ Build ResponseContext (Slots Hardened) [Phase 3]
      │    └─ responder.agenerate(resp_context, llm_override=container.get_responder_llm(overrides)) [V19]
      │
      ├─ 7. Post-Response
      │    ├─ desire_system.on_user_message() / on_assistant_message()
      │    ├─ summary_memory.add_turn()
      │    ├─ memory_judger.evaluate() (fire-and-forget)
      │    ├─ world_graph.advance_turn() + save()
      │    └─ emitter.emit(response_text)
      │
      └─ Return {content, mode, tool_used, tools_used, metadata}
```

## Background Lifecycle (Post-V19-FIX)

```
server.py:lifespan → schedule_cognitive_tasks()
  │
  ├─ ★ Import Verification  [V19-FIX-03: NEW]
  │    ├─ from ..cognitive.desire import get_desire_system
  │    └─ from ..cognitive.proactive import get_proactive_scheduler
  │    └─ Logs: "Import verification passed" or "CRITICAL: imports FAILED"
  │
  ├─ Scheduler.schedule_interval("desire_tick", 3600s)
  │    └─ run_hourly_desire_tick()  [V19-FIX-03: FIXED IMPORT]
  │         ├─ from ..cognitive.desire import get_desire_system
  │         ├─ desire.on_hourly_tick()
  │         └─ Logs battery + loneliness values
  │
  └─ Scheduler.schedule_interval("proactive_check", 3600s)
       └─ _run_proactive_wrapper() → run_hourly_proactive_check()  [V19-FIX-03: FIXED IMPORT]
            ├─ from ..cognitive.proactive import get_proactive_scheduler
            ├─ scheduler.check_and_initiate()
            └─ Logs initiation result
```

## Key Changes from Phase 1

| Path | Before | After |
|------|--------|-------|
| Router call | `aroute(input, history, bool)` — POSITIONAL ❌ | `aroute(query=input, history=history)` — KEYWORD ✅ |
| Reference resolution | Computed, discarded | Computed, formatted, injected into responder context ✅ |
| Scheduler cognitive imports | `from .cognitive.*` — WRONG PATH | `from ..cognitive.*` — CORRECT PATH ✅ |
| Import failures | Silently swallowed | Loud `ImportError` handler + startup verification ✅ |
