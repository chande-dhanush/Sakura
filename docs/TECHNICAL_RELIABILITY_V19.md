# Sakura V19.2 Technical Documentation — Reliability Edition

## 1. Core Architecture Overview
Sakura V19.2 is a reliability-hardened version of the V19 prototype. It uses a **Cascade Dispatch** pattern where intent is classified by a Router before being executed by a budget-aware ReAct Loop.

### **Central Processing Pipeline**
1.  **IntentRouter**: Classifies query into `DIRECT`, `PLAN`, or `CHAT`. 
    *   *Reference Resolution*: In V19.2, any query containing reference pronouns ("it", "that", "the one") or possessives ("my favourite") is forced to `PLAN` mode to ensure `query_memory` runs first.
2.  **Executor (ReActLoop)**: A multi-iteration loop that calls the **Planner** for tool selection and the **ToolRunner** for execution.
    *   *Budget Enforcement*: Monitors millisecond-level budget and token counts.
    *   *Tool Checkpoint*: In V19.2, the loop injects successful tool statuses (e.g., `read_screen ✓`) back into the Planner to prevent redundant execution.
3.  **ResponseGenerator**: Synthesizes final output with character-consistent guardrails.

## 2. State & Safety Systems

### **Cancellation Propagation (NEW in V19.2)**
The system now implements a hardware-style "Kill Switch" for background generation.
- **Module**: `sakura_assistant.core.execution.context`
- **Signal**: `threading.Event` (shared via `context.py`).
- **Trigger**: The `/stop` endpoint in `server.py` signals `request_cancellation()`.
- **Enforcement**: The `ReActLoop` checks `is_cancelled()` at the start of every iteration. If set, it returns a partial `ExecutionResult` immediately, preventing further LLM/Tool costs.

### **Context Hardening**
V19.2 uses `__post_init__` validation for core data structures (`RequestState`, `ResponseContext`, `RouteResult`) to prevent silent attribute drift and malformed requests from crashing the hot-path. (Note: `__slots__` was removed from dataclasses to resolve default value conflicts).

## 3. Tool Infrastructure

### **Ephemeral Context Valve**
A system for managing temporary, extremely large tool outputs (e.g., scraping 10 websites).
- **Storage**: Temporary ChromaDB collections prefixed with `eph_`.
- **Management**: `EphemeralManager` handles auto-cleanup and mass-purge (`clear_all()`). 
- **Tool**: `clear_all_ephemeral_memory` allows manual cache clearing.

### **Tool Filtering & Terminal Enforcement (V19.2)**
*   **Semantic Gating**: The `Planner` now uses semantic tool filtering at the prompt level. Based on the Router's `tool_hint`, only relevant tool categories (e.g., "music", "search") are injected into the prompt, reducing token usage by up to 80% for simple tasks.
*   **Terminal Actions**: To prevent planning loops, system actions (clipboard, screen, volume) are now marked as **Terminal**. Once these tools succeed, the `ReActLoop` terminates immediately without re-consulting the Planner.
*   **Alias Normalization**: The system now supports naming aliases (e.g., `read_clipboard` → `clipboard_read`) to ensure the pipeline is resilient to LLM naming hallucinations.
