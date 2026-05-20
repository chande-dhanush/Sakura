# Sakura V21.1-LITE — Technical Specification
*System Certified: May 20, 2026*

---

## 🎯 Overview

**Sakura Lite** is a desktop-integrated AI assistant optimized for low latency, high reliability, and minimal resource footprint on local environments. 

### **The Lite Philosophy**
Sakura Lite abandons complex multi-turn AGI-like cognitive loops (ReAct planner, verification cascades, and emotional metabolic ticks) in favor of a **deterministic single-turn execution flow**. By focusing on spatial operating system context (screen, clipboard, active window) and high-speed pronoun reference resolution, Sakura Lite achieves sub-second responsiveness while running on a single developer machine.

*   **V21.0 "Sakura Lite Transition" (Current):** Purged legacy cognitive systems (Desire system, Planner loop, Verifier chain) and consolidated all storage (settings, graph, memory metadata, conversation logs) into a single, WAL-enabled thread-safe SQLite database (`data/sakura.db`). Replaced Docker with a secure local Python execution sandbox. Streamlined execution flow around `OneShotRunner`.
*   **V20.0 "Deterministic Execution & Isolation":** Implemented tool call deduplication and registry-level rate-limiting isolation.
*   **V19.5 "Voice I/O Hardening":** Upgraded local audio interfaces with Kokoro TTS, Groq Whisper (STT), and openWakeWord. Implemented Keep-Warm TTS runtime.
*   **V19.0 "Model Abstraction":** Introduced modular stage models and request-time overrides.

**Tech Stack:** Tauri + Svelte (frontend client), FastAPI + Python (backend server), SQLite (state store), Groq/Gemini API (cloud inference), Kokoro + openWakeWord (local audio).

---

## ⚡ Execution Pipeline: One-Shot Runner

Rather than looping through multi-turn agentic thoughts, Sakura Lite resolves queries using a high-speed, single-turn execution model.

```
                      +-----------------------------------+
                      |         Tauri Svelte UI           |
                      +-----------------------------------+
                                        ^
                                        | (Local WebSockets / HTTP)
                                        v
                      +-----------------------------------+
                      |         FastAPI Backend           |
                      +-----------------------------------+
                                        |
                               [User Input / Hotkey]
                                        |
                                        v
                         +-----------------------------+
                         |  Regex Tool Router (Local)  |
                         +-----------------------------+
                           /                         \
                (Matches Regex)                     (No Match)
                         /                             \
                        v                               v
             +--------------------+           +-------------------+
             | Direct Python Tool |           | Single-Turn LLM   |
             | Execution (<150ms) |           | Extraction Route  |
             +--------------------+           +-------------------+
                        \                               /
                         \                             /
                          v                           v
                      +-----------------------------------+
                      |    Thread-Safe SQLite Database    |
                      |  (Memory, Notes, WorldGraph, Log) |
                      +-----------------------------------+
```

### **1. Local Regex Fast Lane**
Direct queries that match registered regex patterns (e.g., "open vscode", "read my clipboard", "what's on my screen") bypass the LLM routing stage entirely. The FastAPI backend dispatches them to their respective system utility tools in **<50ms**.

### **2. OneShotRunner (DIRECT Mode)**
For standard singular actions that require LLM extraction (e.g., "remind me to call John in 10 minutes" or "what is the weather in Paris?"), the router classifies the task as `DIRECT`. The `OneShotRunner` extracts parameters and runs the tool in a single turn.

### **3. MultiStepPlanner (PLAN Mode)**
For complex, multi-step queries (e.g., research, code writing, or multi-stage calculations), the router classifies the task as `PLAN`. The `MultiStepPlanner` initiates a lightweight ReAct planning loop (up to 4 turns). It executes tools sequentially, analyzes observations, and synthesizes a final response, keeping the loop structured and observable without heavy cognitive overhead.

---

## 💾 Unified SQLite Data Layer

All historical JSON files and concurrent databases have been consolidated into `data/sakura.db` running in WAL (Write-Ahead Logging) mode. A Python `threading.RLock` protects all writes to prevent Windows sharing violations.

### **Table Schema**
*   **`settings`:** Key-value storage mapping user settings, bio, and temporal cache.
*   **`conversations`:** Chronological chat history.
*   **`memory_items`:** Extracted facts and FAISS indices pointing to the raw index binary (`data/faiss_index.bin`).
*   **`entities` / `actions` / `responses`:** Structured World Graph representation of pronouns, nouns, and actions. High-overhead float-based emotional decay math has been purged.
*   **`reminders`:** Scheduler state for future events.
*   **`traces`:** Flight Recorder trace logs.

---

## 🧠 Context Intelligence Layer (V21.1)

These engines were added in the Post-Refactor Refinement Phase (Phases A-E) to transform Sakura from a clean architecture into a genuinely attentive, context-aware workflow companion — without reintroducing AGI theater, synthetic emotions, or orchestration creep.

All engines are initialized in `ContextManager.__init__()` and orchestrated through `get_context_for_llm()` in `manager.py`.

### **Engines**

- **`AdaptiveInteractionEngine`** (`adaptive_engine.py`): Tracks interaction metrics (query lengths, response lengths, inter-request delays, interruption frequency) in SQLite. Determines the current **Response Posture** (`SILENT`, `SHORT_ACK`, `NORMAL`, `DETAILED`, `REFLECTIVE`) based on time-of-day, rapid-fire detection, active app, friction level, and query intent keywords.

- **`FrictionDetector`** (`adaptive_engine.py`): Monitors user input for correction/frustration patterns ("no", "wrong", "stop", "redo"). When friction is detected, it automatically increases the friction level in `AdaptiveInteractionEngine`, causing the response posture to scale down to `SHORT_ACK` to reduce annoyance.

- **`ContextRelevanceEngine`** (`relevance_engine.py`): Ranks retrieved RAG memories using a multi-factor scoring system: retrieval confidence × recency decay (48-hour halflife) + active app match boost + current project folder boost + file extension relevance boost. Memories scoring below a configurable threshold are suppressed to prevent stale/creepy memory resurfacing.

- **`ContextBudgeter`** (`relevance_engine.py`): Allocates character budgets dynamically based on request classification (`CHAT`, `DIRECT`, `PLAN`). Chat turns get large history budgets but no screen/clipboard. Direct tool calls get large clipboard/screen budgets but minimal history. Plan modes get balanced budgets across all sources.

- **`WorkflowContextEngine`** (`workflow_engine.py`): Queries the active foreground window title and process name using native Windows APIs (`win32gui`, `win32process`, `psutil`). Latency: <1ms.

- **`SessionStateClassifier`** (`workflow_engine.py`): Classifies the current user session into one of five states — `CODING`, `WRITING`, `RESEARCH`, `MEDIA`, `GENERAL` — based on the active process name and query keywords.

- **`ToolBiasingRegistry`** (`workflow_engine.py`): Returns boosted tool recommendation weights depending on the active session state. For example, `CODING` sessions boost `execute_code` (1.5x) and `file_read` (1.3x); `RESEARCH` sessions boost `search_web` (1.6x).

- **`ImplicitReferenceResolver`** (`workflow_engine.py`): Resolves implicit terms like "that file", "the error", or "open it" by querying the clipboard and the last recorded action in SQLite. Injects resolved context into the LLM prompt so the model doesn't need to guess.

- **`ConfidenceEngine`** (`confidence_engine.py`): Scores the confidence, relevance, and ambiguity of implicit reference resolutions and memory retrievals. Determines an **Action Posture**: `CLARIFY` (confidence <0.4), `HEDGE` (0.4-0.75), or `PROCEED` (≥0.75).

- **`AttentionManager`** (`attention_manager.py`): Detects focus mode (fullscreen apps, rapid typing, gaming) and suppresses interruptions, TTS prompts, and verbose responses during high-focus states.

- **`TrustAwareFailureHandler`** (`failure_handler.py`): Tracks a rolling trust score (0.0-1.5) based on consecutive successes and failures. When trust is low (<0.6), failure messages use humble/transparent phrasing and suggest manual alternatives. When trust is high, failures use calm/direct phrasing.

- **`ReliabilityTelemetry`** (`telemetry.py`): Logs tool success/failure rates, cancellation rates, planner turn metrics, latency history, and context mismatch events back to SQLite for long-term health reporting.

- **`PreferenceAdaptationEngine`** (`preference_adaptation.py`): Learns temporal behavior patterns (focus hours, app transition habits) and manages forgetting/decay logic that periodically reduces entity familiarity scores and prunes ephemeral entities from the WorldGraph.

### **Context Flow**

```
User Input → FrictionDetector → AdaptiveInteractionEngine (posture)
                                         ↓
                              WorkflowContextEngine (active app)
                                         ↓
                              SessionStateClassifier (session type)
                                         ↓
                              ToolBiasingRegistry (tool weights)
                                         ↓
                              ImplicitReferenceResolver ("that file")
                                         ↓
                              ContextRelevanceEngine (ranked memories)
                                         ↓
                              ContextBudgeter (token allocation)
                                         ↓
                              ConfidenceEngine (action posture)
                                         ↓
                              AttentionManager (focus suppression)
                                         ↓
                              LLM Response Generation
```

---

## 🧱 Purged Legacy Systems

The following systems have been completely removed from the codebase to reduce maintenance burden and eliminate operational latency:

1.  **ReAct Planning Loop (`planner.py` & `verifier.py`):** Multi-turn reasoning loops that generated sequential steps, observations, and replans are replaced by the `OneShotRunner`.
2.  **Desire System (`desire.py` / `cognitive/`):** Simulated metabolic float values tracking loneliness, duty, and battery are deleted.
3.  **Proactive Scheduler (`proactive.py`):** Hourly background ticks and 3 AM automated message generation are purged.
4.  **Docker Sandbox (`Dockerfile` sidecars):** Replaced with a restricted local Python execution model running via `subprocess.Popen` in [code_interpreter.py](file:///d:/Personal%20Projects/Sakura%20V10/backend/sakura_assistant/core/tools_libs/code_interpreter.py).

---

## 🔒 Security Sandboxing

### **Path Traversal Shield**
File-system tools route through the canonical `validate_path` validation engine in [executor.py](file:///d:/Personal%20Projects/Sakura%20V10/backend/sakura_assistant/core/execution/executor.py). 
*   **Unicode Normalization:** All file paths are normalized to NFC/NFKD forms.
*   **Blocklist Filters:** Prevents access to system folders (`C:/Windows`, `Program Files`, `AppData`) or parent traversals (`../`).
*   **Scope Restriction:** Code execution and file creation are restricted to the project root, Documents, Desktop, and Downloads folders.

### **Subprocess Sandbox (Code Interpreter)**
Python code execution is sandboxed using native OS process restrictions:
*   Memory caps and CPU core counts are restricted.
*   A strict execution timeout (default: 10s) terminates runaway calculations.
*   Sanitizers warn and block imports of dangerous modules (`os`, `sys`, `subprocess`, `socket`, `requests`).

---

## 📁 Project Structure

```
sakura-v10/
├── backend/                        # FastAPI Backend Service
│   ├── sakura_assistant/           # Core Python Logic
│   │   ├── config.py               # Personality & User configurations
│   │   ├── core/
│   │   │   ├── context/            # Context Intelligence Layer
│   │   │   │   ├── manager.py      # Context Router & Assembly
│   │   │   │   ├── adaptive_engine.py   # Interaction Metrics & Response Posture
│   │   │   │   ├── relevance_engine.py  # Memory Ranking & Token Budgeting
│   │   │   │   ├── workflow_engine.py   # Active App & Session Classification
│   │   │   │   ├── confidence_engine.py # Confidence & Action Posture Scoring
│   │   │   │   ├── attention_manager.py # Focus Mode & Interruption Suppression
│   │   │   │   ├── failure_handler.py   # Trust-Aware Failure Messaging
│   │   │   │   ├── telemetry.py         # Reliability Health Metrics
│   │   │   │   ├── preference_adaptation.py # Habit Learning & Memory Decay
│   │   │   │   ├── governor.py          # Context Governor
│   │   │   │   └── state.py             # Agent State & Rate Limiting
│   │   │   ├── database.py         # Thread-safe WAL SQLite connector
│   │   │   ├── execution/          # Execution Routing
│   │   │   │   ├── executor.py     # Path security and validation helpers
│   │   │   │   └── oneshot_runner.py# Single-turn routing & execution engine
│   │   │   ├── graph/              # World Graph structures (SQLite-backed)
│   │   │   ├── infrastructure/     # Scheduler services
│   │   │   ├── models/             # LLM Model wrappers
│   │   │   ├── routing/            # Intent mapping and fast routing
│   │   │   ├── llm.py              # System Facade and Request Handler
│   │   │   ├── tools.py            # Tool Registry and dispatch
│   │   │   └── tools_libs/         # Built-in execution tool definitions
│   │   ├── memory/                 # FAISS store and search utilities
│   │   ├── utils/                  # TTS (Kokoro), WakeWord, and Logging helpers
│   │   └── tests/                  # Pytest unit suites
│   ├── server.py                   # FastAPI app entry point & compatibility stubs
│   ├── requirements.txt            # Python environment dependencies
│   └── pyproject.toml              # Build & test configurations
│
├── frontend/                       # Tauri Svelte client
│   ├── src/                        # UI markup & components
│   └── src-tauri/                  # Rust window client shell
│
├── docs/                           # Strategic & system documentation
│   ├── SAKURA_CANONICAL_STRATEGIC_REPORT.md
│   ├── SAKURA_LITE_ARCHITECTURE.md
│   └── DOCUMENTATION.md            # This file
```

---

## 📋 Test Suite

| Test Module | Coverage |
| :--- | :--- |
| `tests/test_code_interpreter.py` | Python execution output, syntax checking, sandboxing, resource timeouts |
| `tests/test_executor.py` | Path validation security, dangerous path blocklists, `OneShotRunner` tool execution paths |
| `tests/test_world_graph.py` | SQLite entity/relationship insertions and reference queries |
| `tests/test_api_auth.py` | API authorization validation and timing attack defenses |
| `tests/test_router.py` | Intent classification accuracy and regex extraction routes |
| `tests/test_context_refinement_v19.py` | Context engines: session classification, friction detection, posture adaptation, tool biasing, confidence scoring, telemetry, trust-aware failure handling (12 tests) |
