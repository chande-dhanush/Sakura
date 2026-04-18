# Sakura Feature Wiring Matrix
**Updated:** 2026-04-14 (Phase 3 Alignment)

## Wiring Status Key
- ✅ **WIRED** — Feature is implemented AND connected to runtime
- ⚠️ **PARTIAL** — Feature exists but has known limitations
- ❌ **BROKEN** — Feature exists but fails at runtime
- 👻 **GHOST** — Feature exists but has no runtime effect
- 🔧 **FIXED** — Previously broken, repaired in this session

## Core Pipeline

| Feature | Write Path | Read Path | Runtime Effect | Status |
|---------|-----------|-----------|----------------|--------|
| Intent Routing (LLM) | router.aroute() | llm.py:arun | Determines DIRECT/PLAN/CHAT | ✅ WIRED (V19 stabilized) |
| Intent Routing (Heuristic) | _is_action_command() | router.aroute() | Bypasses LLM for action verbs | ✅ WIRED |
| Safety Checks | _apply_safety_checks() | After route decision | Blocks greeting misclassification | ✅ WIRED |
| Study Mode Detection | detect_study_mode() | ResponseContext.study_mode | Adds educational prompt | ✅ WIRED |
| Reference Resolution | resolve_reference() | responder_context injection | Entity/action context for LLM | ✅ WIRED (V19 stabilized) |

## Memory System

| Feature | Write Path | Read Path | Runtime Effect | Status |
|---------|-----------|-----------|----------------|--------|
| FAISS Vector Store | VectorMemoryStore.add_message() | MemoryCoordinator.recall() | Long-term memory retrieval | ✅ WIRED |
| Conversation History | store.append_to_history() | store.conversation_history | Chat persistence | ✅ WIRED |
| Memory Judger | MemoryJudger.evaluate() | Triggers FAISS add | Filters significant turns | ✅ WIRED |
| Summary Memory | summary_memory.add_turn() | get_context_injection() | Session compression | ✅ WIRED |
| World Graph Entities | wg.add_entity() | wg.get_context_for_planner() | Entity lifecycle tracking | ✅ WIRED |
| World Graph Actions | wg.record_action() | wg.get_recent_actions() | Action history for context | ✅ WIRED |
| Episodic Memory | episodic_memory.store() | _build_episodic_block() | Memory recall queries | ✅ WIRED (Tiered Gating) |
| Request State | llm.py:arun | Execution pipeline | Process-wide state honesty | ✅ WIRED (V19 Contract) |

## Cognitive / Autonomy

| Feature | Write Path | Read Path | Runtime Effect | Status |
|---------|-----------|-----------|----------------|--------|
| Desire System State | desire.on_user_message() | desire.get_mood_prompt() | Mood injection in prompts | ✅ WIRED |
| Desire Hourly Tick | scheduler → on_hourly_tick() | State decay/recharge | Battery/loneliness update | 🔧 FIXED (was BROKEN - import path) |
| Proactive Scheduler | scheduler → check_and_initiate() | WebSocket broadcast | Proactive check-ins | 🔧 FIXED (was BROKEN - import path) |
| Proactive Message Queue | ProactiveState.queue_message() | pop_pending_message() | Deferred delivery | ✅ WIRED |
| Reflection Engine | _run_async_reflection() | Background analysis | Constraint detection | ✅ WIRED |
| Dream Journal | crystallize_facts() | get_dream_journal() | Fact extraction on startup | ✅ WIRED |

## Tools

| Feature | Registration | Reachability | Status |
|---------|-------------|-------------|--------|
| web_search | get_all_tools() | PLAN/DIRECT | ✅ WIRED |
| spotify_control | get_all_tools() | DIRECT (heuristic) | ✅ WIRED |
| gmail_read_email | get_all_tools() | PLAN/DIRECT | ✅ WIRED |
| calendar_get_events | get_all_tools() | PLAN/DIRECT | ✅ WIRED |
| set_reminder | get_all_tools() | PLAN/DIRECT | ✅ WIRED |
| read_screen | get_all_tools() | PLAN/DIRECT | ⚠️ PARTIAL (monitor mapping) |
| open_app | get_all_tools() | DIRECT (heuristic) | ✅ WIRED |

## Infrastructure

| Feature | Source | Consumer | Status |
|---------|--------|----------|--------|
| FlightRecorder | get_recorder() | server.py SSE stream | ✅ WIRED |
| WebSocket Status | /ws/status | Bubble UI | ✅ WIRED |
| WebSocket Proactive | /ws/proactive | Bubble UI | ✅ WIRED |
| TTS | generate_audio() | /chat SSE (audio_ready) | ✅ WIRED |
| Health Check | /health | Tauri startup gate | ✅ WIRED |
| Origin Validation | websocket_status() | Security | ✅ WIRED |

## Known Remaining Issues

| Issue | Severity | Location | Status |
|-------|----------|----------|--------|
| Sync `route()` context drift | ✅ FIXED | router.py:153 | Resolved in Phase 2 |
| `test_router_bias.py` symbols | ✅ FIXED | tests/ | Resolved in Phase 2 |
| Windows emoji encoding | 🟡 Low | desire.py | Mitigation: UTF-8 runtime |
| `test_world_graph.py` fixtures| ✅ FIXED | tests/ | Resolved in Phase 3 |
| Version Drift | ✅ FIXED | Global | Resolved in Phase 3 |
| Dependency Rot | ✅ FIXED | requirements.txt| Resolved in Phase 3 |
