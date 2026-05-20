# Sakura Lite Runtime Flow Trace
**Updated:** May 20, 2026 (V21.0 Sakura Lite Refactor)

This document traces the request lifecycle and background tasks for Sakura Lite.

---

## 1. Request Lifecycle (Post-V21.0-LITE)

Every request to the `/chat` endpoint proceeds in a fast, deterministic, single-turn sequence:

```
POST /chat → server.py
  ├─ Parse JSON → extract query, image_data, llm_overrides
  ├─ Create event_generator() async generator
  │   ├─ Set up FlightRecorder callback trace_id
  │   └─ Start run_pipeline() task
  │       ├─ Get conversation history from SQLite (conversations table)
  │       ├─ Instantiate RequestState(query, history, ...)
  │       └─ assistant.arun(req_state, llm_overrides)  ← core facade in llm.py
  │
  └─ arun() Pipeline (llm.py)
      │
      ├─ 0. Contract Validation (RequestState.__post_init__)
      │
      ├─ 1. Settings Load
      │    └─ Query settings table in SQLite for user settings (bio, style overrides)
      │
      ├─ 2. Reference Resolution
      │    └─ resolve_reference(user_input) → ResolutionResult
      │         └─ Formats active pronoun context if confidence > 0.4
      │
      ├─ 3. Fast Intent Classification & Routing
      │    ├─ Local regex router check (bypasses LLM for direct matches)
      │    └─ LLM Smart Router fallback classification → DIRECT, PLAN, or CHAT
      │
      ├─ 4. Tool Execution (Hybrid Executor)
      │    ├─ If CHAT: Skip execution, proceed to responder
      │    ├─ If DIRECT: Run via OneShotRunner.aexecute() (fast parameter extraction)
      │    │    └─ System tool: direct local Python execution
      │    │    └─ Code interpreter: local restricted subprocess sandbox
      │    ├─ If PLAN: Run via MultiStepPlanner.aexecute() (lightweight ReAct loop up to 4 turns)
      │    │    └─ Sequentially invokes bound tools, evaluates observations, and loops
      │    └─ Write execution record & metadata back to SQLite World Graph
      │
      ├─ 5. Response Synthesis (Responder)
      │    ├─ context_manager.get_context_for_llm(req_state)
      │    │    ├─ Load SQLite World Graph, episodic memory, and SQLite settings
      │    │    └─ Format context blocks (identity, responder context, reference resolution context)
      │    ├─ Load base personality + style instructions
      │    └─ responder.agenerate() → Output text tokens
      │
      └─ 6. Post-Response Tasks
           ├─ Write user turn & response to SQLite conversations table
           └─ Emit streaming response to Tauri Svelte UI
```

---

## 2. Background Lifecycle (Post-V21.0-LITE)

All heavy, CPU-draining cognitive ticks and proactive timers have been purged. The background tasks are strictly confined to database housekeeping and memory compilation:

```
server.py:lifespan → scheduler
  │
  ├─ Scheduler.schedule_interval("compile_memory", 1800s)
  │    └─ run_reflection_engine()
  │         ├─ Triggered only when server is idle (no active chat turns for 30 mins)
  │         ├─ Queries SQLite for new conversation logs
  │         └─ Compresses important facts and writes to memory_items SQLite table
  │
  ├─ Wake Word background downloader (startup)
  │    └─ Check if hey_jarvis_v0.1.onnx exists in models/openwakeword
  │    └─ Downloads model if missing to enable local voice activation
  │
  └─ Kokoro TTS pipeline warmup (startup)
       └─ Loads neural Kokoro pipeline into RAM on background thread to keep it warm
```
