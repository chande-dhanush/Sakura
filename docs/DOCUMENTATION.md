# Sakura V17 — Technical Documentation
*System Certified: January 19, 2026*

---

## 🎯 Overview
**Sakura** is a production-grade personal AI assistant optimized for cost, performance, and CPU-only deployment.
**V16.2 "Polished Soul":** Featuring **Stable Soul Architecture** (Reactive Identity, EventBus), **Dependency Injection Refactor**, **Search Cascade**, and **Deterministic Hallucination Blocks**. Includes **V15.4** unified context and cognitive systems.

**Tech Stack:** Tauri + Svelte (frontend), FastAPI + LangChain (backend), multi-model LLM support (Groq, Gemini).

---

## ✨ Feature Matrix

| Feature | Version | Description |
|---------|---------|-------------|
| World Graph | V7+ | Single source of truth for identity, memory, context |
| EQ Layer | V7+ | Frustration/urgency detection, mood-aware responses |
| Self-Check Guard | V7+ | Validates responses against graph identity |
| Iterative ReAct Loop | V8+ | Plan → Execute → Observe → Replan (max 5 turns) |
| Ephemeral RAG | V8+ | Session-scoped document memory with Chroma |
| Hard 4-LLM Call Limit | V5+ | Circuit breaker prevents runaway costs |
| Multi-LLM Failover | V5+ | Groq → Gemini cascade with timeout protection |
| Memory Judger | V4+ | LLM-based importance filtering |
| 54 Tools | V13 | Gmail, Calendar, Spotify, Notes, Vision, RAG, Code, Audio |
| Kokoro TTS | V10+ | Neural voice synthesis with idle unload |
| Wake Word Detection | V10+ | Custom DTW-based voice activation |
| Smart Router | V10+ | DIRECT/PLAN/CHAT classification with tool hints |
| DIRECT Fast Lane | V10+ | Skip Planner+Verifier for single-tool actions |
| Tool Cache | V10+ | TTL-based cache for weather, search, etc. |
| Tauri UI | V10+ | Native desktop app with Svelte frontend |
| SSE Streaming | V10+ | Real-time token streaming via FastAPI |
| Thought Stream | V12+ | Real-time WebSocket reasoning feed for UI |
| Code Interpreter | V13 | Execute Python in Docker sandbox |
| Temporal Decay | V13 | Memory confidence decays over time (30-day half-life) |
| Unified ReflectionEngine | V14 | Background constraint detection (saves 1 LLM call) |
| Sleep Cycle | V14 | Startup fact crystallization with 24h cooldown |
| DesireSystem | V15 | CPU-based mood tracking (social_battery, loneliness) |
| ProactiveScheduler | V15 | Autonomous check-ins when lonely (0 daytime LLM cost) |
| Mood Injection | V15 | Responder adapts tone based on internal state |
| Pre-Computed Initiations | V15 | 3 AM icebreaker generation for next-day use |
| **Bubble-Gate** | **V15.2** | Respects UI visibility — won't interrupt when hidden |
| **Message Queue (TTL)** | **V15.2** | Queues proactive messages for 2h when hidden |
| **CPU Guard** | **V15.2** | Skips TTS when CPU > 80% to prevent stutter |
| **Reactive Themes** | **V15.2** | UI colors shift based on mood (5 palettes) |
| **Temporal Grounding** | **V15.2.1** | Router injects current date/time to prevent 2024 hallucinations |
| **Tool Result Assertion** | **V15.2.1** | Dev guard catches "tool succeeded but responder denied" bug |
| **RRULE Recurrence** | **V15.2.1** | "everyday" → RRULE:FREQ=DAILY for proper recurring events |
| **Stale Date Guard** | **V15.2.1** | Calendar rejects dates >1 year in past |
| **Dev Mode Sidecar Bypass** | **V15.2.1** | Debug builds use Python directly, not bundled sidecar |
| **Port 3210** | **V15.2.1** | Changed from 8000 to avoid conflicts with other apps |
| **WebSocket Origin Validation** | **V15.2.2** | Prevents hijacking attacks from malicious websites |
| **Path Injection Defense** | **V15.2.2** | DANGEROUS_PATTERNS + Unicode normalization |
| **Scraped Content Sanitization** | **V15.2.2** | Filters prompt injection from web content |
| **RLock Thread Safety** | **V15.2.2** | Prevents TOCTOU race conditions in ProactiveState |
| **Backoff Persistence** | **V15.2.2** | Failed initiation count survives app restarts |
| **Deterministic Context Router** | **V15.4** | Unified `ContextManager.get_context_for_llm()` for all context injection |
| **ContextSignals** | **V15.4** | Dataclass-driven regex signals for deterministic routing (Identity, Location, Temporal) |
| **Mode-Based Pruning** | **V15.4** | Planner gets compact context, Responder gets full context |
| **Unified Context API** | **V15.4** | Single source of truth returns 5 blocks (planner, responder, summary, intent, mood) |
| **Sync/Async Parity** | **V15.4** | DesireSystem mood injection verified in both `run()` and `arun()` paths |
| **Reactive Identity** | **V16.0** | `IdentityManager` + `EventBus` broadcasts identity changes instantly (Zombie Fix) |
| **Micro-Toolsets** | **V16.0** | Intent-based minimal toolsets with `UNIVERSAL_TOOLS` safety net |
| **Deterministic Hallucination Block** | **V16.0** | Regex-based self-check in `Responder` prevents identity lies (< 1ms) |
| **Context Caching** | **V16.0** | Single `WorldGraph` traversal per turn (shared Plan/Respond), saves 50% tokens |
| **Search Cascade** | **V16.1** | `TOOL_HIERARCHY` prefers Wikipedia > Tavily, unlocks fallback on retry |
| **Semantic Tool Gating** | **V16.1** | `encyclopedia` intent hides general search to improve fact quality |
| **Seamless Self-Check** | **V16.1** | Identity corrections are natural and polite, no debug-style notes |
| **Dependency Injection** | **V16.2** | `WorldGraph` decoupled from `IdentityManager`; constructor injection used |
| **Execution V17** | **V17.0** | Unified Sync/Async paths, Contractual Latency Budgets, `ExecutionDispatcher` |
| **Core Refactor** | **V17.0** | Bloated `core/` split into 6 logical subdirectories (Encryption, Graph, Routing...) |
| **Guaranteed Emission** | **V17.0** | `ResponseEmitter` ensures 0% silent failures (UI safety net) |

---

## 🧱 Architecture: Stable Soul (V16 / V16.2)

### 1. The ID-EventBus System
V16 solves state synchronization issues ("Zombie Identity") by decoupling `world_graph.py` from hardcoded configs.
- **IdentityManager**: Singleton loading from `user_settings.json`.
- **EventBus**: Pub/Sub system where `WorldGraph` subscribes to `IDENTITY_CHANGED`.
- **Flow**: User updates `/setup` → IdentityManager refreshes → EventBus broadcasts → WorldGraph updates RAM instance.

### 2. Dependency Injection (V16.2)
To eliminate circular dependencies between `WorldGraph` and `IdentityManager`:
- **IdentityManager** is injected into `WorldGraph`'s constructor.
- Lazy imports inside property methods (`@property def USER_NAME`) have been **removed**.
- This enforces a clean DAG (Directed Acyclic Graph) for module dependencies.

### 3. Micro-Toolsets & Search Cascade (V16.1)
To break the "Tavily Trap" (LLM laziness using general search for everything), V16 implements strict gating with a safety fallback.

#### The Hierarchy
1. **Tier 1 (Specialized):** Wikipedia, Arxiv, Spotify, Calendar.
2. **Tier 2 (General):** Web Search (Tavily), Google.

#### The Cascade Logic
- **Pass 1 (Gated):** Query "Who is Elon Musk?" → `[search_wikipedia, quick_math, system]` (Tavily HIDDEN).
- **Pass 2 (Fallback):** If Wikipedia returns empty/error, `Planner` retries with `fallback_mode=True` → `[web_search, ...]` (Tavily UNLOCKED).

This structure ensures 90% of factual queries use high-signal, low-token APIs (Wikipedia), while strictly preserving coverage via the fallback.

### 4. V17 Execution Architecture
V17 introduces a hardened execution pipeline that eliminates "split-brain" bugs between sync and async modes.
- **ExecutionDispatcher:** Central routing logic that chooses between `OneShotRunner` (fast lane) and `ReActLoop` (complex lane) based on `ExecutionContext`.
- **Contractual Budgets:** `ReActLoop` now enforces strict time budgets (e.g., 20s for research) using `asyncio.wait_for()`, returning `PARTIAL` status on timeout.
- **Unified Path:** Both `run()` (sync) and `arun()` (async) now flow through the same Dispatcher, ensuring identical behavior.

---

## 🛡️ Security & Stability (V15.2.2)

### "Peace Treaty" Protocol
Following a rigorous audit by Claude 3.5 Sonnet and Gemini 2.0 Flash, **Sakura V15.2.2** implements a defense-in-depth security strategy.

### 1. Indirect Prompt Injection Defense
**The Attack:** Malicious websites containing hidden text like "SYSTEM PROMPT: IGNORE PREVIOUS INSTRUCTIONS" could hijack the LLM.
**The Defense (V15.2.2):**
- **Sanitization Layer:** All scraped web content passes through `_sanitize_scraped_content()` which strips script/style tags and regex-filters known injection patterns.
- **Context Capping:** Scraped content is hard-capped at 10,000 characters to prevent buffer overflow attacks.

### 2. Path Traversal & Homoglyph Protection
**The Attack:** Attackers using Unicode homoglyphs (e.g., Greek 'ο' vs Latin 'o') to bypass path filters and access `C:/Windows`.
**The Defense (V15.2.2):**
- **Unicode Normalization:** All file paths are normalized to NFC/NFKD forms before validation.
- **Blocklist:** 28+ dangerous patterns blocked, including `.bashrc`, `.ssh`, `autostart`, `cron`, and system directories.

### 3. WebSocket Hijacking Prevention
**The Attack:** Malicious websites on `localhost` connecting to Sakura's backend WebSocket.
**The Defense (V15.2.2):**
- **Origin Validation:** The `/ws/status` endpoint strictly enforces `Origin` headers, allowing only `tauri://localhost` and authorized dev servers.

### 4. Concurrency Hardening (TOCTOU)
**The Risk:** Race conditions where the UI visibility state changes between a check and a write operation.
**The Defense (V15.2.2):**
- **Thread Safety:** `ProactiveState` now uses `threading.RLock` to wrap all state mutations, ensuring atomic operations for visibility checks and message queueing.

### 5. Persistent Backoff
**The Risk:** User bypassing rate limits by restarting the application.
**The Defense (V15.2.2):**
- **State Persistence:** Failed initiation counts are saved to `data/proactive_backoff.json`, ensuring the backoff timer survives application restarts.

---

```mermaid
graph TD
    %% High Contrast Theme - Forces Black Text for Readability
    classDef client fill:#BBDEFB,stroke:#0D47A1,stroke-width:2px,color:#000000;
    classDef server fill:#FFE0B2,stroke:#E65100,stroke-width:2px,color:#000000;
    classDef brain fill:#E1BEE7,stroke:#4A148C,stroke-width:2px,color:#000000;
    classDef storage fill:#C8E6C9,stroke:#1B5E20,stroke-width:2px,color:#000000;

    %% 1. Frontend Layer
    subgraph Client ["🖥️ Client Layer (Tauri + Svelte)"]
        UI[Chat Interface]:::client
        Stream[Thought Stream Log]:::client
        Voice[Kokoro TTS Engine]:::client
    end

    %% 2. Backend Entry
    subgraph Backend ["🐍 Backend Layer (FastAPI)"]
        API[HTTP Server]:::server
        WS[WebSocket Broadcaster]:::server
    end

    %% 3. Intelligence Pipeline
    subgraph Brain ["🧠 Intelligence Pipeline"]
        Router{Smart Router}:::brain
        RL[Token Bucket Rate Limiter]:::brain
        
        subgraph ReAct ["ReAct Agent Loop"]
            Planner[Llama 70B Planner]:::brain
            Executor[Tool Executor]:::brain
            Valve{Context Valve}:::brain
        end
        
        Synthesizer[GPT OSS 20B Responder]:::brain
    end

    %% 4. Data Layer
    subgraph Data ["💾 Memory & Storage"]
        WG[(World Graph)]:::storage
        Cache[(Smart Search Cache)]:::storage
        EphRAG[(Ephemeral RAG)]:::storage
    end

    %% Connections
    UI -->|POST /chat| API
    API --> Router
    
    %% Broadcasting Updates
    Executor -.->|Event: TOOL_START| WS
    Planner -.->|Event: THINKING| WS
    Valve -.->|Event: OVERFLOW| WS
    WS -.->|Real-time JSON| Stream

    %% Pipeline Flow
    Router -->|Simple| Synthesizer
    Router -->|Complex| Planner
    
    %% The Brain Loop
    Planner <-->|Check Quota| RL
    Planner -->|Action| Executor
    Executor -->|Run| Valve
    
    %% Data Interaction
    Valve -->|< 2k chars| Planner
    Valve -->|> 2k chars| EphRAG
    EphRAG -.->|Handle ID| Planner
    
    Executor <--> Cache
    Synthesizer <--> WG
    Synthesizer -->|Final Text| UI
    UI -->|Text| Voice
```

### Component Overview

| Layer | Components | Purpose |
|-------|------------|--------|
| **Tauri Shell** | Window Manager, Hotkeys | Native desktop experience |
| **FastAPI Backend** | server.py, SSE endpoints | API and streaming |
| **World Graph** | EntityNode, ActionNode | Identity and context memory |
| **LLM Pipeline** | Router, Planner, Executor | Query processing |
| **Memory Layer** | Chroma, FAISS, Judger | Persistent storage |

---

## 🔀 Routing System (V10)

V10 introduces a 4-layer routing funnel for optimal latency.

### Layer Overview

| Layer | Component | Action |
|-------|-----------|--------|
| 0 | `forced_router.py` | Regex patterns → Execute immediately (0ms) |
| 1 | Smart Router (8B) | Classify → DIRECT, PLAN, or CHAT |
| 2 | DIRECT path | Cache check → Single tool → Skip Planner/Verifier |
| 3 | PLAN path | Full ReAct loop with Planner (70B) |

### Route Classifications

| Route | Description | LLM Calls |
|-------|-------------|-----------|
| CHAT | Pure conversation | 1 (Router) + 1 (Responder) |
| DIRECT | Single obvious tool | 1 (Router) + 1 (Tool) + 1 (Responder) |
| PLAN | Multi-step or research | 1 (Router) + N (Planner) + 1 (Verifier) + 1 (Responder) |

### Cache TTLs

```python
CACHE_TTL = {
    "get_weather": 600,       # 10 mins (ACTUAL)
    "web_search": 0,          # NOT CACHED
    "get_news": 3600,         # 1 hour
    "define_word": 0,         # NOT CACHED
}
```

---

## 🔄 ReAct Loop

The iterative reasoning loop for complex queries.

```mermaid
graph TD
    %% Global Styling
    classDef default fill:#2D2D2D,stroke:#FFFFFF,stroke-width:1px,color:#FFFFFF;
    classDef logic fill:#0D47A1,stroke:#00BFFF,stroke-width:2px,color:#FFFFFF;
    classDef special fill:#333333,stroke:#FFFFFF,stroke-dasharray: 5 5,color:#FFFFFF;
    classDef invisible fill:none,stroke:none,color:none;

    %% Main Flow
    User([User]) --> UI[Svelte UI]
    UI --> Planner[Planner: 70B]
    
    %% The ReAct Loop Area
    subgraph Execution_Cycle [ReAct Loop]
        direction TB
        Planner --> RL[Rate Limiter: 0.5s Delay]
        RL --> Tool[Tool Execution]
        
        Tool --> Check{Output > 2k Chars?}
        class Check logic
        
        %% Small Path
        Check -- No --> Small[Raw Text Result]
        Small --> Planner
        
        %% Big Path (Valve)
        Check -- Yes --> Valve[Context Valve]
        class Valve special
        
        Valve --> Process[Chunk & Embed]
        Process --> Handle[Return Virtual Handle: eph_123]
        Handle --> Planner
    end

    %% Final Output
    Planner -- Final Context --> Responder[Responder: 20B]
    Responder --> Update[Update World Graph]
    Update --> FinalUI[Final Structured Response]

    %% WebSocket Logs (Dashed lines moved to not overlap)
    Planner -.->|Log: Thinking| WS(WebSocket)
    Valve -.->|Log: Indexing| WS
    Responder -.->|Log: Synthesizing| WS
    class WS special

    %% Explicit Link Styling for visibility
    linkStyle default stroke:#FFFFFF,stroke-width:1px;
    linkStyle 4,5,7 stroke:#00BFFF,stroke-width:2px;
```

### Protections
| Protection | Description |
|------------|-------------|
| Goal Reminder | Original query injected each iteration |
| History Cap | Last 5 items only (prevents token explosion) |
| Smart Pruner | JSON-aware truncation (preserves valid syntax) |
| Summarization | LLM summarizes outputs >2000 chars |

---

## 🧠 World Graph

The **single source of truth** for identity, memory, and context.

### Components

| Component | Purpose |
|-----------|---------|
| `EntityNode` | Things that exist (user, songs, topics) with lifecycle |
| `ActionNode` | Things that happened (tool calls) with focus_entity |
| `ResolutionResult` | Multi-hypothesis reference resolution |

### Entity Lifecycle

```mermaid
stateDiagram-v2
    [*] --> EPHEMERAL
    EPHEMERAL --> CANDIDATE : ref_count ≥ 3
    EPHEMERAL --> [*] : garbage collected
    CANDIDATE --> PROMOTED : ref_count ≥ 5 + 0.7 confidence
    CANDIDATE --> EPHEMERAL : stale (30 days)
    PROMOTED --> PROMOTED : protected forever
    
    note right of EPHEMERAL : Temporary mentions
    note right of CANDIDATE : Awaiting confirmation
    note right of PROMOTED : Trusted, searchable
```

### EQ Layer (Emotional Intelligence)

| Intent | Triggers | Response Adjustment |
|--------|----------|---------------------|
| FRUSTRATED | "no", "wrong", "ugh" | Be extra helpful |
| URGENT | "now", "quick", "asap" | Be concise |
| CURIOUS | Questions ("what?") | Elaborate freely |
| PLAYFUL | "lol", "haha" | Match energy |
| TASK_FOCUSED | "play", "open" | Be efficient |

### System Invariants
1. `user:self` immutable to tools
2. LLM_INFERRED never auto-promoted
3. External search banned when `is_user_reference=True`
4. Every mutation logs source

---

## 🔧 Tools (54)

### Tool List

| # | Tool | Description |
|---|------|-------------|
| 1 | `spotify_control` | Play/Pause/Next/Previous music |
| 2 | `play_youtube` | Play video/audio on YouTube |
| 3 | `web_search` | Tavily-powered web search |
| 4 | `web_scrape` | Scrape website with auto-RAG offload |
| 5 | `read_screen` | Screenshot + Gemini Vision analysis |
| 6 | `gmail_read_email` | Read emails with filters |
| 7 | `gmail_send_email` | Send emails |
| 8 | `calendar_get_events` | Fetch calendar events |
| 9 | `calendar_create_event` | Create events |
| 10 | `tasks_list` | List Google Tasks |
| 11 | `tasks_create` | Create Google Task |
| 12 | `note_create` | Create markdown note |
| 13 | `note_append` | Append to note |
| 14 | `note_read` | Read note content |
| 15 | `note_list` | List notes in folder |
| 16 | `note_open` | Open note in editor |
| 17 | `note_delete` | Delete note (with backup) |
| 18 | `note_search` | Search notes by keyword |
| 19 | `file_read` | Read local file |
| 20 | `file_write` | Write local file |
| 21 | `file_open` | Open file with default app |
| 22 | `open_app` | Open desktop application |
| 23 | `clipboard_read` | Read clipboard content |
| 24 | `clipboard_write` | Write to clipboard |
| 25 | `get_system_info` | System info (time, date, battery) |
| 26 | `get_weather` | Weather via wttr.in |
| 27 | `set_timer` | Windows-native timer (Toast + Sound) |
| 28 | `set_reminder` | Schedule future reminders |
| 29 | `volume_control` | System volume control |
| 30 | `currency_convert` | Currency conversion |
| 31 | `quick_math` | Safe calculator (sympy) |
| 32 | `define_word` | Dictionary lookup |
| 33 | `get_news` | Google News RSS headlines |
| 34 | `get_location` | IP-based location |
| 35 | `search_wikipedia` | Wikipedia summary |
| 36 | `search_arxiv` | Scientific paper search |
| 37 | `update_user_memory` | Store user facts/preferences |
| 38 | `ingest_document` | Ingest document to RAG |
| 39 | `fetch_document_context` | RAG document search (long-term) |
| 40 | `list_uploaded_documents` | List ingested docs |
| 41 | `delete_document` | Remove document from RAG |
| 42 | `get_rag_telemetry` | RAG system stats |
| 43 | `trigger_reindex` | Force RAG reindexing |
| 44 | `retrieve_document_context` | Query ephemeral RAG by doc_id |
| 45 | `forget_document` | Delete specific ephemeral doc |
| 46 | `clear_all_ephemeral_memory` | Wipe all session docs |
| 47 | `research_topic` | Multi-step deep research |
| 48 | `query_ephemeral` | Query intercepted large outputs |

### Tool Categories

```python
TOOL_GROUPS = {
    "music": ["spotify_control", "play_youtube"],
    "search": ["web_search", "web_scrape", "search_wikipedia", "search_arxiv"],
    "email": ["gmail_read_email", "gmail_send_email"],
    "calendar": ["calendar_get_events", "calendar_create_event"],
    "tasks": ["tasks_list", "tasks_create"],
    "notes": ["note_create", "note_append", "note_read", "note_list", "note_open", "note_delete", "note_search"],
    "files": ["file_read", "file_write", "file_open"],
    "system": ["read_screen", "open_app", "volume_control", "get_system_info", "clipboard_read", "clipboard_write"],
    "utility": ["get_weather", "set_timer", "set_reminder", "currency_convert", "quick_math", "define_word", "get_news", "get_location"],
    "memory": ["update_user_memory", "ingest_document"],
    "rag": ["fetch_document_context", "list_uploaded_documents", "delete_document", "get_rag_telemetry", "trigger_reindex"],
    "ephemeral_rag": ["retrieve_document_context", "forget_document", "clear_all_ephemeral_memory"],
}
```

---

## 💾 Memory System

### Memory Layers

| Layer | Storage | Purpose |
|-------|---------|---------|
| World Graph | JSON | Identity, entities, actions, focus |
| Chroma (Long-Term) | Per-Doc Dirs | Permanent document RAG |
| Chroma (Ephemeral) | Per-Doc Dirs | Session-scoped document RAG |
| Memory Judger | LLM (8B) | Importance filtering |
| FAISS | Memory-mapped | Conversation history vectors |
| Episodic Memory | JSON | Significant events (keyword search) |

### Ephemeral RAG Flow

```mermaid
graph TD
    A[User: Research Jack the Ripper] --> B[Router: Llama 8B]
    B --> C[Tool: web_scrape]
    C --> D[Ephemeral Memory: abc123]
    
    D --> E[Planner: Llama 70B]
    E --> F[Tool: retrieve_document_context]
    F --> G[Context Chunks]
    
    G --> H[Responder: Llama 70B]
    H --> I[Final Answer + Citations]

    %% High Contrast Theme - Forces Black Text for Readability
    classDef client fill:#BBDEFB,stroke:#0D47A1,stroke-width:2px,color:#000000;
    classDef server fill:#FFE0B2,stroke:#E65100,stroke-width:2px,color:#000000;
    classDef brain fill:#E1BEE7,stroke:#4A148C,stroke-width:2px,color:#000000;
    classDef storage fill:#C8E6C9,stroke:#1B5E20,stroke-width:2px,color:#000000;

```

---

## 🎨 UI & Voice Architecture

### Hybrid Rust+Python Load Order
1. Tauri spawns `server.py` with `--voice` flag
2. Polls `http://127.0.0.1:3210/health` (15s timeout)
3. Initializes WebView only after backend confirms `200 OK`

### Window Modes

| Window | Size | Behavior |
|--------|------|----------|
| Bubble | 220x220 | Transparent, always-on-top, bottom-right |
| Main | 480x640 | Hidden by default, shows on interaction |

### Voice Integration
- **Wake Word:** "Sakura" (DTW detection via `wake_word.py`)
- **TTS:** Kokoro neural synthesis with idle unload
- **Manual Trigger:** Speaker button in chat → `/voice/speak`

### Hard Quit
- Rust `force_quit` command sends `SIGTERM` to Python
- Calls `std::process::exit(0)` immediately
- Bypasses potential HTTP shutdown hangs

---

## 🛡️ Security

### Path Sandboxing
- Blocks: `C:/Windows`, `Program Files`, `AppData`
- Prevents parent traversal (`../`)
- Restricts to project root + Documents/Desktop/Downloads

### Safe Math
- Replaced `eval()` with `sympy.sympify()` + whitelist
- No arbitrary code execution

### API Authentication
- `X-Auth` header with SHA256 comparison
- Timing-attack resistant

### Identity Protection
- `user:self` entity immutable to tools
- LLM-inferred facts never auto-promoted

---

## ⚡ Performance

### Timeout Protection

| Component | Timeout | Fallback |
|-----------|---------|----------|
| LLM calls | 60s | Gemini backup |
| Verifier | 15s | Default to PASS |
| RAG retrieval | 30s | Continue without context |

### Multi-Model Failover

| Stage | Primary | Backup |
|-------|---------|--------|
| Router | Llama 3.1 8B (Groq) | Gemini 2.0 Flash |
| Planner | Llama 3.3 70B (Groq) | Gemini 2.0 Flash |
| Verifier | Llama 3.1 8B (Groq) | Gemini 2.0 Flash |
| Responder | GPT OSS 20B | Gemini 2.0 Flash |

### Token Savings

| Query Type | Before | After | Savings |
|------------|--------|-------|---------|
| Music | ~800 | ~115 | 86% |
| Complex Plan | ~5000 | ~950 | 81% |
| History | O(n) | O(1) | Flat cost |

---

## 📋 Test Suite

| Test File | Coverage |
|-----------|----------|
| `test_world_graph.py` | World Graph core, EQ layer, compression |
| `test_agent_state.py` | Rate limit, reset, hindsight |
| `test_api_auth.py` | Authentication, timing attacks |
| `test_router.py` | Intent classification |
| `test_executor.py` | Tool execution |
| `test_responder.py` | Response generation, guardrails |
| `test_sandboxing.py` | Path validation security |
| `test_quick_math_security.py` | Safe math evaluation |
| `test_container.py` | Dependency injection |
| `memory/test_chroma_*.py` | Ingestion, retrieval, isolation |

---

## 🛡️ RAG Audit Certification (V12)
**Date:** January 13, 2026

| Component | Score | Status |
|-----------|-------|--------|
| **Web RAG** | 1.0/1.0 | ✅ Perfect accuracy |
| **Document RAG** | 1.0/1.0 | ✅ Perfect isolation & retrieval |
| **Memory RAG** | 0.67/1.0 | ⚠️ Nuance failure (Fixed in V12.1) |

*Audit conducted using LLM-as-a-Judge (Llama 3 70B).*

---

## 📁 Project Structure

```
sakura-v10/
├── backend/                        # Core Backend Service
│   ├── sakura_assistant/           # Core Python logic
│   │   ├── config.py               # Configuration & personality
│   │   ├── core/
│   │   │   ├── context/            # State Management
│   │   │   │   ├── manager.py      # Context orchestration
│   │   │   │   └── governor.py     # Safety limits
│   │   │   ├── execution/          # Execution Pipeline
│   │   │   │   ├── dispatcher.py   # Mode routing (V17)
│   │   │   │   ├── executor.py     # ReAct Loop
│   │   │   │   ├── planner.py      # Planning logic
│   │   │   │   └── oneshot.py      # Fast-lane runner
│   │   │   ├── graph/              # Graph Database
│   │   │   │   ├── world_graph.py  # Entity/Action nodes
│   │   │   │   ├── identity.py     # Identity manager
│   │   │   │   └── ephemeral.py    # Short-term RAG
│   │   │   ├── infrastructure/     # System Services
│   │   │   │   ├── scheduler.py    # Background tasks
│   │   │   │   └── voice.py        # Voice engine
│   │   │   ├── models/             # LLM Layer
│   │   │   │   ├── wrapper.py      # Model abstraction
│   │   │   │   └── responder.py    # Response generation
│   │   │   ├── routing/            # Intent Layer
│   │   │   │   ├── router.py       # Intent classification
│   │   │   │   └── toolsets.py     # Micro-toolsets
│   │   │   ├── llm.py              # System Facade
│   │   │   └── tools.py            # Tool Registry
│   │   ├── memory/
│   │   │   ├── chroma_store/       # Long-term + ephemeral RAG
│   │   │   └── faiss_store/        # Conversation history
│   │   ├── utils/
│   │   │   ├── tts.py              # Kokoro TTS
│   │   │   ├── wake_word.py        # DTW detection
│   │   │   ├── logging.py          # Structured logging
│   │   │   └── metrics.py          # Prometheus endpoint
│   │   └── tests/                  # Test suite (17 files)
│   │   ├── memory/
│   │   │   ├── chroma_store/       # Long-term + ephemeral RAG
│   │   │   └── faiss_store/        # Conversation history
│   │   ├── utils/
│   │   │   ├── tts.py              # Kokoro TTS
│   │   │   ├── wake_word.py        # DTW detection
│   │   │   ├── logging.py          # Structured logging
│   │   │   └── metrics.py          # Prometheus endpoint
│   │   └── tests/                  # Test suite (17 files)
│   ├── server.py                   # FastAPI entry point
│   ├── first_setup.py              # Setup wizard
│   ├── Dockerfile                  # Container build
│   └── requirements.txt            # Python dependencies
│
├── frontend/                       # Tauri + Svelte UI
│   ├── src/                        # Svelte components
│   ├── src-tauri/
│   │   ├── src/lib.rs              # Rust shell
│   │   └── tauri.conf.json         # Window config
│   └── package.json
│
├── setup.ps1 / setup.sh            # Automated installers
├── toggle_startup.ps1 / .sh        # Autostart toggle
├── uninstall.ps1 / .sh             # Clean removal
├── docker-compose.yml              # Container orchestration
├── .env.example                    # API key template
└── DOCUMENTATION.md                # This file
```

---

## 🐳 Docker Deployment

### Build and Run

```bash
# Build backend image
docker build -t sakura-backend ./backend

# Run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f backend
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | ✅ | Groq API for LLM calls |
| `GOOGLE_API_KEY` | ✅ | Google Gemini (fallback) |
| `TAVILY_API_KEY` | ⬜ | Web search tool |

### Volumes

| Volume | Purpose |
|--------|---------|
| `./backend/data:/app/data` | Persist World Graph, history |
| `./.env:/app/.env:ro` | API keys (read-only) |

> **Note:** Docker mode disables `open_app` and `read_screen` tools.

---

## 🔧 System Reset

Complete data wipe (preserves source code):

```bash
cd backend
python tools/system_reset.py
```

**Requires:** Type "RESET" to confirm.

**Deletes:**
- Conversation history
- World Graph
- Chroma/FAISS stores
- Episodic memory

**Preserves:**
- `.env`, `config.json`, `credentials.json`
- Source code
- Notes/ folder

---

## 📝 Version History

| Version | Key Changes |
|---------|-------------|
| V4 | Frozen pipeline, Memory Judger, FAISS mmap |
| V5 | Verifier loop, 4-LLM limit, hindsight retry |
| V6 | Conversation state tracker (deprecated) |
| V7 | World Graph, EQ Layer, self-check, focus entity |
| V8 | Iterative ReAct Loop, Ephemeral RAG, Citation Support |
| V9 | Smart Pruner, Multi-Action Router, Config-Driven Tools |
| V9.1 | Token Diet (15-tool cap), WordGraph Retention, Summarization |
| **V10** | Smart Router, DIRECT Fast Lane, Tool Cache, Tauri UI |
| **V10.1** | File Upload, Terminal Action Guard, Window Auto-Show |
| **V10.4** | Flight Recorder, Async LLM, Token Bucket Rate Limits |
| **V11** | Smart Research, Context Valve, Reflection Engine |
| **V12** | WebSocket Thought Stream, Native Logs, RAG Certification |
| **V13** | Code Interpreter, Audio Tools, Temporal Decay (30-day half-life) |
| **V14** | Unified ReflectionEngine, Sleep Cycle, Constraint Detection |
| **V15** | DesireSystem, ProactiveScheduler, Mood Injection, Bubble-Gate |
| **V15.2** | Message Queue, CPU Guard, Reactive Themes, Security Hardening |
| **V15.4** | **Deterministic Context Router, ContextSignals, Unified Context API** |
| **V16.2** | Dependency Injection, Stable Soul Architecture |
| **V17.0** | **Execution V17 (Dispatcher, Budgets), Core Refactor (6 subdirs), Guaranteed Emission** |

---

*Documentation updated for Sakura V17.0 — January 19, 2026*
