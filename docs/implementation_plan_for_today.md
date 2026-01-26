# Sakura V17: Production-Grade Execution Architecture

> **Audit Date:** January 19, 2026  
> **Reviewed System:** Sakura V10-V16.2  
> **Status:** Requires architectural intervention  
> **Revision:** v2.1 (production-hardened with 8-point review)

---

## Executive Diagnosis (Blunt)

Your system has **good bones** but suffers from **execution mode confusion**. The core problems:

| Problem | Root Cause | Impact |
|---------|------------|--------|
| **80s+ latency** | ReAct loop runs unconditionally, even for trivial requests | Unusable UX |
| **Planner called when unnecessary** | No gating logic before `ReActLoop.run()` | Wasted LLM calls |
| **Terminal actions don't stop the loop** | V17 removed break on terminal (for "multi-tool chains") | Infinite loops |
| **ToolMessage validation error** | `status=None` passed when tool execution fails silently | Crashes |
| **Frontend shows nothing** | SSE message not properly emitted after tool execution | Silent failures |

> [!CAUTION]
> **The ReAct loop is your execution default.** This is backwards. ReAct should be the *exception*, not the rule.

### Critical Corrections (v2.1)

Based on 8-point production review, these issues must be addressed:

| # | Issue | v2.0 Gap | v2.1 Correction |
|---|-------|----------|-----------------|
| 1 | Mode leaks implicitly | Mode inferred locally | **`ExecutionContext` threaded everywhere** |
| 2 | Terminal is tool-based | `is_terminal(tool_name)` | **Plan-relative: `final: true` tag on last step** |
| 3 | ONE_SHOT creeps toward planner | LLM fallback for args | **No LLM in ONE_SHOT. Regex-only, fail to ITERATIVE** |
| 4 | Router confidence undefined | `confidence` field | **Remove confidence. Deterministic heuristics only** |
| 5 | Sync wrapper dangerous | `run_until_complete` | **Async-only core. Sync only at HTTP boundary** |
| 6 | Message double-emit | Finally block | **`ResponseEmitter` with state guard** |
| 7 | Partial = success | `success=True` on timeout | **`ExecutionStatus` enum: SUCCESS/PARTIAL/FAILED** |
| 8 | Reference resolution races | Live graph access | **`GraphSnapshot` at dispatcher entry** |

---

## 1. The Correct Mental Model

```
  User Input
      │
      ▼
  ┌─────────────────────────┐
  │     Forced Router       │  ← Regex bypass (0ms)
  │   [time, bye, lol]      │
  └─────────┬───────────────┘
            │
            ▼
  ┌─────────────────────────┐
  │    SmartRouter (LLM)    │  ← Classifies: CHAT / DIRECT / PLAN
  │    (300-800ms)          │
  └─────────┬───────────────┘
            │
   ┌────────┼────────┐
   ▼        ▼        ▼
 CHAT    DIRECT    PLAN
   │        │        │
   │        │        │
   ▼        ▼        ▼
┌──────┐ ┌──────────────┐ ┌─────────────────────┐
│ LLM  │ │ ONE_SHOT     │ │ ITERATIVE ReAct     │
│ Only │ │ (1 tool)     │ │ (capped, budgeted)  │
└──────┘ └──────────────┘ └─────────────────────┘
   │        │                     │
   └────────┴─────────────────────┘
                    │
                    ▼
            ┌─────────────┐
            │  Responder  │
            │  (always)   │
            └─────────────┘
```

### The Three Execution Modes

| Mode | Trigger | Behavior | Max LLM Calls |
|------|---------|----------|---------------|
| **CHAT** | No tools needed | Skip executor entirely → Responder | 2 (Router + Responder) |
| **ONE_SHOT** | Single obvious tool (hint provided) | Execute 1 tool directly, no planner | 3 (Router + Tool + Responder) |
| **ITERATIVE** | Multi-step, research, ambiguous | ReAct loop with hard cap | 2 + N×2 (max 5 iterations = 12) |

> [!IMPORTANT]
> **ONE_SHOT is your fast lane.** 80% of tool requests should hit this path.

---

## 2. What's Wrong in Your Current Code

### 2.1 Executor Always Runs ReAct

```python
# Current: executor.py:815-827
def execute(self, user_input: str, route_result: Any, graph_context: str, state: Any = None):
    if not self.react_loop:
        return ExecutionResult("Error: No planner configured", [], "Error", None, False)
        
    return self.react_loop.run(  # ← ALWAYS runs ReAct!
        user_input=user_input,
        graph_context=graph_context,
        available_tools=self.tools,
        state=state
    )
```

**Fix:** Executor must check `route_result.classification` and branch:
- `DIRECT` → `one_shot_execute()`
- `PLAN` → `react_loop.run()` (with cap)

### 2.2 ReAct Loop Doesn't Respect Terminal Actions

```python
# Current: executor.py:537-538
if self.policy.is_terminal(final_tool_used) and exec_result.success:
    print(f"✅ [ReActLoop] Terminal action '{final_tool_used}' completed")
    # ← NO BREAK! Loop continues
```

This was intentional ("V17 multi-tool chains") but is wrong. Terminal means *terminal*.

### 2.3 Planner Called for Every Iteration

```python
# Current: executor.py:511-517
plan_result = self.planner.plan(
    user_input=user_input,
    context=graph_context,
    tool_history=all_tool_messages,
    available_tools=available_tools
)
```

For a simple "open VS Code" request, the planner is called, which takes 2-3 seconds. But the Router already provided `tool_hint="open_app"`. **Use it.**

### 2.4 Router Misclassifies Complex Queries

```python
# From flight_recorder.jsonl:
# Query: "Open VS Code, play i believe i can fly on youtube, play no friends on spotify..."
# Router: DIRECT (hint: spotify_control)  ← WRONG!
```

The router's `_is_action_command()` checks for `" and "` but the query uses commas. Fixed in V17.1 but comma detection is too aggressive.

---

## 3. Proposed Execution Architecture (v2.0 Corrected)

### 3.1 New Class: `ExecutionDispatcher`

This replaces the current `ToolExecutor.execute()` facade.

```python
from enum import Enum
from typing import Optional
from dataclasses import dataclass


class ExecutionMode(Enum):
    CHAT = "chat"
    ONE_SHOT = "one_shot"
    ITERATIVE = "iterative"


@dataclass
class RouteResult:
    classification: str  # CHAT, DIRECT, PLAN
    tool_hint: Optional[str]
    urgency: str
    confidence: float = 1.0  # v2.0: Added for gating


class ExecutionDispatcher:
    """
    Single Responsibility: Decide HOW to execute, then delegate.
    
    v2.0 Corrections:
        - Confidence gating before ONE_SHOT
        - Tool sanity check before trusting Router
        - Async-first design with sync fallback
    """
    
    # v2.0: Minimum confidence to trust ONE_SHOT
    ONE_SHOT_CONFIDENCE_THRESHOLD = 0.75
    
    def __init__(
        self, 
        one_shot_runner: "OneShotRunner",
        react_loop: "ReActLoop",
        tools: list
    ):
        self.one_shot_runner = one_shot_runner
        self.react_loop = react_loop
        self.tools = tools
        self.tool_names = {t.name for t in tools}
    
    async def adispatch(
        self, 
        user_input: str, 
        route_result: RouteResult,
        graph_context: str,
        state: "AgentState"
    ) -> "ExecutionResult":
        """Async dispatch - preferred path."""
        
        mode = self._determine_mode(route_result)
        
        if mode == ExecutionMode.CHAT:
            return ExecutionResult.empty()
        
        elif mode == ExecutionMode.ONE_SHOT:
            return await self.one_shot_runner.aexecute(
                tool_name=route_result.tool_hint,
                user_input=user_input,
                graph_context=graph_context
            )
        
        elif mode == ExecutionMode.ITERATIVE:
            return await self.react_loop.arun(
                user_input=user_input,
                graph_context=graph_context,
                available_tools=self.tools,
                state=state
            )
    
    def dispatch(self, ...) -> "ExecutionResult":
        """Sync dispatch - wraps async for compatibility."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self.adispatch(...)
        )
    
    def _determine_mode(self, route_result: RouteResult) -> ExecutionMode:
        """
        Mode determination with v2.0 safety valves.
        
        INVARIANT: CHAT → CHAT (no execution)
        INVARIANT: DIRECT + tool_hint + confident + valid_tool → ONE_SHOT
        INVARIANT: Otherwise → ITERATIVE (safe fallback)
        """
        if route_result.classification == "CHAT":
            return ExecutionMode.CHAT
        
        # v2.0: ONE_SHOT only if ALL conditions met
        if route_result.classification == "DIRECT" and route_result.tool_hint:
            # Safety valve 1: Confidence check
            if route_result.confidence < self.ONE_SHOT_CONFIDENCE_THRESHOLD:
                print(f"⚠️ [Dispatcher] Low confidence ({route_result.confidence:.2f}), downgrading to ITERATIVE")
                return ExecutionMode.ITERATIVE
            
            # Safety valve 2: Tool exists check
            if route_result.tool_hint not in self.tool_names:
                print(f"⚠️ [Dispatcher] Tool '{route_result.tool_hint}' not found, downgrading to ITERATIVE")
                return ExecutionMode.ITERATIVE
            
            return ExecutionMode.ONE_SHOT
        
        # PLAN or DIRECT without hint → safe fallback
        return ExecutionMode.ITERATIVE
```

### 3.2 New Class: `OneShotRunner` (v2.0 with LLM Fallback)

Executes a single tool without invoking the Planner. Uses cheap arg extraction with LLM fallback for reliability.

```python
import re
from typing import Dict, Optional
from langchain_core.messages import ToolMessage, SystemMessage, HumanMessage


class OneShotRunner:
    """
    Execute a single, pre-determined tool call.
    
    v2.0 Corrections:
        - Two-tier arg extraction: regex first, cheap LLM fallback
        - Async-native with sync wrapper
        - Terminal behavior is ALWAYS true (mode-aware)
    """
    
    # v2.0: Arg extraction prompt for fallback
    ARG_EXTRACT_PROMPT = """Extract ONLY the arguments for the tool "{tool_name}".
Tool schema: {tool_schema}
User input: {user_input}

Return ONLY a JSON object with the required arguments. No explanation."""
    
    def __init__(
        self, 
        tool_runner: "ToolRunner", 
        output_handler: "OutputHandler",
        cheap_llm: Optional["ReliableLLM"] = None  # v2.0: For arg extraction
    ):
        self.tool_runner = tool_runner
        self.output_handler = output_handler
        self.cheap_llm = cheap_llm  # 8B model, same as Router
    
    async def aexecute(
        self, 
        tool_name: str, 
        user_input: str, 
        graph_context: str
    ) -> "ExecutionResult":
        """Async execution path."""
        
        # v2.0: Two-tier arg extraction
        args = self._extract_args_regex(tool_name, user_input)
        
        if not args or self._args_incomplete(tool_name, args):
            # Fallback to cheap LLM
            args = await self._extract_args_llm(tool_name, user_input)
        
        # Run single tool (async)
        result = await self.tool_runner.arun(tool_name, args, user_input)
        
        # Process output
        output = self.output_handler.intercept_large_output(
            result.output, tool_name
        )
        
        # Create single ToolMessage (v2.0: status never None)
        tool_msg = ToolMessage(
            tool_call_id=f"oneshot_{tool_name}",
            content=output,
            name=tool_name,
            status="success" if result.success else "error"
        )
        
        return ExecutionResult(
            outputs=output,
            tool_messages=[tool_msg],
            tool_used=tool_name,
            last_result={"tool": tool_name, "args": args, "output": output, "success": result.success},
            success=result.success
        )
    
    def execute(self, ...) -> "ExecutionResult":
        """Sync wrapper for compatibility."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self.aexecute(...)
        )
    
    def _extract_args_regex(self, tool_name: str, user_input: str) -> Dict:
        """
        Fast regex extraction for common patterns.
        Returns empty dict if unsure (triggers LLM fallback).
        """
        text = user_input.lower()
        
        if tool_name == "open_app":
            match = re.search(r'open\s+(.+?)(?:\s*,|$)', user_input, re.I)
            if match:
                return {"app_name": match.group(1).strip()}
        
        elif tool_name == "spotify_control":
            if "play" in text:
                match = re.search(r'play\s+(.+?)(?:\s+on\s+spotify)?(?:\s*,|$)', user_input, re.I)
                if match:
                    return {"action": "play", "query": match.group(1).strip()}
            elif "pause" in text or "stop" in text:
                return {"action": "pause"}
        
        elif tool_name == "play_youtube":
            match = re.search(r'play\s+(.+?)\s+on\s+youtube', user_input, re.I)
            if match:
                return {"topic": match.group(1).strip()}
        
        elif tool_name == "get_weather":
            match = re.search(r'weather\s+(?:in\s+)?(.+)', user_input, re.I)
            if match:
                return {"location": match.group(1).strip()}
        
        elif tool_name == "set_timer":
            match = re.search(r'(\d+)\s*(min|sec|hour)', user_input, re.I)
            if match:
                return {"duration": int(match.group(1)), "unit": match.group(2)}
        
        # Fallback: return empty to trigger LLM
        return {}
    
    def _args_incomplete(self, tool_name: str, args: Dict) -> bool:
        """Check if extracted args are missing required fields."""
        required_fields = {
            "open_app": ["app_name"],
            "spotify_control": ["action"],
            "play_youtube": ["topic"],
            "get_weather": ["location"],
            "web_search": ["query"],
        }
        required = required_fields.get(tool_name, [])
        return any(f not in args or not args[f] for f in required)
    
    async def _extract_args_llm(self, tool_name: str, user_input: str) -> Dict:
        """
        Cheap LLM fallback for arg extraction.
        Uses the 8B router model - fast and cheap.
        """
        if not self.cheap_llm:
            # No LLM available, return best-effort
            return {"query": user_input}
        
        try:
            # Get tool schema if available
            tool_schema = "See tool definition"  # Could fetch actual schema
            
            prompt = self.ARG_EXTRACT_PROMPT.format(
                tool_name=tool_name,
                tool_schema=tool_schema,
                user_input=user_input
            )
            
            response = await self.cheap_llm.ainvoke([
                SystemMessage(content="You extract tool arguments. JSON only."),
                HumanMessage(content=prompt)
            ])
            
            # Parse JSON response
            import json
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1].strip()
                if content.startswith("json"):
                    content = content[4:].strip()
            
            return json.loads(content)
            
        except Exception as e:
            print(f"⚠️ [OneShotRunner] LLM arg extraction failed: {e}")
            return {"query": user_input}
```

### 3.3 Modified ReAct Loop (v2.0 Corrected)

```python
import time
import asyncio
from typing import List, Dict, Any


class ReActLoop:
    """
    v2.0 Corrections:
        - Aggressive latency budgets (8-10s default)
        - Mode-aware terminal semantics
        - Async-first with proper timeout handling
        - Partial result summarization on timeout
    """
    
    MAX_ITERATIONS = 3  # Down from 5
    
    # v2.0: Aggressive budgets for desktop UX
    LATENCY_BUDGETS = {
        "default": 8_000,      # 8s for normal queries
        "research": 20_000,    # 20s for explicit research
    }
    ITERATION_TIMEOUT_MS = 5_000  # 5s per iteration max
    
    # v2.0: Hard terminals that ALWAYS stop (regardless of mode)
    HARD_TERMINALS = {"shutdown", "exit", "kill_process"}
    
    def __init__(
        self,
        planner: "Planner",
        tool_runner: "ToolRunner",
        output_handler: "OutputHandler",
        policy: "ExecutionPolicy"
    ):
        self.planner = planner
        self.tool_runner = tool_runner
        self.output_handler = output_handler
        self.policy = policy
    
    async def arun(
        self,
        user_input: str,
        graph_context: str,
        available_tools: List,
        state: "AgentState"
    ) -> "ExecutionResult":
        """Async ReAct loop with hard time bounds."""
        
        all_tool_messages = []
        all_outputs = []
        final_tool_used = "None"
        final_last_result = None
        
        # v2.0: Determine budget based on query type
        budget_ms = self._get_budget(user_input)
        start_time = time.time()
        
        print(f"🔄 [ReActLoop] Starting (budget: {budget_ms}ms)")
        
        for iteration in range(self.MAX_ITERATIONS):
            elapsed_ms = (time.time() - start_time) * 1000
            
            # HARD STOP: Total budget exceeded
            if elapsed_ms > budget_ms:
                print(f"⏱️ [ReActLoop] Budget exceeded ({elapsed_ms:.0f}ms > {budget_ms}ms)")
                # v2.0: Summarize partial results instead of empty return
                if all_outputs:
                    return self._build_partial_result(all_outputs, all_tool_messages)
                break
            
            # 1. PLAN (with per-iteration timeout)
            try:
                plan_result = await asyncio.wait_for(
                    self.planner.aplan(
                        user_input=user_input,
                        context=graph_context,
                        tool_history=all_tool_messages,
                        available_tools=available_tools
                    ),
                    timeout=self.ITERATION_TIMEOUT_MS / 1000
                )
            except asyncio.TimeoutError:
                print(f"⏱️ [ReActLoop] Planner timeout at iteration {iteration + 1}")
                break
            
            steps = plan_result.get("steps", [])
            
            # HARD STOP: No steps = complete
            if not steps:
                print("⏹️ [ReActLoop] No more steps - complete")
                break
            
            # 2. EXECUTE (async)
            exec_result = await self._aexecute_steps(steps, user_input, state)
            
            # 3. OBSERVE
            all_tool_messages.extend(exec_result.tool_messages)
            if exec_result.outputs:
                all_outputs.append(exec_result.outputs)
            
            final_tool_used = exec_result.tool_used
            final_last_result = exec_result.last_result
            
            # v2.0: Mode-aware terminal check
            if self._is_terminal_for_mode(exec_result.tool_used, exec_result.success):
                print(f"✅ [ReActLoop] Terminal action '{exec_result.tool_used}' - stopping")
                break  # ← v2.0: RESTORED!
        
        return ExecutionResult(
            outputs="\n".join(all_outputs),
            tool_messages=all_tool_messages,
            tool_used=final_tool_used,
            last_result=final_last_result,
            success=True
        )
    
    def _get_budget(self, user_input: str) -> int:
        """Determine latency budget based on query type."""
        research_keywords = ["research", "compare", "summarize", "analyze", "deep dive"]
        if any(kw in user_input.lower() for kw in research_keywords):
            return self.LATENCY_BUDGETS["research"]
        return self.LATENCY_BUDGETS["default"]
    
    def _is_terminal_for_mode(self, tool_name: str, success: bool) -> bool:
        """
        v2.0: Terminal semantics are mode-aware.
        
        In ITERATIVE mode:
            - HARD_TERMINALS always stop
            - Regular terminals (play, open) stop ONLY if successful
        """
        if not success:
            return False
        
        if tool_name in self.HARD_TERMINALS:
            return True
        
        # In ITERATIVE mode, regular terminals stop on success
        return self.policy.is_terminal(tool_name)
    
    def _build_partial_result(
        self, 
        outputs: List[str], 
        tool_messages: List
    ) -> "ExecutionResult":
        """Build result from partial execution when budget exceeded."""
        return ExecutionResult(
            outputs="\n".join(outputs) + "\n[Execution time limit reached - partial results]",
            tool_messages=tool_messages,
            tool_used=tool_messages[-1].name if tool_messages else "None",
            last_result=None,
            success=True  # Partial success is still success
        )
    
    async def _aexecute_steps(self, steps: List[Dict], user_input: str, state) -> "ExecutionResult":
        """Execute steps asynchronously (existing implementation)."""
        # ... (keep existing implementation, ensure status is never None)
        pass
```

### 3.4 Guaranteed Message Emission Pattern (v2.0)

This pattern ensures the frontend ALWAYS receives exactly one assistant message:

```python
# In SmartAssistant.arun() - the main pipeline

async def arun(self, user_input: str, history: List[Dict], ...) -> Dict[str, Any]:
    """
    v2.0: Guaranteed message emission via finally block.
    
    INVARIANT: Every request emits exactly 1 assistant message.
    """
    response = None  # Will be set in try or except
    response_metadata = {"status": "unknown"}
    
    try:
        # ... routing, execution ...
        
        exec_result = await self.dispatcher.adispatch(
            user_input, route_result, planner_ctx, state
        )
        
        response = await self.responder.agenerate(resp_context)
        response_metadata = {"status": "success", "latency": f"{elapsed:.2f}s"}
        
    except RateLimitExceeded:
        response = "I'm working too hard and hit a rate limit. Please try again in a moment."
        response_metadata = {"status": "rate_limited"}
        
    except Exception as e:
        print(f"❌ Pipeline Error: {e}")
        response = f"I encountered an error: {e}"
        response_metadata = {"status": "error"}
        
    finally:
        # v2.0: GUARANTEED emission - never skip this
        if response is None:
            response = "Something went wrong. Please try again."
            response_metadata = {"status": "unknown_error"}
        
        # Emit to frontend (SSE/WebSocket)
        await self._emit_assistant_message(response, response_metadata)
        
        # Return value for API response
        return {
            "content": response,
            "mode": route_result.classification if 'route_result' in locals() else "ERROR",
            "metadata": response_metadata
        }
```
```

---

## 4. Router Improvements

### 4.1 Better Complex Query Detection

```python
def _is_complex_multi_step(self, text: str) -> bool:
    """
    Detect queries that need PLAN, not DIRECT.
    
    Patterns:
        - Multiple action verbs
        - Sequential connectors ("then", "after that", "and also")
        - Research indicators ("research", "compare", "summarize")
    """
    text_lower = text.lower()
    
    # Count action verbs
    action_verbs = ["play", "open", "search", "create", "send", "set", "find"]
    verb_count = sum(1 for v in action_verbs if v in text_lower)
    
    if verb_count >= 2:
        return True
    
    # Sequential connectors
    if any(seq in text_lower for seq in [" and ", " then ", ", then ", " after that"]):
        return True
    
    # Research patterns
    if any(r in text_lower for r in ["research", "compare", "summarize", "analyze"]):
        return True
    
    return False
```

### 4.2 Route Classification Update

```python
def route(self, query: str, ...) -> RouteResult:
    # 1. Check complexity BEFORE action command check
    if self._is_complex_multi_step(query):
        print(f"🔀 [Router] Complex multi-step detected, forcing PLAN")
        return RouteResult("PLAN", None, get_urgency(query))
    
    # 2. Then check for single action commands
    if self._is_action_command(query):
        print(f"⚡ [Router] Single action detected, forcing DIRECT")
        return RouteResult("DIRECT", self._guess_tool_hint(query), get_urgency(query))
    
    # 3. Fall through to LLM classification
    ...
```

---

## 5. Hard Rules / Invariants

These MUST be enforced in code:

### Execution Invariants

| Invariant | Location | Enforcement |
|-----------|----------|-------------|
| **CHAT never invokes Executor** | `SmartAssistant.run()` | Check `route_result.classification == "CHAT"` |
| **ONE_SHOT never calls Planner** | `ExecutionDispatcher` | Branch to `OneShotRunner` |
| **Terminal action ends ReAct immediately** | `ReActLoop._execute_steps()` | Break on terminal + success |
| **ReAct capped at 3 iterations** | `ReActLoop.run()` | `range(3)` + break checks |
| **30s total budget for execution** | `ReActLoop.run()` | `time.time()` check |

### Frontend Invariants

| Invariant | Location | Enforcement |
|-----------|----------|-------------|
| **Every request emits exactly 1 assistant message** | `server.py` | SSE emit before return |
| **Tool results always have `status`** | `ToolMessage` construction | Default to `"error"` if None |
| **Frontend polls for refresh** | Svelte store | `setInterval` on message list |

### WorldGraph Invariants (Already Documented)

| Invariant | Current State |
|-----------|---------------|
| `user:self` immutable | ✅ Enforced |
| LLM_INFERRED never auto-promoted | ✅ Enforced |
| External search banned for user references | ✅ Enforced |

---

## 6. WorldGraph Refactor Recommendations

### Current State

WorldGraph is 1880 lines and does:
- Identity management
- Reference resolution
- Memory storage
- Action recording
- Garbage collection
- EQ layer (intent inference)
- Self-check validation
- Context generation for Planner/Responder
- Temporal decay
- Compression

### Recommendation: Split into 4 Components

```
WorldGraph (Current: 1880 LOC)
    │
    └── Split into:
        │
        ├── IdentityStore (200 LOC)
        │   - user:self management
        │   - pref:* management
        │   - get_user_identity()
        │   - is_user_reference()
        │
        ├── ReferenceResolver (300 LOC)
        │   - resolve_reference()
        │   - get_last_action()
        │   - pronoun handling ("this", "that", "again")
        │
        ├── MemoryIndex (400 LOC)
        │   - entities: Dict[str, EntityNode]
        │   - actions: List[ActionNode]
        │   - record_action()
        │   - get_recent_actions()
        │   - garbage_collect()
        │
        └── ContextBuilder (300 LOC)
            - get_context_for_planner()
            - get_context_for_responder()
            - summarize_recent_activity()
```

### What Must Stay Synchronous

| Component | Sync/Async | Reason |
|-----------|------------|--------|
| `IdentityStore.get_user_identity()` | **Sync** | Called in hot path, must be <1ms |
| `ReferenceResolver.resolve_reference()` | **Sync** | CPU-bound regex, <5ms |
| `ContextBuilder.get_context_for_*()` | **Sync** | Pure computation, <10ms |

### What Can Be Async/Lazy

| Component | Strategy |
|-----------|----------|
| `MemoryIndex.garbage_collect()` | Run in background task every 60s |
| `MemoryIndex.run_compression()` | Run after response, before next request |
| Embedding computation | Lazy-load on semantic search only |
| Disk persistence (`save()`) | Use `asyncio.to_thread()` |

### What Should Never Be in Critical Path

| Operation | Current Location | Fix |
|-----------|------------------|-----|
| `save()` | End of every request | Move to background task |
| `run_compression()` | `advance_turn()` | Move to 1-minute cron |
| Embedding generation | On entity creation | Lazy-load on first semantic query |

### v2.0 Critical: ContextBuilder Must Be Pure

> [!WARNING]
> **ContextBuilder must be a pure function. Zero side effects. No mutations.**

Current `WorldGraph.get_context_for_*()` methods may:
- Update recency timestamps
- Touch access counters
- Infer preferences

**This is dangerous.** It couples read operations to write operations.

**Hard Rule:**

```python
class ContextBuilder:
    """
    PURE FUNCTION: Read-only context generation.
    
    INVARIANT: This class NEVER mutates any state.
    INVARIANT: Calling any method twice returns identical results.
    INVARIANT: No side effects, no logging to state, no promotions.
    """
    
    def __init__(self, identity_store, memory_index, reference_resolver):
        # Injected dependencies (read-only access)
        self._identity = identity_store
        self._memory = memory_index
        self._resolver = reference_resolver
    
    def get_context_for_planner(self, query: str, budget: int = 500) -> str:
        """Pure: builds context string, no mutations."""
        # ... read-only operations ...
        pass
    
    def get_context_for_responder(self) -> str:
        """Pure: builds context string, no mutations."""
        # ... read-only operations ...
        pass
```

All mutations (recency updates, promotions, decay) happen:
- **After responder** completes
- **In background tasks**
- **Via explicit `MemoryIndex.record_*()` calls**

---

## 7. Step-by-Step Implementation Plan

### Phase 1: Fix Immediate Bugs (Day 1)

- [ ] **Fix ToolMessage validation error**
  - File: `executor.py` line 632-637, 718-723
  - Change: Ensure `status` is never `None`
  ```python
  status="error" if not run_result.success else "success"
  ```

- [ ] **Restore terminal action break in ReAct**
  - File: `executor.py` line 537-538 and 591-592
  - Change: Add `break` after terminal action log

- [ ] **Cap ReAct to 3 iterations**
  - File: `executor.py` line 485
  - Change: `max_iterations: int = 3`

---

### Phase 2: Implement Execution Modes (Day 2-3)

- [ ] **Create `OneShotRunner` class**
  - New file: `backend/sakura_assistant/core/oneshot_runner.py`
  - Implement `execute()` and `_extract_args()`

- [ ] **Create `ExecutionDispatcher` class**
  - New file: `backend/sakura_assistant/core/execution_dispatcher.py`
  - Implement `dispatch()` and `_determine_mode()`

- [ ] **Update `SmartAssistant` to use dispatcher**
  - File: `llm.py` lines 158-188 and 344-368
  - Replace: `self.executor.execute()` → `self.dispatcher.dispatch()`

---

### Phase 3: Router Improvements (Day 3)

- [ ] **Add `_is_complex_multi_step()` to Router**
  - File: `router.py` after line 236
  - Call before `_is_action_command()`

- [ ] **Update `_is_action_command()` to exclude complex queries**
  - File: `router.py` line 203
  - Keep the comma/and/then check but improve logic

---

### Phase 4: Latency Budget (Day 4)

- [ ] **Add time tracking to ReAct loop**
  - File: `executor.py` lines 500-546
  - Add: `start_time`, `elapsed_ms` checks, budget constants

- [ ] **Add per-iteration timeout**
  - Wrap planner call in `asyncio.wait_for()` with 10s timeout

---

### Phase 5: WorldGraph Split (Day 5-7)

- [ ] **Extract `IdentityStore`**
  - New file: `backend/sakura_assistant/core/identity_store.py`
  - Move: `_initialize_identity()`, `get_user_identity()`, `is_user_reference()`

- [ ] **Extract `ReferenceResolver`**
  - New file: `backend/sakura_assistant/core/reference_resolver.py`
  - Move: `resolve_reference()`, `_lookup_entity_by_name()`, `get_last_action()`

- [ ] **Make WorldGraph a thin coordinator**
  - Update: `world_graph.py` to delegate to new components
  - Keep: Thread-safety (RLock), singleton pattern

---

### Phase 6: Frontend SSE Fix (Day 7)

- [ ] **Audit `server.py` SSE emission**
  - Ensure every path emits `assistant_message` event
  - Add: Explicit emit before return in error handlers

- [ ] **Add frontend polling fallback**
  - If no SSE message for 5s after tool execution, trigger refresh

---

## 8. Alternative Architecture (Simpler)

If the above is too much work, consider this simpler approach:

### Option B: "Dumb Router" Pattern

Remove mode classification entirely. Make every request follow:

```
Request → Extract Tools → Execute All → Respond
```

Use the existing Planner for *every* request, but:
1. Set `max_iterations=1` for simple queries
2. Let the LLM decide tools in a single pass
3. Execute all tools returned, no loop

This is how Claude and GPT-4 work (function calling without iterative planning).

**Pros:**
- Simpler code
- Single code path
- LLM handles complexity detection

**Cons:**
- Slightly higher latency for simple requests (Planner always called)
- Less predictable

---

## 9. Success Metrics

After implementation, verify:

| Metric | Current | Target |
|--------|---------|--------|
| Simple query latency (CHAT) | 1-2s | <1s |
| Single tool latency (DIRECT) | 3-6s | <2s |
| Multi-tool latency (PLAN) | 30-80s | <15s |
| ReAct iterations for simple queries | 1-5 | 0 (ONE_SHOT) |
| Frontend message render rate | ~80% | 100% |

---

## 10. Codebase De-Bloating & Organization

### Bloat Analysis (Lines of Code)

| File | LOC | Status | Issue |
|------|-----|--------|-------|
| `world_graph.py` | 1837 | 🔴 **Critical** | God object. Needs split into 4 components |
| `executor.py` | 808 | 🟡 **High** | Will shrink after OneShotRunner extraction |
| `scheduler.py` | 763 | 🟡 **High** | 500 lines are calendar tool duplications |
| `wake_word.py` | 664 | 🟢 **OK** | Self-contained, DSP-specific |
| `faiss_store/store.py` | 635 | 🟡 **High** | Mixes FAISS + conversation history |
| `llm.py` | 461 | 🟡 **Medium** | SmartAssistant will shrink after dispatcher extraction |
| `config.py` | 427 | 🔴 **Critical** | Prompts embedded in config! |
| `flight_recorder.py` | 421 | 🟢 **OK** | Clean observability layer |
| `forced_router.py` | 370 | 🟢 **OK** | Just pattern data + functions |
| `identity_manager.py` | 320 | 🟡 **Medium** | Duplicates WorldGraph identity logic |

### Critical De-Bloating Tasks

#### 10.1 Split `config.py` (427 LOC → 150 LOC)

**Problem:** System prompts are embedded in config.py as giant multi-line strings.

**Current structure:**
```python
# config.py lines 160-380
SYSTEM_PROMPT = """..."""  # 80 lines
RESPONDER_PROMPT = """..."""  # 40 lines
ROUTER_SYSTEM_PROMPT = """..."""  # 30 lines
VERIFIER_PROMPT = """..."""  # 20 lines
MEMORY_JUDGER_PROMPT = """..."""  # 15 lines
```

**Fix:**
```
config.py (150 LOC) - Pure configuration
prompts/
├── system.txt
├── responder.txt
├── router.txt
├── verifier.txt
├── memory_judger.txt
└── __init__.py  # load_prompt("responder")
```

**New loader:**
```python
# prompts/__init__.py
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.txt").read_text()
```

---

#### 10.2 Merge `identity_manager.py` into WorldGraph Split

**Problem:** `IdentityManager` (320 LOC) duplicates `WorldGraph` identity logic.

**Current:**
```
identity_manager.py → loads from user_settings.json
world_graph.py → has user:self entity
```

**These should be the same thing.**

**Fix:** When splitting WorldGraph:
- `IdentityStore` replaces `IdentityManager`
- `IdentityManager` becomes a thin facade that delegates to `IdentityStore`
- Delete duplicate `check_claim()` logic

---

#### 10.3 De-duplicate `scheduler.py` (763 LOC → 300 LOC)

**Problem:** Lines 340-750 contain calendar tool implementations that should be in `tools_libs/`.

**Current structure:**
```python
class Scheduler:  # Lines 47-251 (core scheduler - KEEP)
    ...

# Lines 278-763 (calendar tools - MOVE)
def remind_me(...): ...
def schedule_morning_briefing(...): ...
def memory_maintenance(...): ...
class CalendarTool: ...
class SmartCalendarResolver: ...
```

**Fix:**
1. Keep `Scheduler` class in `scheduler.py`
2. Move calendar tool implementations to `tools_libs/calendar.py`
3. Move `memory_maintenance` to `memory/maintenance.py`

---

#### 10.4 Split `faiss_store/store.py` (635 LOC → 400 LOC)

**Problem:** Mixes vector memory with conversation history management.

**Current:**
```python
class VectorMemoryStore:
    # Vector operations (lines 84-550) - KEEP HERE
    def add_message(...)
    def get_context_for_query(...)
    
    # Conversation history (lines 298-404) - SHOULDN'T BE HERE
    def _load_conversation(...)
    def append_to_history(...)
    def get_full_history(...)
```

**Fix:**
```
faiss_store/
├── store.py              # VectorMemoryStore (vector ops only)
└── conversation_store.py  # ConversationStore (history management)
```

---

#### 10.5 Clean Up Redundant Memory Layers

**Problem:** Memory is spread across too many files:

```
memory/
├── faiss_store/store.py       # Vector memory + conversation
├── memory_coordinator.py       # Unified interface
├── summary_memory.py           # Summary generation
├── ephemeral_cache.py         # Temp storage
├── chroma_store/              # Unused?
├── ingestion/                 # File ingestion
└── router.py                  # Memory routing??
```

**Questions to answer:**
1. Is `chroma_store/` used? If not, delete.
2. Why is there a `memory/router.py`? Merge with `memory_coordinator.py`.
3. Is `summary_memory.py` used? Check references.

**Audit needed:**
```python
# Check for imports
grep -r "from.*chroma_store" backend/
grep -r "summary_memory" backend/
grep -r "memory.router" backend/
```

---

#### 10.6 Consolidate Cognitive Layer

**Current:**
```
core/cognitive/
├── desire.py    # 315 LOC - Mood tracking
├── proactive.py # Unknown size
├── state.py     # Unknown size
└── __init__.py
```

**Question:** Is cognitive layer actively used, or is it an experiment?

If used: Keep as-is (self-contained).
If not: Archive to `_archive/cognitive/`.

---

### File Movement Summary

| From | To | Reason |
|------|----|--------|
| `config.py` prompts | `prompts/*.txt` | Separation of concerns |
| `scheduler.py` calendar tools | `tools_libs/calendar.py` | SRP |
| `scheduler.py` memory_maintenance | `memory/maintenance.py` | SRP |
| `identity_manager.py` | Merge into `IdentityStore` | Deduplication |
| `faiss_store/store.py` history | `faiss_store/conversation_store.py` | SRP |
| `memory/router.py` | Merge into `memory_coordinator.py` | Consolidation |

### Files to Audit for Deletion

| File | Check |
|------|-------|
| `chroma_store/` | Is it imported anywhere? |
| `core/micro_toolsets.py` | Still used after forced_router? |
| `core/ingest_state.py` | Necessary or legacy? |
| `memory/router.py` | Duplicate of memory_coordinator? |

---

## 11. v2.1 Implementation Priority

### Must-Have (Production Blockers)

1. **ExecutionContext threading** - Mode must be explicit everywhere
2. **ResponseEmitter with state guard** - Stop double-emissions
3. **ExecutionStatus enum** - Partial ≠ Success
4. **GraphSnapshot at dispatcher** - Stop reference races
5. **Remove sync wrappers** - Async-only core

### Should-Have (Major UX)

6. **OneShotRunner (regex-only)** - Fast lane for simple tools
7. **Plan-relative terminal (`final: true`)** - Multi-tool chains work
8. **Deterministic mode selection** - No confidence guessing

### Nice-to-Have (Organization)

9. **De-bloat config.py** - Extract prompts
10. **De-bloat scheduler.py** - Move calendar tools
11. **WorldGraph split** - Can defer if time-constrained

---

## Summary

1. **Your architecture is fundamentally sound.** Router → Executor → Responder is correct.
2. **The bug is behavioral:** ReAct runs when it shouldn't.
3. **Fix priority:** Execution modes > Terminal breaks > Latency budget > WorldGraph split > De-bloating
4. **Don't over-engineer:** The Dumb Router pattern might be simpler if you're time-constrained.
5. **Codebase is moderately bloated** (~3000 LOC can be removed/reorganized without losing functionality.

---

*Plan generated by: Antigravity Architecture Audit*  
*January 19, 2026 - v2.1*
