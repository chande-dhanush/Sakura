# Sakura Legacy System Dependency Map

This document outlines the dependencies and import relations of the Sakura V19.5/V20.0 assistant backend before the Sakura Lite refactor.

## 1. Architectural Layers & Coupling

```mermaid
graph TD
    Server[backend/server.py] --> Router[core/routing/router.py]
    Server --> Voice[core/audio/voice.py]
    
    Router --> Context[core/context/manager.py]
    Router --> Executor[core/execution/executor.py]
    
    Executor --> Tools[core/execution/tools.py]
    Executor --> Verifier[core/execution/verifier.py]
    
    Context --> WG[core/graph/world_graph.py]
    Context --> FAISS[core/memory/store.py]
    Context --> Summary[core/memory/summary_memory.py]
    
    Reflection[core/memory/reflection.py] --> WG
    Judger[core/memory/judger.py] --> FAISS
    
    Scheduler[core/cognitive/proactive.py] --> Desire[core/cognitive/desire.py]
    Scheduler --> WG
    
    classDef legacy fill:#ffe6e6,stroke:#ff9999,stroke-width:1px;
    class Server,Router,Voice,Context,Executor,Tools,Verifier,WG,FAISS,Summary,Reflection,Judger,Scheduler,Desire legacy;
```

## 2. Dependency Directory Matrix

| Module | Location | Primary Dependencies | Coupling Level |
| :--- | :--- | :--- | :--- |
| **Server / Entrypoint** | `backend/server.py` | `core/routing/router.py`, `utils/flight_recorder.py`, FastAPI | High |
| **Intent Router** | `backend/sakura_assistant/core/routing/` | `core/context/manager.py`, `core/execution/executor.py`, Groq/Gemini client | High |
| **Execution Loop** | `backend/sakura_assistant/core/execution/` | `core/execution/tools.py`, `core/execution/verifier.py`, `utils/flight_recorder.py` | Critical |
| **Context Manager** | `backend/sakura_assistant/core/context/` | `core/graph/world_graph.py`, `memory/memory_coordinator.py`, `utils/flight_recorder.py` | High |
| **Memory / Graph** | `backend/sakura_assistant/core/graph/` | `sqlite3` (actions), JSON-files (entities), standard library | Medium-High |
| **Vector Memory** | `backend/sakura_assistant/core/memory/` | `faiss`, `sentence_transformers`, `numpy`, JSON files | High |
| **Proactive / Desire** | `backend/sakura_assistant/core/cognitive/`| `core/graph/world_graph.py`, standard math library | Medium |
| **Observability** | `backend/sakura_assistant/utils/` | `json`, `time`, SSE websocket emitter | Low (Utility) |
