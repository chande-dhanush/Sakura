# Sakura Legacy Current Execution Flow

This document details the step-by-step request lifecycle and planning pipelines in Sakura V19.5/V20.0.

## 1. Request Lifecycle Overview

```mermaid
sequenceDiagram
    autonumber
    User->>Tauri Frontend: Types query / Speaks hotkey
    Tauri Frontend->>FastAPI Server: WebSocket Event / HTTP Request
    FastAPI Server->>Flight Recorder: start_trace(query)
    FastAPI Server->>Intent Router: classify_intent(query, history)
    Note over Intent Router: LLM call (e.g. Llama-3.1-8B)<br/>Checks for greetings/Tavily traps
    
    alt DIRECT Mode
        Intent Router->>OneShot Runner: execute_tool_direct()
        OneShot Runner->>System Tools: run()
        System Tools-->>Intent Router: return tool_output
    else PLAN Mode
        Intent Router->>ReAct Loop: execute_plan()
        loop Up to 5 Planner Iterations
            ReAct Loop->>Planner LLM: generate_action(state, observations)
            Planner LLM-->>ReAct Loop: Action (Tool + Args)
            ReAct Loop->>System Tools: execute(tool, args)
            System Tools-->>ReAct Loop: Observation (JSON output)
        end
        ReAct Loop->>Plan Verifier: verify_plan(plan, observations)
        Note over Plan Verifier: LLM call verifying results
        Plan Verifier-->>ReAct Loop: is_complete (True/False)
    end
    
    Intent Router->>Responder LLM: generate_final_response(context, outputs)
    Responder LLM-->>FastAPI Server: output_text
    FastAPI Server->>Flight Recorder: end_trace(success)
    FastAPI Server-->>Tauri Frontend: Streamed text / Audio File (Kokoro)
    Tauri Frontend-->>User: Visual response / Audio voice
```

## 2. Background Reflection Execution

Parallel to the main response cycle, after the FastAPI server responds to the client, the following asynchronous task flow triggers:

```mermaid
flowchart TD
    Start[FastAPI Server Response Finished] --> Spawn[Spawn Background Tasks]
    Spawn --> Task1[Memory Judger Task]
    Spawn --> Task2[Reflection Engine Task]
    
    Task1 --> JudgerLLM[LLM call: Is turn worth remembering?]
    JudgerLLM -->|Score >= 7| WriteFAISS[Write to FAISS vector index]
    WriteFAISS --> DebounceSave[Debounced write to vector_store.bin]
    
    Task2 --> ReflectionLLM[LLM call: Extract preferences & entity mutations]
    ReflectionLLM --> WriteWG[Write nodes & edges to WorldGraph JSON]
    WriteWG --> SaveWG[Write to world_graph.json]
```
