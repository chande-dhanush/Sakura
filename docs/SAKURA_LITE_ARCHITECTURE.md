# Sakura Lite Systems Architecture Specification
**Version:** V1.0-LITE  
**Status:** Canonical Technical Standard  

This document defines the architecture, data flows, latency specifications, and engineering guidelines for **Sakura Lite**. It serves as the engineering source of truth to prevent future regression into AGI-style cognitive orchestration loops or metadata-bloated background state ticks.

---

## 1. Core Architectural Strategy

Sakura Lite is a **deterministic, low-latency desktop cognitive layer** designed to act as a silent context shadow over the local OS. 

```
                                  +-----------------------------------+
                                  |        Tauri System Tray UI       |
                                  +-----------------------------------+
                                                    ^
                                                    | (Local WebSockets / HTTP)
                                                    v
                                  +-----------------------------------+
                                  |        FastAPI Backend            |
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
                         | Execution (<150ms) |           | Responder (<1.0s) |
                         +--------------------+           +-------------------+
                                    \                               /
                                     \                             /
                                      v                           v
                                  +-----------------------------------+
                                  |    Thread-Safe SQLite Database    |
                                  |  (Memory, Notes, WorldGraph, Log) |
                                  +-----------------------------------+
                                                    |
                                                    v
                                  +-----------------------------------+
                                  |       Streaming Audio Output      |
                                  |         (Kokoro TTS Engine)       |
                                  +-----------------------------------+
```

---

## 2. Core vs. Experimental Systems

To prevent dependency bloat and performance degradation, the codebase is strictly separated into **Core Systems** and **Experimental/Optional Modules**.

### Core Systems (Production-Grade, Zero Latency)
These systems must be maintained, optimized, and never compromised for experimental features:
1.  **FastAPI Backend & Tauri Hotkey Shell:** Handles OS interactions, web sockets, system tray events, and IPC.
2.  **OneShotRunner Execution Engine:** Parses intents, executes direct regex commands, and processes single-turn tool calls.
3.  **Thread-Safe SQLite persistence layer (`sakura.db`):** WAL-enabled database storing all configuration, logs, world-graph entity mappings, and conversations.
4.  **Reference Resolution Engine:** Contextual resolver that updates and evaluates active pronouns (e.g., "that screen", "it", "that song") on every turn.
5.  **Local Notes & File System Tooling:** Low-overhead direct system hooks.
6.  **Flight Recorder:** Logging utility for debugging state transitions and LLM latencies.

### Experimental / Optional Modules (Detachable & Sandbox Restricted)
These features must remain isolated behind environment variables, feature flags, or separate threads, and must degrade gracefully if disabled:
1.  **openWakeWord Voice Activation:** Heavy ONNX model. Disabled by default via `SAKURA_ENABLE_VOICE=false` to prevent CPU exhaustion.
2.  **Spotify / Gmail / Calendar API Tools:** High API drift risk. Wrapped in try-catch guards; authentication failures must not crash server initialization.
3.  **Local Code Execution (Subprocess):** Subprocess-based local execution. Sandbox-restricted with strict resource budgets (CPU, memory, timeouts) to prevent memory leaks and infinite loops.
4.  **Vision Context (Llama Scout):** On-demand visual screen ingestion; must not run on passive loops.

---

## 3. Data Persistence & Memory Architecture

Ad-hoc JSON serialization loops have been purged. All system state resides in a single SQLite instance `data/sakura.db` running in **WAL (Write-Ahead Logging)** mode.

### Database Schema Mappings
*   **`settings`:** Key-value storage mapping user settings, bio, system settings, and temporal cache.
*   **`conversations`:** Historical turns stored chronologically. Checked for reference resolution.
*   **`memory_items`:** Extracted facts and indices pointing to the raw FAISS vector file (`data/faiss_index.bin`).
*   **`entities`, `actions`, `responses`:** SQLite-backed nodes for the simplified World Graph. Confined to booleans and datetimes—no floating-point emotional decay multipliers.
*   **`reminders`:** Scheduler state for tasks and calendar items.
*   **`traces`:** Human-readable reasoning logs (Flight Recorder output).

---

## 4. Latency Guarantees & Budgets

Every user interaction has a strict time budget. If a component exceeds its budget, it must timeout and degrade gracefully.

| Interaction Path | Target Latency | Max Budget | Fallback Strategy |
| :--- | :--- | :--- | :--- |
| **Regex Match Route** (Local command) | `<50ms` | `150ms` | Execute command silently, skip LLM calls. |
| **Single-turn LLM Tool Call** | `<600ms` | `1200ms` | Terminate tool extraction; fall back to dry chat. |
| **Speech-to-Text Ingestion (Whisper)** | `<300ms` | `800ms` | Fall back to text input or abort transcription. |
| **Kokoro TTS Keep-Warm Playback** | `<200ms` | `500ms` | Deliver text response immediately, play audio as ready. |
| **Idle Database Transaction** | `<2ms` | `10ms` | Skip transaction, log lock collision to Flight Recorder. |

---

## 5. Architectural Principles & Anti-Overengineering Rules

Developers modifying Sakura V10 must adhere to the following rules:

1.  **Silent by Default:** Do not explain actions. If the user asks to "mute music", mute music and return a silent confirmation or a single-word response. Never output verbose status messages unless explicitly prompted.
2.  **Bypass the LLM (Deterministic Lanes):** If a user input can be resolved with a regex pattern or string matching (e.g., "open spotify", "what is on my clipboard", "take a screenshot"), route it directly to the tool and execute. Do not burn API calls to let a router model determine obvious intents.
3.  **No Concurrency Theater:** Do not use parallel LLM workers (like the legacy memory-judger + reflection split). Reflection and long-term memory consolidation must run sequentially on an idle background scheduler thread when user activity is zero.
4.  **No Emulated Consciousness:** Never write float-based variables to simulate loneliness, anxiety, hunger, or happiness. An assistant's quality is measured by utility and situational context awareness, not synthetic mood swings.

---

## 6. Architectural Red Flags

If you encounter any of the following during development or review, it is a sign of system drift and must be refactored:

*   **[RED FLAG 01] Multi-Step Verification Loops:** Reintroducing prompt validation chains (`PlanVerifier`) that verify an LLM's own tool call output with another LLM call.
*   **[RED FLAG 02] Passive Tick Schedules:** Ticks that query external APIs or run LLM thought cycles every hour, draining battery and generating API bills when the computer lid is closed.
*   **[RED FLAG 03] Global State Blocking:** Import-time disk reads or database queries that block the FastAPI startup event loop.
*   **[RED FLAG 04] Apology/Sarcasm Scaffolding:** Hardcoded personality files containing lists of sarcastic remarks or apologetic boilerplate. Personality must emerge through prompt instructions rather than execution loops.
