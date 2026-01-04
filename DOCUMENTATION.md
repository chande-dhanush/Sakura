# Sakura V10 - AI Personal Assistant
## Technical Documentation

---

## 🎯 Overview

**Sakura** is a production-grade personal AI assistant with voice interaction, agentic tool execution, persistent world memory, emotional intelligence, and self-correcting verification. Built with **Tauri + Svelte** (V10 UI), LangChain, and multi-model LLM support.

### Key Features

| Feature | Status | Description |
|---------|--------|-------------|
| **World Graph** | ✅ | Single source of truth for identity, memory, and context |
| **EQ Layer** | ✅ | Frustration/urgency detection, mood-aware responses |
| **Self-Check Guard** | ✅ | Validates responses against graph identity |
| **Iterative ReAct Loop** | ✅ | Plan → Execute → Observe → Replan (max 5 turns) |
| **Ephemeral RAG** | ✅ | Session-scoped document memory with Chroma |
| **Hard 4-LLM Call Limit** | ✅ | Circuit breaker prevents runaway costs |
| **Token-Optimized Planner** | ✅ | ~115 tokens via dynamic tool injection |
| **Multi-LLM Failover** | ✅ | Groq → Gemini cascade with timeout protection |
| **Memory Judger** | ✅ | LLM-based importance filtering |
| **Chroma Vector Store** | ✅ | Per-document isolation with auto-cleanup |
| **48 Tools** | ✅ | Gmail, Calendar, Spotify, Notes, Vision, RAG, Ephemeral Memory |
| **Kokoro TTS** | ✅ | Neural voice synthesis with idle unload |
| **Wake Word Detection** | ✅ | Custom DTW-based voice activation |
| **Smart Pruner** | ✅ | V9: JSON-aware token bloat prevention |
| **Multi-Action Router** | ✅ | V9: Compound request detection |
| **Config-Driven Tools** | ✅ | V9: OCP-compliant tool groups |
| **Summarization Layer** | ✅ | V9.1: LLM summarizes large outputs instead of truncating |
| **Post-Turn Reflection** | ✅ | V9.1: Auto-learns user facts from conversation |
| **Token Diet** | ✅ | V9.1: Dynamic tool injection (15 max per request) |
| **WorldGraph Retention** | ✅ | V9.1: Bounded memory with hard caps |
| **Smart Router** | ✅ | V10: DIRECT/PLAN/CHAT classification with tool hints |
| **DIRECT Fast Lane** | ✅ | V10: Skip Planner+Verifier for single-tool actions |
| **Tool Cache** | ✅ | V10: TTL-based cache for weather, search, etc. |
| **Planner 70B** | ✅ | V10: Upgraded for implicit query reasoning |
| **Tauri UI** | ✅ | V10: Native desktop app with Svelte frontend |
| **SSE Streaming** | ✅ | V10: Real-time token streaming via FastAPI |
| **Window Modes** | ✅ | V10: Hidden/Input/Full with hotkeys |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    TAURI SHELL (Rust)                          │
│  ┌─────────────────┐    ┌──────────────────┐                   │
│  │  Window Manager │    │  Global Hotkeys  │                   │
│  │  (3 modes)      │    │  Shift+S / Shift+F│                  │
│  └────────┬────────┘    └──────────────────┘                   │
│           │                                                    │
│           │ processing_status_changed(str)                      │
├───────────▼─────────────────────────────────────────────────────┤
│                     ViewModel Layer                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              ChatViewModel                               │   │
│  │  - QThreadPool for async workers                         │   │
│  │  - ProcessingStatus enum                                 │   │
│  └────────┬─────────────────────────────────────────────────┘   │
├───────────▼─────────────────────────────────────────────────────┤
│                      WORLD GRAPH LAYER                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  WorldGraph (Single Source of Truth)                     │   │
│  │  ├─ EntityNode (user, songs, topics, preferences)        │   │
│  │  ├─ ActionNode (tool calls with focus_entity)            │   │
│  │  ├─ infer_user_intent() → FRUSTRATED/URGENT/CASUAL/etc   │   │
│  │  ├─ self_check() → Validates response against graph      │   │
│  │  └─ resolve_reference() → "that" → song, not action      │   │
│  └──────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                      LLM Pipeline (V8 ReAct)                    │
│                                                                 │
│  ┌────────────┐                                                 │
│  │   Router   │ → CHAT → RESPONDER → Done                       │
│  │ (DIRECT/   │ → DIRECT → Fast Lane (skip Planner) → Done      │
│  │  PLAN/CHAT)│                                                 │
│  └─────┬──────┘                                                 │
│        │ PLAN                                                │
│        ▼                                                        │
│  ╔══════════════════════════════════════════════════════════╗   │
│  ║              ITERATIVE ReAct LOOP (Max 5)                ║   │
│  ║  ┌──────────┐   ┌──────────┐   ┌──────────┐              ║   │
│  ║  │ PLANNER  │ → │ EXECUTOR │ → │ OBSERVE  │ ─┐           ║   │
│  ║  │(+history)│   │(+graph)  │   │(ToolMsg) │  │           ║   │
│  ║  └──────────┘   └──────────┘   └──────────┘  │           ║   │
│  ║       ▲                                      │           ║   │
│  ║       └───────────── LOOP ───────────────────┘           ║   │
│  ║                                                          ║   │
│  ║  [GOAL REMINDER] injected each iteration                 ║   │
│  ╚══════════════════════════════════════════════════════════╝   │
│        │                                                        │
│        ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │       VERIFIER → PASS → RESPONDER (+EQ adjustment)       │   │
│  │                → FAIL → Hindsight Retry                  │   │ 
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Memory Layer                           │   │
│  │  Chroma (Per-Doc) + WorldGraph + Memory Judger           │   │
│  │  + Ephemeral RAG (Session-Scoped)                        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Iterative ReAct Loop (V8)

The assistant now uses a **Thinking Loop** for complex queries.

### How It Works

1. **Plan**: Planner receives user query + tool history
2. **Execute**: Tools are called, results stored as `ToolMessage`
3. **Observe**: Results appended to history
4. **Replan**: Planner sees results and decides next action
5. **Repeat**: Until goal is complete or max 5 turns

### Key Features

| Feature | Implementation |
|---------|----------------|
| **Goal Reminder** | Original query injected in every loop iteration |
| **History Injection** | `ToolMessage` objects passed to Planner |
| **Loop Protection** | Max 5 iterations hard limit |
| **Cleanup Prompt** | System note when ephemeral docs created |
| **Smart Pruner** | V9: Truncates outputs >1000 chars (JSON-aware) |

---

## ⚡ V9 Optimizations

### 1. Smart Pruner (Token Bloat Fix)

**Problem:** ReAct loop stuffed context with huge tool outputs, pushing user context out.

**Solution:** `ToolExecutor.prune_output()` in `executor.py` (Refactored from `llm.py`):
- Detects JSON → prunes large keys (`html`, `body`, `content`)
- Keeps JSON syntax valid
- Text → truncates at word/sentence boundaries

```python
# Before (breaks JSON):
{"html_body": "<15000 chars..."  # INVALID JSON

# After (valid JSON):
{"html_body": "[15000 chars - use retrieve_document_context()]"}
```

---

## 🛡️ Enterprise Hardening (V10)

### 1. Security
- **Simple Auth:** `X-Auth` header enforcement on `/chat`.
- **Eval Removal:** Replaced unsafe `eval()` with `sympy.sympify()` + whitelist.
- **Sandboxing:** Whitelisted directories for file operations.

### 2. SOLID Architecture
Refactored the Monolithic `llm.py` into specialized modules:
- `router.py`: Intent classification (Direct/Plan/Chat).
- `executor.py`: Tool execution and output management.
- `responder.py`: Response generation and guardrails.
- `container.py`: Dependency Injection for LLM configuration.

### 3. Observability
- **Structured Logging:** JSON logs via `structlog`.
- **Metrics:** Prometheus endpoint for request/LLM tracking.

### 2. Multi-Action Router (Compound Requests)

**Problem:** Router classified "Check weather AND email boss" as SIMPLE.

**Solution:** `has_multi_action()` in `intent_classifier.py`:
- Detects `action + "and" + action` pattern
- Only triggers on compound actions, not "Tom and Jerry"

### 3. Config-Driven Tool Groups (OCP)

**Problem:** Adding tool groups required modifying `planner.py`.

**Solution:** Moved to `config.py`:
```python
TOOL_GROUPS = {
    "music": ["spotify", "youtube", "volume"],
    "search": ["web", "retrieve", "fetch", "news"],
    # ...
}
TOOL_GROUPS_UNIVERSAL = ["quick_math", "get_weather", "read_screen", "clipboard_read"]
```

### 4. Session Isolation

**Problem:** Ephemeral docs persisted after reset.

**Solution:** `reset_session_docs()` in `tools.py`, called from `viewmodel.py` on reset.

---

## 🧠 V9.1 Brain Improvements

### 1. Summarization Layer (Context Preservation)

**Problem:** Tool outputs truncated to 1000 chars, losing semantic meaning by turn 4.

**Solution:** For outputs >2000 chars, uses 8B model to summarize instead of truncate:
```python
# Before: "[TRUNCATED: 5000 chars]" - Model "forgets" content
# After: "[SUMMARY of 5000 chars] The document shows revenue of $5M..."
```

Anti-hallucination prompt ensures factual accuracy.

### 2. Post-Turn Reflection (Auto-Learning)

**Problem:** User says "I moved to Tokyo" → Graph stays stale.

**Solution:** Async analysis after each response:
```
User: "I moved to Tokyo last month"
→ 🧠 [V9.1] Reflection: New fact detected: location = Tokyo
→ World Graph updated automatically
```

Strict extraction prompt ignores hypotheticals ("I wish I was in Tokyo").

### 3. Token Diet (Groq Free Tier Optimization)

**Problem:** Sending all 48 tools = ~5,000 tokens/request. Groq limit = 8K TPM.

**Solution:** Keyword-based dynamic tool injection in `planner.py`:
- Extracts keywords from user input ("play", "email", "weather")
- Maps to tool groups (music, email, utility)
- Hard cap of 15 tools max per request

```
User: "Play Blinding Lights"
→ Keywords: "play"
→ Groups: {music}
→ Tools: 8 (spotify, youtube, volume + universals)
→ Tokens: ~2,000 (was ~5,000)
```

### 4. WorldGraph Retention Policy

**Problem:** Promoted entities accumulate forever (slow hoarding).

**Solution:** Bounded retention in `world_graph.py`:

| Rule | Implementation |
|------|----------------|
| **EPHEMERAL never persisted** | `save()` filters lifecycle |
| **Stale CANDIDATES deleted** | Not referenced in 7 days → deleted |
| **Hard caps per type** | QUERY: 200, SONG: 150, APP: 100 |
| **Protected** | `user:*` and `pref:*` never deleted |

### 5. Confidence-Gated Reflection

**Problem:** 8B model might misinterpret statements.

**Solution:** Added 90% confidence threshold:
```python
# If <90% confident, output null instead of storing wrong fact
"If confidence < 90%, respond with: null
Better to miss a memory than store a lie."
```

### 6. Brutal Planner Optimization (Token & Logic)

**Problem:** Planner system prompt was ~800 tokens of static examples. History loops caused token explosion.

**Solution:**
1.  **Prompt Diet**: Removed all 48 tool examples (relying on Native Schema). Condensed rules by 60%.
    - Result: Context drops from ~800 → ~150 tokens.
2.  **History Lobotomy**: Hard cap of **last 5 items** in `tool_history`.
    - Result: Prevents infinite context growth in deep loops.

### 7. Scalability Assurance (O(1) History)

**Analysis:** Does token usage increase with 10,000 messages?

**Verdict:** **NO.**
- **Responder**: Uses fixed window (Rolling Summary + Last 3 Messages).
- **Planner**: Sees ZERO history (only current request + graph).
- **Cost**: Constant (O(1)) regardless of conversation length.

---

## 🚀 V10 "God Tier" Architecture

V10 introduces a 4-layer routing funnel for optimal latency and intelligence.

### The 4-Layer Funnel

```
LAYER 0: forced_router.py (Regex) → Execute immediately (0ms, $0)
    ↓ (no match)
LAYER 1: Smart Router (70B) → {DIRECT, PLAN, CHAT}
    ↓
LAYER 2: DIRECT → Cache check → Execute tool (skip Planner/Verifier)
LAYER 3: PLAN → Planner (70B) + ReAct loop
    ↓
OUTPUT: Responder + World Graph
```

### Key Improvements

| Feature | Description |
|---------|-------------|
| **Smart Router** | Outputs JSON `{classification, tool_hint}` instead of SIMPLE/COMPLEX |
| **DIRECT Path** | Skips Planner + Verifier for single-tool actions like "check email" |
| **Tool Cache** | TTL-based dict cache (weather: 30m, search: 24h, news: 1h) |
| **Planner 70B** | Upgraded from 8B for implicit query reasoning ("Who is X?") |

### Route Classifications

| Route | Description | LLM Calls |
|-------|-------------|-----------|
| **CHAT** | Pure conversation, no tools | 1 (Router) + 1 (Responder) |
| **DIRECT** | Single tool, obvious action | 1 (Router) + 1 (Responder) |
| **PLAN** | Multi-step or research needed | 1 (Router) + N (Planner) + 1 (Verifier) + 1 (Responder) |

### Cache TTLs

```python
CACHE_TTL = {
    "get_weather": 1800,      # 30 mins
    "web_search": 86400,      # 24 hours
    "get_news": 3600,         # 1 hour
    "define_word": 604800,    # 7 days
}
```

---

## 🧠 World Graph

The World Graph is the **single source of truth** for identity, memory, and context.

### Core Components

| Component | Purpose |
|-----------|---------|
| `EntityNode` | Things that exist (user, songs, topics) with lifecycle |
| `ActionNode` | Things that happened (tool calls) with focus_entity |
| `ResolutionResult` | Multi-hypothesis reference resolution |
| `EmbeddingManager` | Lazy embeddings with auto-unload |

### Entity Lifecycle

```
EPHEMERAL ─────► CANDIDATE ─────► PROMOTED
   │                 │                │
   │ ref_count < 2   │ ref_count ≥ 3  │ user_stated or
   │ (garbage        │ (awaiting      │ high confidence
   │  collected)     │  promotion)    │ (trusted, searchable)
```

### EQ Layer (Emotional Intelligence)

```python
# Intent Detection
graph.infer_user_intent("No not that, wrong one!")
# → UserIntent.FRUSTRATED

# Mood Adaptation
graph.get_intent_adjustment()
# → "User seems frustrated. Be extra helpful."

# Self-Check (Hallucination Guard)
valid, correction = graph.self_check("As the famous actor Dhanush...")
# valid = False, blocks hallucination
```

### Intent States

| Intent | Trigger Signals | Response Adjustment |
|--------|-----------------|---------------------|
| FRUSTRATED | "no", "wrong", "ugh" | Be extra helpful |
| URGENT | "now", "quick", "asap" | Be concise |
| CURIOUS | Questions ("what?") | Elaborate freely |
| PLAYFUL | "lol", "haha", "jk" | Match energy |
| TASK_FOCUSED | "play", "open", "search" | Be efficient |

### Reference Resolution

```
User: "Play Shape of You"
Graph: Creates entity:song:shape_of_you, sets as focus_entity

User: "Who sings that?"
Graph: resolve_reference("that") → song (not action) with 0.9 confidence
```

### System Invariants

1. **Identity Protection**: `user:self` immutable to tools
2. **No Hallucination Crystallization**: LLM_INFERRED never auto-promoted
3. **External Search Ban**: Banned when `is_user_reference=True`
4. **Reference Priority**: focus_entity > entities_involved > action
5. **Source Tracking**: Every mutation logs source
6. **Compression Non-Destructive**: key_facts never lost

---

## ⚡ LLM Pipeline

### Pipeline Flow (V8)

```
═══════════════════════════════════════════════════════════════
SELF-CORRECTING PIPELINE WITH ITERATIVE ReAct LOOP
═══════════════════════════════════════════════════════════════

World Graph Query (identity, intent, resolution)
    │
    ▼
ROUTER (#1 - Llama 70B)
    │
    ├─► SIMPLE → RESPONDER (#2) → Done
    │
    └─► COMPLEX → ITERATIVE ReAct LOOP ═══════════════════════
                    │
                    ▼
                 ╔═══════════════════════════════════════════╗
                 ║  FOR turn IN range(5):                    ║
                 ║    1. PLANNER(query, tool_history)        ║
                 ║    2. EXECUTOR(steps) → ToolMessages      ║
                 ║    3. tool_history.extend(results)        ║
                 ║    4. IF no_more_tools: BREAK             ║
                 ║    5. [GOAL REMINDER] injected            ║
                 ║  END LOOP                                 ║
                 ╚═══════════════════════════════════════════╝
                    │
                    ▼
                 VERIFIER (#3)
                    │
        ┌───────────┴───────────┐
       PASS                    FAIL
        │                       │
        ▼                       ▼
  RESPONDER (#4)         RETRY PLANNER (#4)
  (+EQ adjustment)             │
        │                      ▼
      Done              LOCAL FORMATTER
                        (No LLM - Budget Safe)

═══════════════════════════════════════════════════════════════
```

### Multi-Model Failover

| Stage | Primary Model | Backup Model |
|-------|---------------|--------------|
| Router | Llama 3.3 70B (Groq) | Gemini 2.0 Flash |
| Planner | OpenAI/OSS-120b (Groq) | Gemini 2.0 Flash |
| Verifier | Llama 3.3 70B (Groq) | Gemini 2.0 Flash |
| Responder | OpenAI/OSS-20b (Groq) | Gemini 2.0 Flash |

---

## 🎨 V10 UI & Voice Architecture

Sakura V10 introduces a hybrid Rust+Python architecture with deep voice integration.

### 1. Hybrid Load Order
To prevent "Frontend Loading..." hangs, the `lib.rs` backend coordinator uses a polling mechanism:
1. Spawns `server.py` with `--voice` flag.
2. Polls `http://127.0.0.1:8000/health` (15s timeout).
3. **Only** initializes the main WebView when backend confirms `200 OK`.

### 2. Bubble Window (Transparent)
The bubble interface is a **220x220 transparent WebView** pinned to the bottom-right.
- **Why 220px?** To allow the context menu to expand without being clipped by the OS window manager.
- **CSS:** Elements are positioned absolutely to the bottom-right corner to mimic a 64px widget.

### 3. Voice Loop Integration
- **Default Mode:** Voice Engine runs in a background thread (`--voice`).
- **Wake Word:** "Sakura" (DTW detection via `shared_mic.py`).
- **Manual Trigger:** Speaker button (`🔊`) in chat triggers `/voice/speak` for immediate TTS.
- **Visual Feedback:** Frontend sends `trigger` signal, Backend logs `[WAKE]`.

### 4. Hard Quit (Safety)
The system uses a custom `force_quit` Rust command:
- **Signal:** Immediately sends `SIGTERM/KILL` to the Python child process.
- **Exit:** Calls `std::process::exit(0)` to terminate the Tauri shell instantly.
- **Why?** Bypasses potential HTTP shutdown hangs if the main thread is blocked.

---

## 📝 Ephemeral RAG (V8)

Session-scoped document memory for handling large content without context overflow.

### How It Works

1. **Auto-Offload**: `web_scrape` detects content > 2000 chars
2. **Ingest**: Content saved to per-document Chroma store
3. **Preview**: Returns first 500 chars + AI-generated summary
4. **Retrieve**: `retrieve_document_context(doc_id, query)` fetches relevant chunks
5. **Cleanup**: `forget_document(doc_id)` or `clear_all_ephemeral_memory()`

### Key Features

| Feature | Implementation |
|---------|----------------|
| **Citation Support** | Chunk IDs returned for source tracking |
| **Session Tracking** | `_SESSION_DOCS` list tracks created docs |
| **Cleanup Reminder** | System note when ephemeral docs exist |
| **Preview Text** | 500 chars + summary to guide queries |

### Example Flow

```
User: "Research Jack the Ripper"
    │
    ▼
Agent: web_scrape("https://en.wikipedia.org/wiki/Jack_the_Ripper")
    │
    ▼
Tool: "📄 Saved to Ephemeral Memory
       ID: `abc123`
       Preview: 'Jack the Ripper was an unidentified...'
       Summary: 'Victorian-era serial killer in London'
       Use: retrieve_document_context('abc123', 'victims')"
    │
    ▼ (Loop 2)
Agent: retrieve_document_context("abc123", "canonical five victims")
    │
    ▼
Tool: "📄 Context from Doc `abc123`:
       [Chunk 1: chunk_7] Mary Ann Nichols was found...
       [Chunk 2: chunk_9] Annie Chapman was discovered..."
    │
    ▼
Agent: Synthesizes answer with citations [Source: abc123, Chunk 7]
    │
    ▼ (Task Complete)
Agent: forget_document("abc123")
```

---

## 🔧 Tools (41)

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
| 27 | `set_timer` | **Windows-native timer** (Toast + Alarm Sound) |
| 28 | `set_reminder` | Schedule future reminders |
| 29 | `volume_control` | System volume control |
| 30 | `currency_convert` | Currency conversion |
| 31 | `quick_math` | Safe calculator |
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
| **44** | `retrieve_document_context` | **Query ephemeral RAG by doc_id** |
| **45** | `forget_document` | **Delete specific ephemeral doc** |
| **46** | `clear_all_ephemeral_memory` | **Wipe all session docs** |

### Tool Categories

```python
TOOL_SCHEMAS = {
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
| **World Graph** | JSON | Identity, entities, actions, focus |
| **Chroma (Long-Term)** | Per-Doc Dirs | Permanent document RAG |
| **Chroma (Ephemeral)** | Per-Doc Dirs | Session-scoped document RAG |
| **Memory Judger** | LLM (8B) | Importance filtering |
| **Episodic Memory** | JSON | Significant events (keyword search) |
| **Conversation History** | JSON | Short-term context |

### Memory Before Routing

Memory is injected **before** the router classifies the query:

```python
# 1. World Graph Query
is_user_ref, conf = world_graph.is_user_reference(input)
intent = world_graph.infer_user_intent(input)
resolution = world_graph.resolve_reference(input)

# 2. Episodic Memory Retrieval
memory_context = get_memory_for_routing(user_input)

# 3. Route with full context
```

---

## 📁 Project Structure

```
Sakura V10/
├── run_sakura.py              # Entry point (Legacy)
├── DOCUMENTATION.md           # This file
├── sakura_assistant/
│   ├── config.py              # Configuration & personality
│   ├── core/
│   │   ├── llm.py             # Pipeline with ReAct loop
│   │   ├── voice_engine.py    # V10: Background interaction loop
│   │   ├── planner.py         # Token-optimized planner
│   │   ├── world_graph.py     # World Graph implementation
│   │   ├── agent_state.py     # State tracking
│   │   ├── verifier.py        # Outcome verification
│   │   ├── tools.py           # Tool definitions
│   │   ├── scheduler.py       # Background task scheduler
│   │   ├── context_manager.py # Smart context injection
│   │   └── reflection.py      # Memory reflection engine
│   ├── utils/
│   │   ├── tts.py             # Kokoro TTS (Local)
│   │   ├── wake_word.py       # DTW wake word detection
│   │   ├── memory_judger.py   # Importance classifier
│   │   └── episodic_memory.py # Significant events store
│   ├── data/
│   │   └── world_graph.json   # Persisted graph state
├── tools/
│   ├── record_wakeword.py     # V10: CLI Tool to record templates
│   └── system_reset.py        # Factory reset
├── server.py                  # V10: FastAPI Backend Entry Point
├── debug_kokoro.py            # Audio diagnostics
├── Dockerfile                 # Backend container build
├── logging.conf
└── requirements.txt
```

---

## ⚡ Performance

### Timeout Protection

| Component | Timeout | Fallback |
|-----------|---------|----------|
| LLM calls | 60s | Gemini backup |
| Verifier | 15s | Default to PASS |
| RAG retrieval | 30s | Continue without context |

### Token Savings

| Query Type | Before | After | Savings |
|------------|--------|-------|---------|
| Music | ~800 | ~115 | **86%** |
| Complex Plan | ~5000 | ~950 | **81%** |
| Full History | - | O(1) | **Flat** |

---

## 🔒 Security

- **Path Sandboxing**: Blocks parent traversal, restricts to project root
- **Identity Protection**: Graph prevents tool mutations to user identity
- **API Keys**: Stored in `.env` (gitignored)
- **Ephemeral Cleanup**: Session docs auto-tracked for deletion

---

## 📋 Test Suite

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_world_graph.py` | 28 | World Graph core, EQ layer, compression |
| `test_agent_state.py` | 11 | Rate limit, reset, hindsight |
| `test_verifier.py` | 12 | Verdict parsing, fallbacks |
| `test_e2e_retry.py` | 9 | Retry flow, formatters |
| `test_chroma_ingest.py` | 3 | Document ingestion pipeline |

---

## 📦 Deployment & Lifecycle (New in V10)
V10 allows standard cross-platform deployment without Docker, preserving native desktop automation capabilities.

### 1. Automated Setup (Recommended)
This installs Python, Node.js, System Libraries (`ffmpeg`, `tesseract`), and creates the venv.

| OS | Command | Action |
|----|---------|--------|
| **Windows** | `.\setup.ps1` | Full install + Venv setup |
| **Linux/Mac** | `./setup.sh` | Uses `apt`/`brew` for sys deps |

### 2. Startup Management (Autostart)
Configure Sakura to run silently in the background on login.

| OS | Toggle Script | Mechanism |
|----|---------------|-----------|
| **Windows** | `.\toggle_startup.ps1` | Start Menu Shortcut → `run_background.vbs` |
| **Linux** | `./toggle_startup.sh` | `~/.config/autostart/sakura.desktop` |

### 3. Background Execution (Manual)
Run the backend silently without an open terminal window.

- **Windows**: `run_background.vbs` (Visual Basic wrapper)
- **Linux/Mac**: `run_background.sh` (nohup wrapper)

### 4. Uninstallation (Clean Wipe)
Removes all generated artifacts (`PA/` venv, `node_modules`, `data/`, `target/`).
Preserves source code and `.env`.

- **Windows**: `.\uninstall.ps1`
- **Linux/Mac**: `./uninstall.sh`

### Docker Support (Headless)
For server-only deployments (no desktop automation), use `docker-compose up`.
**Note**: `open_app` and `read_screen` tools will be disabled in Docker mode.


---

## 📁 Project Structure

```
sakura-v10/
├── backend/                    # Core Backend Service
│   ├── sakura_assistant/       # Core Python logic (LLM, RAG, Tools)
│   ├── tools/                  # Script utilities
│   ├── data/                   # Persistent storage (World Graph, History)
│   ├── Notes/                  # User notes
│   ├── server.py               # FastAPI entry point
│   ├── Dockerfile              # Backend container build
│   └── requirements.txt        # Python dependencies
│
├── frontend/                   # Tauri + Svelte UI
│   ├── src/                    # Svelte components
│   ├── src-tauri/              # Rust shell
│   └── package.json
│
├── docker-compose.yml          # Container orchestration
├── .env.example                # API key template (copy to .env)
└── DOCUMENTATION.md            # This file
```

---

## 🐳 Docker Deployment

### Build and Run

```bash
# Build backend image
docker build -t sakura-backend .

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
| `OPENAI_API_KEY` | ⬜ | GPT-4o mini (fallback) |
| `TAVILY_API_KEY` | ⬜ | Web search tool |

### Volumes

| Volume | Purpose |
|--------|---------|
| `./data:/app/data` | Persist World Graph, history |
| `./.env:/app/.env` | API keys (read-only) |

---

## 📝 Version History

| Version | Key Changes |
|---------|-------------|
| V4 | Frozen pipeline, Memory Judger, FAISS mmap |
| V5 | Verifier loop, 4-LLM limit, hindsight retry |
| V5.1 | Pre-LLM heuristics, token optimization |
| V6 | Conversation state tracker (deprecated) |
| V7 | World Graph, EQ Layer, self-check, focus entity |
| V8 | Iterative ReAct Loop, Ephemeral RAG, Goal Reminder, Citation Support |
| V9 | Smart Pruner, Multi-Action Router, Config-Driven Tools, Session Isolation |
| V9.1 | Token Diet (15-tool cap), WorldGraph Retention, Summarization Layer, Post-Turn Reflection |
| **V10** | **Smart Router (DIRECT/PLAN/CHAT), DIRECT Fast Lane, Tool Cache, Planner 70B** |
| **V10 Stable** | **Voice Mode Default, Hard Quit, Manual TTS, 220px Bubble UI, Backend Health Check** |

---

*Documentation updated for Sakura V10 Stable - January 2026*

---

## 🔧 System Reset

**Complete data wipe:**
```bash
python tools/system_reset.py
```

**Requires confirmation:** Type "RESET" to proceed.

**Deletes:**
- Conversation history
- WorldGraph
- Chroma/FAISS stores
- Episodic memory
- User uploads

**Preserves:**
- .env, config.json, credentials
- Source code
- Notes/ folder
- Documentation

