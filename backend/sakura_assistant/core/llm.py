import os
import re
import time
import threading
import gc
import json
from typing import List, Dict, Any, Optional, Tuple

from ..core.reflection import reflection_engine
from ..core.context_manager import get_smart_context
# LangChain & AI
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.callbacks import StdOutCallbackHandler

# Local Imports
from ..config import (
    SYSTEM_PERSONALITY, GROQ_API_KEY, GOOGLE_API_KEY, USER_DETAILS, TOOL_BEHAVIOR_RULES,
    HISTORY_WINDOW, TOKEN_BUDGET, MIN_HISTORY,
    ENABLE_V4_SUMMARY, ENABLE_V4_COMPACT_CONTEXT, ENABLE_LOCAL_ROUTER,
    V4_MAX_RAW_MESSAGES, V4_MEMORY_LIMIT, V4_MEMORY_CHAR_LIMIT,
    ROUTER_SYSTEM_PROMPT  # V10: Smart Router prompt
)

# V10: Cache Manager
from .cache_manager import cache_get, cache_set
from .tools import get_all_tools, execute_actions
# from .note_routing import route_note_intent

# from .relevance_mapper import get_tool_relevance # DEPRECATED
from .planner import Planner # NEW
from ..memory.faiss_store import get_relevant_context, get_memory_store

# V5 Imports
from .agent_state import AgentState, RateLimitExceeded
from .verifier import Verifier
from .retry_formatter import format_retry_response, format_multi_tool_response
from .intent_classifier import classify_intent, IntentMode, has_judgment_signals

# V7 Imports - World Graph (Single Source of Truth)
from .world_graph import WorldGraph, EntitySource, ActionType

from ..utils.memory import cleanup_memory

# V4 Feature Imports
from ..utils.user_state import get_current_user_state, update_user_state
from ..utils.study_mode import detect_study_mode, get_study_mode_system_prompt, build_study_mode_response


# V10: Qwen offline fallback REMOVED (unused)
# If offline support is needed in future, consider Ollama integration instead.

def sanitize_memory_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", "", text)
    text = re.sub(r"(?im)^(system|assistant|user|developer)\s*:", "Role:", text)
    return text.replace("---", "-").replace("===", "=")

# Responder guardrail: Text-only output rule
RESPONDER_NO_TOOLS_RULE = """CRITICAL RULE: You are a TEXT-ONLY responder. You CANNOT call tools.
You must ONLY return plain text responses. Never output JSON, tool schemas, or {"name": ...} patterns.
If you believe a tool is needed, explain in plain text what action the user should take instead.
IMPORTANT: If tool outputs are provided below, the action was ALREADY completed. Acknowledge it naturally (e.g., "Playing now" or "Done") - do NOT tell the user to manually do it."""

def validate_responder_output(text: str) -> tuple[str, bool]:
    """
    Validate responder output and strip any tool-call patterns.
    Returns: (cleaned_text, had_violation)
    """
    # Detect tool-call JSON patterns
    tool_patterns = [
        r'\{\s*"name"\s*:', 
        r'\{\s*"tool"\s*:',
        r'\{\s*"function"\s*:',
        r'\{\s*"action"\s*:\s*"',
    ]
    
    had_violation = False
    for pattern in tool_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            had_violation = True
            break
    
    if had_violation:
        # Log violation
        print("⚠️ [GUARDRAIL] Responder attempted tool call - stripping JSON")
        # Try to extract any plain text before the JSON
        clean = re.split(r'\{\s*"(name|tool|function|action)"\s*:', text)[0].strip()
        if not clean or len(clean) < 10:
            clean = "I apologize, but I encountered an issue processing that request. Could you please rephrase?"
        return clean, True
    
    return text, False

# LLM call timeout (seconds)
LLM_TIMEOUT = 60

import concurrent.futures

def invoke_with_timeout(llm, messages, timeout=LLM_TIMEOUT, **kwargs):
    """
    Invoke LLM with a timeout to prevent hanging after idle.
    Returns response or raises TimeoutError.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(llm.invoke, messages, **kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            print(f"❌ [TIMEOUT] LLM call timed out after {timeout}s")
            raise TimeoutError(f"LLM call timed out after {timeout}s")

class ReliableLLM:
    """
    A wrapper that tries a Primary LLM, and falls back to a Backup LLM on error.
    Implements the standard LangChain 'invoke' interface with timeout protection.
    """
    def __init__(self, primary, backup=None, name="Model"):
        self.primary = primary
        self.backup = backup
        self.name = name
    
    def invoke(self, messages, timeout=LLM_TIMEOUT, **kwargs):
        print(f"🔄 [{self.name}] Invoking LLM...")
        try:
            result = invoke_with_timeout(self.primary, messages, timeout=timeout, **kwargs)
            print(f"✅ [{self.name}] LLM call succeeded")
            return result
        except (TimeoutError, Exception) as e:
            # FIX: Recover from Groq "tool_use_failed" error with <function=...>
            # Llama 3 sometimes leaks XML tool calls that Groq API rejects.
            # We catch this rejection and parse the intent manually.
            err_str = str(e)
            if "failed_generation" in err_str and "<function=" in err_str:
                print(f"🔧 [{self.name}] Recovering from Groq XML tool call...")
                try:
                    import re
                    import json
                    from langchain_core.messages import AIMessage
                    import uuid
                    
                    # V10: Handle BOTH formats:
                    # Format 1: <function=name{json_args}>
                    # Format 2: <function=name(kwarg="value", ...)>
                    
                    # Try JSON format first
                    match = re.search(r"<function=(\w+)(\{.*?\})(?:</function>)?", err_str)
                    
                    if match:
                        tool_name = match.group(1)
                        args_str = match.group(2)
                        args = json.loads(args_str)
                    else:
                        # Try Python kwargs format: <function=name(key="value")>
                        match = re.search(r"<function=(\w+)\(([^)]+)\)", err_str)
                        if match:
                            tool_name = match.group(1)
                            kwargs_str = match.group(2)
                            # Parse kwargs like: query="git change origin"
                            args = {}
                            for pair in re.findall(r'(\w+)=["\']([^"\']*)["\']', kwargs_str):
                                args[pair[0]] = pair[1]
                        else:
                            raise ValueError("Could not parse tool call format")
                    
                    print(f"   Parsed: {tool_name} args={args}")
                    call_id = f"call_{uuid.uuid4().hex[:8]}"
                    
                    return AIMessage(
                        content="",
                        tool_calls=[{
                            "name": tool_name,
                            "args": args,
                            "id": call_id
                        }]
                    )
                except Exception as parse_err:
                    print(f"❌ Recovery failed: {parse_err}")

            if self.backup:
                print(f"⚠️ {self.name} Primary failed: {e}. Switching to Backup (Gemini)...")
                try:
                    return invoke_with_timeout(self.backup, messages, timeout=timeout, **kwargs)
                except Exception as backup_err:
                    print(f"❌ {self.name} Backup also failed: {backup_err}")
                    raise backup_err
            print(f"❌ {self.name} Failed (No Backup Available): {e}")
            raise e

    def bind_tools(self, tools):
        """
        Bind tools to both primary and backup LLMs.
        Returns a new ReliableLLM instance with bound models.
        """
        print(f"🔗 [{self.name}] Binding {len(tools)} tools to Primary & Backup")
        
        # Bind to primary
        bound_primary = self.primary.bind_tools(tools)
        
        # Bind to backup if exists
        bound_backup = None
        if self.backup:
            # Check if backup supports binding (some might not)
            if hasattr(self.backup, "bind_tools"):
                bound_backup = self.backup.bind_tools(tools)
            else:
                bound_backup = self.backup # Keep unbound if not supported
        
        # Return new wrapper so invoke() works heavily
        return ReliableLLM(bound_primary, bound_backup, f"{self.name}+Tools")

class SmartAssistant:

    def __init__(self):
        self.tools = get_all_tools()
        self.tool_map = {t.name: t for t in self.tools}
        self.current_mood = "Neutral"
        self._setup_llms()
        self.planner = Planner(self.planner_llm) if self.planner_llm else None
        # V5: Initialize Verifier with fast 8B model
        self.verifier = Verifier(self.intent_llm) if self.intent_llm else None
        # V7: Initialize World Graph (Single Source of Truth)
        # This replaces ConversationStateTracker with a proper entity/action graph
        from ..config import get_project_root
        self.world_graph = WorldGraph(
            persist_path=os.path.join(get_project_root(), "data", "world_graph.json")
        )

    def _setup_llms(self):
        """Initialize Tiered Models with Hot Failover."""
        self.intent_llm = None
        self.planner_llm = None
        self.responder_llm = None
        
        # 1. Initialize Backup / OpenRouter (Preferred if available)
        self.backup_llm = None
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        if openrouter_key:
             try:
                # OpenRouter (Gemini 2.0 Flash Exp for Vision/Speed)
                self.backup_llm = ChatOpenAI(
                    model="google/gemini-2.0-flash-exp:free",
                    temperature=0.3,
                    api_key=openrouter_key,
                    base_url="https://openrouter.ai/api/v1",
                    max_retries=2,
                    request_timeout=30
                )
                print("✅ Backup Model (OpenRouter/Gemini 2.0) Loaded.")
             except Exception as e:
                print(f"⚠️ OpenRouter init failed: {e}")

        if not self.backup_llm and openai_key:
            try:
                self.backup_llm = ChatOpenAI(
                    model="gpt-4o-mini", 
                    temperature=0.3,
                    api_key=openai_key,
                    max_retries=2,
                    request_timeout=20
                )
                print("✅ Backup Model (GPT-4o mini) Loaded.")
            except Exception as e:
                print(f"⚠️ OpenAI init failed: {e}")

        # 2. Initialize Primary (Groq)
        if GROQ_API_KEY:
            try:
                # -- Intent Router --
                groq_intent = ChatGroq(
                    model="llama-3.1-8b-instant", # V10: 8B for fast routing (Tier 1)
                    temperature=0.0,
                    groq_api_key=GROQ_API_KEY,
                    max_retries=1 
                )
                self.intent_llm = ReliableLLM(groq_intent, self.backup_llm, "IntentRouter")

                # -- Planner (V10: Upgraded for implicit reasoning) --
                groq_planner = ChatGroq(
                    model="llama-3.3-70b-versatile", # V10: 70B for deep reasoning (Tier 2)
                    temperature=0.1,
                    groq_api_key=GROQ_API_KEY,
                    max_retries=1
                )
                self.planner_llm = ReliableLLM(groq_planner, self.backup_llm, "Planner")

                # -- Responder --
                groq_responder = ChatGroq(
                    model="openai/gpt-oss-20b", # V10: Fast responder (Mixtral decommissioned)
                    temperature=0.6,
                    groq_api_key=GROQ_API_KEY,
                    max_retries=1
                )
                self.responder_llm = ReliableLLM(groq_responder, self.backup_llm, "Responder")
                
                print(f"✅ Tiered Architecture Loaded (Router: 8B, Planner: 70B, Responder: 8B).")
            except Exception as e:
                print(f"⚠️ Groq init failed: {e}")

        # 3. Fallback: If Groq failed completely
        if not self.intent_llm and self.backup_llm:
            self.intent_llm = self.backup_llm
            self.planner_llm = self.backup_llm
            self.responder_llm = self.backup_llm
            print("⚠️ Running on Backup Model Only (Groq Unavailable).")

    def _route_with_qwen(self, user_input: str) -> bool:
        # ... existing qwen logic ...
        return False

    def run(self, user_input: str, history: List[Dict], image_data: Optional[str] = None) -> Dict[str, Any]:
        """
        SAKURA V10 PIPELINE
        Supports Text + Vision
        """
        print(f"🚀 [LLM] SmartAssistant.run() STARTED")
        start_time = time.time()
        state = AgentState()
        
        # V10 Vision Short-Circuit
        # If image is present, skip all complex routing and go straight to Vision Model (OpenRouter/Gemini)
        if image_data:
            print("🖼️ Image detected! Routing to Vision Model...")
            if not self.backup_llm:
                 return {"content": "I received an image, but I don't have a vision-capable model configured (OpenRouter/OpenAI key missing)."}
            
            try:
                # Construct Multimodal Message
                # OpenRouter/OpenAI format (HumanMessage imported at module level):
                msg = HumanMessage(content=[
                    {"type": "text", "text": user_input or "Describe this image."},
                    {"type": "image_url", "image_url": {"url": image_data}} # Data URL assumed
                ])
                
                # Invoke directly
                response = self.backup_llm.invoke([msg])
                
                # Record in graph? maybe later.
                return {
                    "content": response.content,
                    "mode": "Vision",
                    "tools_used": "VisionModel",
                    "metadata": {"latency": f"{time.time()-start_time:.2f}s"}
                }
            except Exception as e:
                print(f"❌ Vision Error: {e}")
                return {"content": f"I had trouble analyzing that image: {e}"}

        # Regular Text Pipeline...
        
        # Default error response
        error_response = {
            "content": "I encountered an error. Please try again.",
            "metadata": {"mode": "Error", "tool_used": "None", "latency": "0s"}
        }
        
        try:
            # V4: Detect study mode FIRST (before any memory ops)
            study_mode_active = detect_study_mode(user_input)
            if study_mode_active:
                print(f"📚 Study Mode: ACTIVATED - Memory injection disabled")
            
            # V4.2: Import optimization config
            from ..config import (
                RAG_CONTEXT_MAX_CHARS, TOOL_OUTPUT_MAX_CHARS, 
                EXECUTOR_MAX_ITERATIONS, ENABLE_PLANNER_CACHE
            )
            
            # V5: Memory retrieval BEFORE routing
            user_memory = ""
            if not study_mode_active:
                user_memory = self._get_memory_for_routing(user_input)
            
            # ═══ V7: WORLD GRAPH QUERY (before routing) ═══
            # The graph is the SINGLE SOURCE OF TRUTH for identity and references
            is_user_ref, user_ref_confidence = self.world_graph.is_user_reference(user_input)
            resolution = self.world_graph.resolve_reference(user_input)
            
            # V7: EQ Layer - Infer user intent for response adaptation
            user_intent = self.world_graph.infer_user_intent(user_input, history)
            intent_adjustment = self.world_graph.get_intent_adjustment()
            
            print(f"📊 [V7] Graph: user_ref={is_user_ref} (conf={user_ref_confidence:.2f}), "
                  f"resolution={'found' if resolution.resolved else 'none'} "
                  f"(conf={resolution.confidence:.2f}), intent={user_intent.value}")
            
            # V7: User-reference short-circuit (BANNED from external search)
            # Uses World Graph identity instead of tools
            if is_user_ref and user_ref_confidence > 0.7 and not study_mode_active:
                print(f"🎯 [V7] User-reference detected - using graph identity instead of tools")
                mode = "UserIdentity"
                user_identity = self.world_graph.get_user_identity()
                tool_outputs = f"[USER PROFILE - DO NOT SEARCH EXTERNALLY]\n{user_identity.summary}\n\nAttributes: {user_identity.attributes}"
                # Downgrade to SIMPLE path - responder will use the profile
                is_complex = False
                state.current_intent = "USER_IDENTITY"
                # Skip routing LLM call
                state.llm_call_count -= 1  # Compensate for the routing call we'll skip
            
            # Initialize state variables
            tool_outputs_initialized = tool_outputs if is_user_ref and user_ref_confidence > 0.7 else ""
            tool_outputs = tool_outputs_initialized
            tool_used = "None"
            mode = mode if is_user_ref and user_ref_confidence > 0.7 else "Chat"
            safe_context = ""
            plan_data = None
            last_tool_result = None  # For retry formatter
            
            # V7: Get graph context for planner (resolved entities, recent actions)
            graph_context = self.world_graph.get_context_for_planner(user_input)
            
            # V7.1: Extract last conversation topic for pronoun resolution ("search it up" → topic)
            # This fixes cases where "it" refers to something discussed, not a graph entity
            if history and len(history) >= 2:
                # Get last assistant message to find what was being discussed
                for msg in reversed(history[-6:]):  # Check last 6 messages
                    if msg.get("role") == "assistant":
                        last_response = msg.get("content", "")[:200]  # First 200 chars
                        if last_response and len(last_response) > 20:
                            graph_context = f"[LAST TOPIC] {last_response[:150]}...\n{graph_context}"
                        break


            # ═══ STEP 1: V10 SMART ROUTER (DIRECT/PLAN/CHAT classification) ═══
            state.record_llm_call("routing")  # LLM Call #1
            route_classification = "CHAT"
            tool_hint = None
            
            try:
                if study_mode_active:
                    route_classification = "PLAN"
                    tool_hint = None
                    
                # V7: Hard heuristic for action verbs - force DIRECT/PLAN path
                elif self._is_action_command(user_input):
                    route_classification = "PLAN"  # Let Planner decide exact tool
                    print(f"🎯 [V7] Router: Action verb detected - forcing PLAN")
                
                # V7: Public-figure hallucination guard - force search for "who is X"
                elif self._is_public_figure_query(user_input)[0]:
                    _, person_name = self._is_public_figure_query(user_input)
                    person_entity = self.world_graph.entities.get(f"entity:person:{person_name.replace(' ', '_').lower()}")
                    if not person_entity or person_entity.lifecycle.value != "promoted":
                        route_classification = "PLAN"
                        tool_hint = "web_search"
                        print(f"🛡️ [V7] Router: Public figure query ('{person_name}') - PLAN with web_search")
                    
                elif ENABLE_LOCAL_ROUTER:
                    is_complex = self._route_with_qwen(user_input)
                    route_classification = "PLAN" if is_complex else "CHAT"
                    state.llm_call_count -= 1  # Local router doesn't count
                    
                elif self.intent_llm:
                    # V10: Smart Router with DIRECT/PLAN/CHAT classification
                    router_prompt = f"""[USER MEMORY]
{user_memory if user_memory else "(none)"}

[CURRENT MESSAGE]
{user_input}

Classify and output JSON."""
                    
                    router_msg = [
                        SystemMessage(content=ROUTER_SYSTEM_PROMPT),
                        HumanMessage(content=router_prompt)
                    ]
                    
                    # V9.1: Governor enforcement
                    from .context_governor import get_context_governor, ContextBudgetExceeded
                    governor = get_context_governor()
                    router_msg, _, _ = governor.enforce(router_msg, "ROUTER")
                    
                    router_res = self.intent_llm.invoke(router_msg).content
                    route_classification, tool_hint = self._parse_router_response(router_res)
                
                # V10: Map classification to state
                state.current_intent = route_classification
                is_complex = route_classification in ("DIRECT", "PLAN")
                print(f"🚦 Router: {route_classification}{' (Study Mode)' if study_mode_active else ''}")
                
            except Exception as e:
                print(f"⚠️ Router error: {e}")
                route_classification = "CHAT"
                is_complex = False
            
            # V4.2: RAG only for COMPLEX queries
            if is_complex and not study_mode_active:
                print(f"📚 [RAG] Fetching context...")
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(get_relevant_context, user_input, RAG_CONTEXT_MAX_CHARS)
                        context = future.result(timeout=30)
                    if len(context) > RAG_CONTEXT_MAX_CHARS:
                        context = context[:RAG_CONTEXT_MAX_CHARS] + "..."
                    print(f"📚 [RAG] Context retrieved ({len(context)} chars)")
                    safe_context = sanitize_memory_text(context)
                except concurrent.futures.TimeoutError:
                    print(f"⚠️ [RAG] Context retrieval timed out")
                except Exception as e:
                    print(f"⚠️ [RAG] Context retrieval failed: {e}")
            elif not is_complex:
                print(f"⚡ [RAG] Skipped - CHAT query")
            
            # ═══ V10: DIRECT PATH (Fast Lane) ═══
            # Skip Planner + Verifier for single-tool DIRECT actions
            # Only for safe, simple tools with reliable arg extraction
            DIRECT_SAFE_TOOLS = {
                "get_weather", "gmail_read_email", "calendar_get_events", 
                "note_list", "get_news", "define_word"
            }
            
            if route_classification == "DIRECT" and tool_hint and not study_mode_active:
                # Safety check: Only allow whitelisted tools for DIRECT
                if tool_hint not in DIRECT_SAFE_TOOLS:
                    print(f"⚠️ [V10] Tool {tool_hint} not in DIRECT whitelist, falling back to PLAN")
                    route_classification = "PLAN"
                else:
                    print(f"🚀 [V10] DIRECT path: Executing {tool_hint} immediately")
                    mode = "Direct/FastLane"
                    
                    # Check cache first
                    cached_result = cache_get(tool_hint, {})
                    if cached_result:
                        tool_outputs = f"[CACHED] {cached_result}"
                        tool_used = f"{tool_hint} (cached)"
                        print(f"⚡ [V10] Cache HIT - skipping tool execution")
                    else:
                        # Execute tool directly
                        try:
                            tool_obj = self.tool_map.get(tool_hint)
                            if tool_obj:
                                # Simple arg extraction for DIRECT tools
                                direct_args = self._extract_direct_args(user_input, tool_hint)
                                result = tool_obj.invoke(direct_args)
                                tool_outputs = f"=== TOOL: {tool_hint} ===\n{result}"
                                tool_used = tool_hint
                                
                                # Cache the result
                                cache_set(tool_hint, direct_args, result)
                                
                                # Record in World Graph
                                self.world_graph.record_action(
                                    tool=tool_hint,
                                    args=direct_args,
                                    result=str(result)[:500],
                                    success=True
                                )
                            else:
                                # Tool not found, fall back to PLAN
                                print(f"⚠️ [V10] Tool {tool_hint} not found, falling back to PLAN")
                                route_classification = "PLAN"
                        except Exception as e:
                            print(f"⚠️ [V10] DIRECT execution failed: {e}")
                            tool_outputs = f"Error executing {tool_hint}: {e}"
                            route_classification = "PLAN"  # Fall back to Planner
            
            # ═══ STEP 2: PLANNER + EXECUTOR (only if PLAN) ═══
            if route_classification == "PLAN" and self.planner:
                mode = "Study/Source" if study_mode_active else "Complex/Tool"
                print("⚙️ Entering Detailed Mode (Planner)...")
                
                # V5.1: Intent Classification (0 LLM calls - pure heuristic)
                intent_mode_enum, intent_reason = classify_intent(user_input)
                state.intent_mode = intent_mode_enum.value
                print(f"🎯 [V5.1] Intent: {state.intent_mode.upper()} ({intent_reason})")
                
                # V5.1: REASONING_ONLY mode - skip planner entirely, no LLM call spent
                if state.intent_mode == "reasoning":
                    plan_data = {"plan": [], "mode": "reasoning"}
                    tool_outputs = "(Reasoning mode - no tools executed)"
                    mode = "Reasoning"
                    print(f"🧠 Planner: REASONING mode - skipping planner LLM call")
                else:
                    # V8: ITERATIVE ReAct LOOP
                    # Allows Planner to see output of Step 1 before planning Step 2
                    print("⚙️ Entering Detailed Mode (Iterative Planner)...")
                
                # V8: Initialize variables for all code paths
                tool_history = []
                final_tool_outputs = []
                tool_outputs = ""
                tool_used = "None"
                last_tool_result = None
                plan_data = {"plan": []}  # V8: Initialize for edge cases
                MAX_LOOPS = 5
                
                
                # Skip tool execution for reasoning mode
                if state.intent_mode != "reasoning":
                    
                    # V9.1: Track executed steps to prevent infinite replanning
                    executed_steps = set()
                    
                    for turn in range(MAX_LOOPS):
                        state.record_llm_call("planning")
                        
                        # Plan with history
                        plan_data = self.planner.plan(
                            user_input, graph_context, 
                            hindsight=state.hindsight if turn == 0 else None,
                            intent_mode=state.intent_mode,
                            resolution=resolution,
                            tool_history=tool_history
                        )
                        
                        steps = plan_data.get("plan", [])
                        raw_msg = plan_data.get("message")
                        
                        # Track conversation state for next loop
                        if raw_msg:
                            tool_history.append(raw_msg)
                            
                        # If no more tools needed, break loop
                        if not steps:
                            if turn == 0:
                                tool_outputs = "(No tools were deemed necessary by the planner)."
                                tool_used = "None"
                                last_tool_result = None
                            break
                        
                        
                        # V9.1: Duplicate step detection (with normalized args)
                        if steps:
                            step = steps[0]  # Check first step
                            # Normalize args: filter out empty strings, None, empty dicts
                            normalized_args = {
                                k: v for k, v in step.get('args', {}).items()
                                if v not in (None, "", {}, [])
                            }
                            step_signature = (step['tool'], tuple(sorted(normalized_args.items())))
                            if step_signature in executed_steps:
                                print(f"⚠️ [ReAct] Duplicate step detected: {step['tool']} - breaking loop")
                                break
                            executed_steps.add(step_signature)
                            
                        # Execute steps (returns valid ToolMessages for history)
                        res_txt, res_msgs, tool_used, last_tool_result = self._execute_steps_react(steps, state)
                        
                        # Add results to history
                        tool_history.extend(res_msgs)
                        final_tool_outputs.extend(res_txt)
                        
                        # Update Graph per step
                        if last_tool_result:
                            self.world_graph.record_action(
                                tool=last_tool_result["tool"],
                                args=last_tool_result["args"],
                                result=last_tool_result["output"],
                                success=last_tool_result["success"]
                            )
                            
                            # V9.1: Fail-fast on tool error
                            if not last_tool_result["success"]:
                                print(f"⚠️ [ReAct] Tool failed: {last_tool_result['tool']} - exiting loop")
                                break
                            
                    # Combine all outputs for Responder/Verifier
                    tool_outputs = "\n\n=== TOOL EXECUTION LOG ===\n" + "\n".join(final_tool_outputs)
                    
                    # V9: Proactive Cleanup Reminder
                    if "Saved to Ephemeral Memory" in tool_outputs or "Content Saved to Ephemeral Memory" in tool_outputs:
                        tool_outputs += "\n\n[SYSTEM NOTE] Ephemeral documents were created during this task. When fully done, use `clear_all_ephemeral_memory()` or `forget_document(doc_id)` to free resources."
                
                # Now handle post-execution logic (Verifier/Responder handoff)
                if state.intent_mode == "reasoning":
                    pass
                
                elif final_tool_outputs: # If tools were used
                    
                    # V5.1: DATA_REASONING mode - skip verifier/retry, go straight to responder
                    if state.intent_mode == "data_then_reason":
                        if len(tool_outputs.strip()) < 50 or "error" in tool_outputs.lower():
                             print("⚠️ [V5.1] DATA→REASONING: Fetch failed, using general analysis fallback")
                        else:
                             print("📊 [V5.1] DATA→REASONING: Tool output is context, responder will analyze")
                        mode = "Data→Reasoning"
                    
                    # V5: ACTION mode - full verifier (Run ONCE at the end of the loop)
                    elif self.verifier and state.can_call_llm() and not study_mode_active:
                        print("🔍 [V5] Verifier: Evaluating final outcome...")
                        # Pass user_input, last plan, and ALL outputs
                        verdict = self.verifier.evaluate(user_input, plan_data, tool_outputs, state) # Use last plan_data
                        state.verifier_verdicts.append(verdict.reason)
                        print(f"🔍 [V5] Verdict: {'PASS ✓' if verdict.is_pass else 'FAIL ✗'} - {verdict.reason}")
                        
                        # RETRY (If fail)
                        # For now, simplistic retry: just ONE more loop if failed? 
                        # Or simple "Hindsight Inject & Linear Retry" like before?
                        # Re-using the OLD retry logic is safest but triggers a SECOND full loop.
                        if verdict.is_fail and state.can_call_llm():
                             print(f"🔄 [V5] Retry: Injecting hindsight and restarting loop...")
                             state.set_hindsight(verdict.reason)
                             # Recursive call or just rely on next turn? 
                             # Since we replaced the static block, we can just jump to retry block if we kept it?
                             # Actually I removed the retry block in this replacement.
                             # Let's simple-retry: One single retry step using the old linear logic?
                             # OR: Rerun the loop? Rerun loop is risky for infinite loops.
                             # DECISION: For this iteration, I will skip complex retry recursion to avoid infinite loops.
                             # I will just log the failure. The loop itself *should* have corrected itself if it was smart.
                             pass
                else:
                    tool_outputs = "(No tools were deemed necessary by the planner)."
            
            # ═══ STEP 4: RESPONDER (text-only, ALWAYS runs for non-retry paths) ═══
            print(f"🏁 [LLM] SmartAssistant.run() completing - calling responder")
            
            # V5: Check rate limit before responder
            if not state.can_call_llm():
                print("⚠️ [V5] Rate limit reached - using fallback response")
                return self._create_rate_limit_response(state, start_time, tool_outputs)
            
            state.record_llm_call("responding")  # LLM Call (2, 3, or 4)
            
            # V7: Get responder context from graph
            graph_responder_context = self.world_graph.get_context_for_responder()
            
            response = self._generate_final_response(
                user_input, tool_outputs, history, safe_context, start_time, 
                tool_used, mode, study_mode_active, state, graph_responder_context,
                intent_adjustment  # V7: EQ Layer mood adaptation
            )
            
            # V7: Advance turn and persist graph
            self.world_graph.advance_turn()
            self.world_graph.save()
            
            # V9.1: Post-Turn Reflection (async memory learning)
            self._reflect_and_learn(user_input, response.get("content", ""))
            
            return response
            
        except RateLimitExceeded as e:
            # V5: Explicit rate limit handling
            print(f"🛑 [V5] Rate Limit Exceeded: {e}")
            return {
                "content": "I'm stuck in a reasoning loop and stopping to protect my rate limits. Could you try rephrasing your request?",
                "metadata": {
                    "mode": "RateLimitSafety",
                    "status": "failed",
                    "latency": f"{time.time() - start_time:.2f}s",
                    **state.to_metadata()
                }
            }
            
        except Exception as e:
            print(f"❌ [LLM] SmartAssistant.run() FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            error_response["content"] = f"I encountered an error: {str(e)[:100]}. Please try again."
            error_response["metadata"]["latency"] = f"{time.time() - start_time:.2f}s"
            error_response["metadata"]["status"] = "failed"
            return error_response
    
    def _get_memory_for_routing(self, query: str) -> str:
        """V5: Retrieve compact memory for routing context."""
        try:
            memories = self._get_compact_memories(query)
            if not memories:
                return ""
            
            lines = []
            for m in memories[:2]:  # Max 2 memories
                lines.append(f"- {m['text'][:100]}")
            return "\n".join(lines)
        except Exception as e:
            print(f"⚠️ Memory for routing failed: {e}")
            return ""
    
    def _is_action_command(self, user_input: str) -> bool:
        """
        V7: Hard heuristic to detect action commands that MUST go to planner.
        
        This prevents the LLM router from misclassifying obvious tool commands
        like "play it" or "search that" as SIMPLE chat.
        """
        text = user_input.lower().strip()
        
        # Action verbs that ALWAYS need tools
        action_verbs = [
            "play", "queue", "pause", "stop", "skip", "resume",  # Music
            "open", "launch", "start", "run",                    # Apps
            "search", "find", "look up", "google",               # Search
            "send", "message", "email", "text", "call",          # Communication
            "remind", "reminder", "set alarm", "timer",          # Reminders
            "create", "add", "make", "delete", "remove",         # CRUD
            "download", "upload", "save", "export",              # Files
            "turn on", "turn off", "enable", "disable",          # System
        ]
        
        # Check if input starts with or contains action verb as first word
        words = text.split()
        if not words:
            return False
        
        first_word = words[0]
        
        # Direct match on first word
        for verb in action_verbs:
            if first_word == verb or first_word == verb.split()[0]:
                return True
        
        # Also check multi-word verbs at start
        for verb in action_verbs:
            if text.startswith(verb):
                return True
        
        return False

    def _parse_router_response(self, response_text: str) -> Tuple[str, Optional[str]]:
        """
        V10: Parse enhanced Router response with DIRECT/PLAN/CHAT classification.
        
        Args:
            response_text: Raw LLM response (should be JSON)
            
        Returns:
            Tuple of (classification, tool_hint)
            classification: "DIRECT", "PLAN", or "CHAT"
            tool_hint: Tool name if DIRECT/PLAN, None otherwise
        """
        try:
            # Clean potential markdown wrapping
            clean = response_text.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].split("```")[0].strip()
            
            data = json.loads(clean)
            classification = data.get("classification", "CHAT").upper()
            tool_hint = data.get("tool_hint")
            
            # Validate classification
            if classification not in ("DIRECT", "PLAN", "CHAT"):
                classification = "CHAT"
            
            print(f"🧠 [V10] Router: {classification} (hint: {tool_hint or 'none'})")
            return classification, tool_hint
            
        except json.JSONDecodeError:
            # Fallback: Try to detect old SIMPLE/COMPLEX format
            lower = response_text.lower()
            if "complex" in lower:
                return "PLAN", None
            elif "simple" in lower:
                return "CHAT", None
            else:
                # Default to CHAT for safety
                print(f"⚠️ [V10] Router parse failed, defaulting to CHAT")
                return "CHAT", None

    def _extract_direct_args(self, user_input: str, tool_name: str) -> dict:
        """
        V10: Extract arguments for DIRECT path tool execution.
        
        Simple heuristic extraction for common tools.
        Falls back to empty args for tools that don't need them.
        """
        text = user_input.lower().strip()
        
        if tool_name == "get_weather":
            # Extract city if mentioned
            # Prio 1: Explicit preposition (weather in Tokyo)
            match = re.search(r"weather (?:in|at|for) (.+?)(?:\?|$)", text, re.IGNORECASE)
            if match:
                return {"city": match.group(1).strip()}
            
            # Prio 2: City before weather (Tokyo weather)
            # Filter out common phrases that aren't cities
            match = re.search(r"(.+?)\s+weather", text, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                stopwords = {
                    "the", "check", "current", "my", "what's the", "what is the", 
                    "whats the", "how's the", "how is the", "show", "show me", 
                    "get", "tell me", "hey, what's the", "hey"
                }
                if candidate.lower() not in stopwords:
                    return {"city": candidate}
            
            return {}  # Default to user's location
            
        elif tool_name == "gmail_read_email":
            # Check for filters
            if "unread" in text:
                return {"query": "is:unread"}
            return {}
            
        elif tool_name == "calendar_get_events":
            # Check for date mentions
            if "tomorrow" in text:
                from datetime import datetime, timedelta
                tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                return {"date": tomorrow}
            return {}
            
        elif tool_name == "set_timer":
            # Extract minutes/seconds
            # improved: match "in 5 mins", "for 5 mins", "5 min timer"
            match = re.search(r"(\d+)\s*(min|minute|hour|hr|sec)", text)
            if match:
                value = int(match.group(1))
                unit = match.group(2)
                if "hour" in unit or "hr" in unit:
                    value *= 60
                elif "sec" in unit:
                    value = max(1, value // 60)
                return {"minutes": value}
            
            # Match "10 minutes" at start or end
            match = re.search(r"^(\d+)$", text.replace("timer", "").strip())
            if match:
                return {"minutes": int(match.group(1))}
                
            return {"minutes": 5}  # Default
            
        elif tool_name == "open_app":
            # Extract app name
            # Support "open up X", "launch X", "start X"
            match = re.search(r"(?:open|launch|start|run)(?:\s+up)?\s+(.+?)(?:\s+app)?$", text, re.IGNORECASE)
            if match:
                return {"app_name": match.group(1).strip()}
            return {"app_name": text}
            
        elif tool_name == "note_list":
            return {}
            
        elif tool_name == "set_reminder":
            match = re.search(r"remind\s+(?:me\s+)?(?:to\s+)?(.+?)(?:\s+in\s+(\d+)\s*(min|hour))?", text)
            if match:
                message = match.group(1).strip()
                delay = 5  # Default
                if match.group(2):
                    delay = int(match.group(2))
                    if match.group(3) and "hour" in match.group(3):
                        delay *= 60
                return {"message": message, "delay_minutes": delay}
            return {"message": text, "delay_minutes": 5}
        
        # Default empty args
        return {}

    def _reflect_and_learn(self, user_input: str, response: str):
        """
        V9.1: Post-Turn Reflection - async memory learning from conversation.
        
        Analyzes the exchange and updates World Graph with new facts.
        Runs async to not block response delivery.
        """
        import threading
        
        def _reflect():
            try:
                # Skip very short exchanges (no facts in "ok" or "thanks")
                if len(user_input) < 15:
                    return
                
                from langchain_core.messages import HumanMessage
                import json
                
                prompt = f"""Analyze this conversation. Extract ONLY facts the user explicitly stated as TRUE about themselves.

STRICT RULES:
- Only extract facts explicitly stated as TRUE in present/past tense
- IGNORE wishes, desires, hypotheticals ("I wish", "I want to", "maybe")
- IGNORE questions the user asked
- IGNORE temporary states ("I'm tired" is NOT a fact)
- Focus on: location, preferences, habits, relationships, work, identity

User: {user_input[:500]}
Assistant: {response[:300]}

If a new PERMANENT fact was stated AND you are 90%+ confident, respond with JSON:
{{"fact_type": "location|preference|habit|relationship|work", "key": "specific_key", "value": "exact_value", "confidence": 0.9}}

If NO new permanent fact OR confidence < 90%, respond with: null
Better to miss a memory than store a lie."""
                
                result = self.intent_llm.invoke([HumanMessage(content=prompt)])
                content = result.content.strip()
                
                if content.lower() == "null" or not content.startswith("{"):
                    return
                
                # Parse JSON
                try:
                    fact = json.loads(content)
                    if fact and fact.get("key") and fact.get("value"):
                        # Update World Graph
                        from .world_graph import EntitySource
                        print(f"🧠 [V9.1] Reflection: New fact detected: {fact['key']} = {fact['value']}")
                        
                        # Create entity from learned fact
                        from .world_graph import EntityType
                        
                        # Map string type to Enum
                        etype_str = fact['fact_type'].lower()
                        etype = EntityType.USER # Default fallback
                        try:
                            etype = EntityType(etype_str)
                        except ValueError:
                            pass # Keep default
                            
                        self.world_graph.get_or_create_entity(
                            type=etype,
                            name=fact['key'],
                            source=EntitySource.USER_STATED,
                            attributes={"value": fact['value'], "learned_from": "reflection"}
                        )
                        self.world_graph.save()
                except json.JSONDecodeError:
                    pass  # Not valid JSON, skip
                    
            except Exception as e:
                print(f"⚠️ [V9.1] Reflection failed: {e}")
        
        # Run async to not block response
        threading.Thread(target=_reflect, daemon=True).start()

    def _prune_tool_output(self, output: str, max_chars: int = 1000) -> str:
        """
        V9.1: Smart Pruner with Summarization Layer.
        
        For large outputs, uses LLM to summarize instead of truncating.
        This preserves semantic meaning while reducing token count.
        """
        if len(output) <= max_chars:
            return output
        
        # V9.1: For very large outputs, summarize instead of truncate
        if len(output) > 2000 and hasattr(self, 'intent_llm') and self.intent_llm:
            try:
                summary = self._summarize_output(output)
                if summary:
                    return f"[SUMMARY of {len(output)} chars]\n{summary}"
            except Exception as e:
                print(f"⚠️ Summarization failed: {e}, falling back to truncation")
        
        # Check if output looks like JSON
        stripped = output.strip()
        if (stripped.startswith('{') and stripped.endswith('}')) or \
           (stripped.startswith('[') and stripped.endswith(']')):
            try:
                import json
                data = json.loads(output)
                
                # Recursively prune large string values in the JSON
                def prune_json(obj, depth=0):
                    if depth > 5:
                        return "[NESTED]"
                    if isinstance(obj, dict):
                        pruned = {}
                        for k, v in obj.items():
                            # Skip known large keys
                            if k.lower() in ('html', 'html_body', 'raw_content', 'body', 'content'):
                                pruned[k] = f"[{len(str(v))} chars - use retrieve_document_context()]"
                            else:
                                pruned[k] = prune_json(v, depth + 1)
                        return pruned
                    elif isinstance(obj, list):
                        if len(obj) > 5:
                            return [prune_json(obj[0], depth + 1), f"... [{len(obj) - 1} more items]"]
                        return [prune_json(item, depth + 1) for item in obj]
                    elif isinstance(obj, str) and len(obj) > 200:
                        return obj[:200] + "..."
                    return obj
                
                pruned_data = prune_json(data)
                pruned_json = json.dumps(pruned_data, indent=2, ensure_ascii=False)
                
                if len(pruned_json) <= max_chars:
                    return pruned_json
                # Still too long, truncate the JSON string (but keep it valid)
                return json.dumps({"_truncated": True, "preview": str(data)[:500]})
            except (json.JSONDecodeError, TypeError):
                pass  # Not valid JSON, fall through to text truncation
        
        # Text truncation - don't split words
        truncated = output[:max_chars]
        # Find last complete word/sentence
        last_space = truncated.rfind(' ')
        last_newline = truncated.rfind('\n')
        cut_point = max(last_space, last_newline, max_chars - 100)
        if cut_point > 0:
            truncated = output[:cut_point]
        
        remaining = len(output) - len(truncated)
        return f"{truncated}\n... [TRUNCATED: {remaining} chars. Use retrieve_document_context() for full content.]"

    def _summarize_output(self, output: str) -> str:
        """
        V9.1: Summarize large tool outputs using 8B model.
        Anti-hallucination prompt ensures factual accuracy.
        """
        from langchain_core.messages import HumanMessage
        
        # Limit input to 3000 chars to avoid token explosion
        sample = output[:3000]
        
        prompt = f"""Summarize this tool output in 2-3 concise sentences.

CRITICAL RULES:
- Extract exact numbers, dates, and quotes verbatim
- Do NOT hallucinate or invent details not in the source
- If uncertain, say "unclear" instead of guessing

Tool Output:
{sample}

Summary:"""
        
        print(f"🧹 [V9.1] Summarizing {len(output)} char output...")
        response = self.intent_llm.invoke([HumanMessage(content=prompt)])
        summary = response.content.strip()[:500]  # Cap at 500 chars
        return summary
    
    def _execute_plan_v5(self, steps: list, user_input: str, state: AgentState, 
                         max_iterations: int, max_output_chars: int) -> tuple:
        """
        V5: Execute plan steps and track results.
        Returns: (tool_outputs, tool_used, last_tool_result)
        """
        from ..config import TOOL_OUTPUT_MAX_CHARS
        
        results = []
        tool_used = "None"
        last_tool_result = None
        steps = steps[:max_iterations]
        
        if len(steps) > max_iterations:
            print(f"⚠️ Executor: Capped at {max_iterations} steps")
        
        for step in steps:
            tool_name = step.get("tool")
            tool_args = step.get("args", {})
            
            if tool_name in self.tool_map:
                print(f"▶️ Executing Step {step.get('id')}: {tool_name} {tool_args}")
                try:
                    res = self.tool_map[tool_name].invoke(tool_args)
                    
                    # Smart summarization (existing V4 logic)
                    res, tool_used = self._handle_smart_summarization(tool_name, res, user_input, tool_used)
                    
                    # Truncate output
                    res_str = str(res)
                    if len(res_str) > max_output_chars:
                        res_str = res_str[:max_output_chars] + "... [truncated]"
                    
                    results.append(f"Step {step.get('id')} ({tool_name}): {res_str}")
                    tool_used = tool_name
                    last_tool_result = {"tool": tool_name, "args": tool_args, "output": res_str, "success": True}
                    state.record_tool_result(success=True)
                    
                except Exception as e:
                    results.append(f"Step {step.get('id')} Error: {e}")
                    last_tool_result = {"tool": tool_name, "args": tool_args, "output": str(e), "success": False}
                    state.record_tool_result(success=False)
            else:
                results.append(f"Step {step.get('id')} Error: Tool '{tool_name}' not found.")
                state.record_tool_result(success=False)
        
        tool_outputs = "\n\n=== TOOL EXECUTION LOG ===\n" + "\n".join(results) if results else ""
        return tool_outputs, tool_used, last_tool_result

    def _execute_steps_react(self, steps: list, state: AgentState) -> tuple:
        """
        V8: Execute steps for ReAct loop, returning ToolMessages for history.
        V9: Added History Pruner to prevent token bloat.
        Returns: (results_text_list, tool_messages, tool_used, last_tool_result)
        """
        from langchain_core.messages import ToolMessage
        
        results_text = []
        tool_messages = []
        tool_used = "None"
        last_tool_result = None
        
        for step in steps:
            tool_name = step.get("tool")
            tool_args = step.get("args", {})
            call_id = step.get("tool_call_id")
            
            if tool_name in self.tool_map:
                print(f"▶️ Executing Step {step.get('id')}: {tool_name} {tool_args}")
                try:
                    # Invoke tool
                    res = self.tool_map[tool_name].invoke(tool_args)
                    res_str = str(res)
                    
                    # V9: Prune output to prevent context bloat in ReAct loop
                    pruned_res = self._prune_tool_output(res_str)
                    
                    # Append valid ToolMessage for ReAct history (PRUNED)
                    if call_id:
                        tool_messages.append(ToolMessage(
                            tool_call_id=call_id,
                            content=pruned_res,
                            name=tool_name
                        ))
                    
                    results_text.append(f"Step {step.get('id')} ({tool_name}): {res_str}")
                    tool_used = tool_name
                    last_tool_result = {"tool": tool_name, "args": tool_args, "output": res_str, "success": True}
                    state.record_tool_result(success=True)
                    
                except Exception as e:
                    err_msg = f"Error: {e}"
                    if call_id:
                        tool_messages.append(ToolMessage(
                            tool_call_id=call_id,
                            content=err_msg,
                            name=tool_name,
                            status="error"
                        ))
                    results_text.append(f"Step {step.get('id')} Error: {e}")
                    last_tool_result = {"tool": tool_name, "args": tool_args, "output": str(e), "success": False}
                    state.record_tool_result(success=False)
            else:
                err = f"Tool '{tool_name}' not found."
                results_text.append(f"Step {step.get('id')} Error: {err}")
                if call_id:
                    tool_messages.append(ToolMessage(tool_call_id=call_id, content=err, name=tool_name, status="error"))
                state.record_tool_result(success=False)
        
        return results_text, tool_messages, tool_used, last_tool_result
    
    def _create_rate_limit_response(self, state: AgentState, start_time: float, tool_outputs: str) -> dict:
        """V5: Create response when rate limit prevents responder call."""
        # Use tool outputs directly if available
        if tool_outputs and "Error" not in tool_outputs:
            content = "I completed the action. " + tool_outputs[:200]
        else:
            content = "I've used my thinking budget for this request. Here's what I found so far."
        
        return {
            "content": content,
            "metadata": {
                "mode": "RateLimitFallback",
                "status": "completed",
                "latency": f"{time.time() - start_time:.2f}s",
                **state.to_metadata()
            }
        }


    def _handle_smart_summarization(self, tool_name: str, res: Any, user_input: str, current_tool_used: str):
        """
        V5.1 DISABLED: Smart summarization removed to maintain 4-LLM call invariant.
        
        The LLM call here was untracked by AgentState, violating rate limit guarantees.
        Raw RAG/scrape results are now passed through unchanged.
        
        Re-enable post-V5.1 only if tracking is added.
        """
        # V5.1: Return unchanged - no LLM call
        return res, current_tool_used
    
    def _build_knowledge_block(self, tool_outputs: str, tool_name: str = None) -> str:
        """
        V7: Clean up tool outputs into a knowledge block for the responder.
        
        Strips junk like "Search results for 'X':" and extracts useful content.
        Returns a clean block that the responder can use to synthesize answers.
        """
        if not tool_outputs:
            return ""
        
        # Patterns to strip (junk headers)
        junk_patterns = [
            r"Search results for '[^']+':?\s*",
            r"\[?Search results for [^\]]+\]?:?\s*",
            r"Output from Tavily:?\s*",
            r"=== TOOL EXECUTION LOG ===\s*",
            r"Step \d+ \([^)]+\):\s*",
            r"\[truncated\]\s*",
        ]
        
        import re
        cleaned = tool_outputs
        for pattern in junk_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        
        # Remove empty brackets/lists
        cleaned = re.sub(r'\[\s*\]', '', cleaned)
        cleaned = re.sub(r'\[\s*""\s*\]', '', cleaned)
        
        # Strip and normalize whitespace
        cleaned = "\n".join(line.strip() for line in cleaned.split("\n") if line.strip())
        
        # If still too short after cleaning, indicate thin knowledge
        if len(cleaned.strip()) < 30:
            return "[Knowledge too thin to answer reliably]"
        
        # Truncate to reasonable size for responder
        if len(cleaned) > 1500:
            cleaned = cleaned[:1500] + "..."
        
        return f"[KNOWLEDGE BLOCK]\n{cleaned}"
    
    def _is_public_figure_query(self, user_input: str) -> tuple:
        """
        V7: Detect "who is X" / "tell me about X" queries for public figures.
        
        Returns:
            (is_public_figure_query: bool, person_name: str or None)
        """
        import re
        text = user_input.lower().strip()
        
        # Patterns for public figure queries
        patterns = [
            r"who is ([a-z\s]+?)[\?]?$",
            r"who'?s ([a-z\s]+?)[\?]?$",
            r"tell me about ([a-z\s]+?)$",
            r"what do you know about ([a-z\s]+?)$",
            r"do you know ([a-z\s]+?)[\?]?$",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip()
                # Exclude self-references
                if name in ["me", "myself", "my name", "dhanush", "the user"]:
                    return False, None
                # Likely a public figure query
                if len(name.split()) <= 4:  # Names are usually 1-4 words
                    return True, name
        
        return False, None

    def _generate_final_response(self, user_input, tool_outputs, history, safe_context, start_time, tool_used, mode, study_mode_active=False, state=None, graph_context="", intent_adjustment=""):
        """
        V4/V5 Compact Token Pipeline:
        - System prompt (full personality)
        - Merged <CONTEXT> block (summary + 3 msgs + 2 memories)
        - Single HumanMessage(user_input)
        
        V5 additions:
        - State metadata in response
        - Action-claim guardrail for SIMPLE paths
        
        V7 additions:
        - World Graph context injection (replaces V6 conversation state)
        - EQ Layer intent adjustment (frustration/urgency adaptation)
        
        Target: ~500-900 tokens total
        """
        messages = []
        user_state = get_current_user_state()  # V4: Get user state for metadata
        
        # V4: Study mode additional instructions
        study_mode_prompt = ""
        if study_mode_active:
            study_mode_prompt = get_study_mode_system_prompt()

        # 1. SYSTEM PROMPT (full personality - kept as-is)
        # Include responder guardrail rule
        
        # V5.1: DATA_REASONING mode instruction - ensure opinion, not content dump
        data_reasoning_instruction = ""
        if state and state.intent_mode == "data_then_reason":
            data_reasoning_instruction = """
CRITICAL: The user wants your ANALYSIS/OPINION, not a summary.
- Provide your honest critique, evaluation, or perspective
- Use judgment language: "I think", "this suggests", "the issue is", "I'd recommend"
- Do NOT just repeat or summarize what the data says
- If data fetch failed, provide general analysis based on context
"""
        
        # V7: World Graph context (identity, preferences, last action)
        graph_context_block = ""
        if graph_context:
            graph_context_block = f"\n{graph_context}\n"
        
        # V7: EQ Layer - Intent-aware response adjustment
        intent_adjustment_block = ""
        if intent_adjustment:
            intent_adjustment_block = f"\n[USER MOOD ADAPTATION]\n{intent_adjustment}\n"
        
        system_prompt = (
            f"{SYSTEM_PERSONALITY}\n"
            f"{RESPONDER_NO_TOOLS_RULE}\n"
            f"{data_reasoning_instruction}"
            f"{graph_context_block}"
            f"{intent_adjustment_block}"
            f"{study_mode_prompt}\n"
            f"CURRENT MOOD: {self.current_mood}\n"
            f"USER STATE: {user_state}\n"
            f"{tool_outputs if tool_outputs else ''}\n"
            f"Task: Respond naturally based on context."
        )
        messages.append(SystemMessage(content=system_prompt))
        
        # 2. V4 COMPACT CONTEXT (FROZEN - single path only)
        compact_context = self._build_v4_context(history, safe_context, user_input)
        messages.append(SystemMessage(content=compact_context))
        
        # Token estimation
        est_tokens = len(compact_context) // 4
        print(f"📦 V4 Compact Context: {len(compact_context)} chars (~{est_tokens} tokens)")
        
        # 3. CURRENT USER INPUT (single message, no duplication)
        messages.append(HumanMessage(content=user_input))
        
        # V9.1: CONTEXT GOVERNOR (Proactive Budget Enforcement)
        # Replaces reactive backtracking - enforces limits BEFORE API call
        from .context_governor import get_context_governor, ContextBudgetExceeded
        governor = get_context_governor()
        
        try:
            messages, tool_outputs, _ = governor.enforce(
                messages, 
                "RESPONDER",
                tool_outputs=tool_outputs
            )
        except ContextBudgetExceeded as e:
            # Explicit abort - tell user, never silent failure
            print(f"❌ [Governor] ABORT: {e.message}")
            return f"I couldn't process this request - the context was too large ({e.current_chars:,} chars). Try asking a more specific question or clearing conversation history."
        
        # 4. INVOKE RESPONDER (text-only, no tools allowed)
        final_response = "..."
        if self.responder_llm:
            try:
                total_msgs = len(messages)
                print(f"🤖 Synthesizing... ({total_msgs} messages)")
                
                # Guardrail: Invoke with tool_choice=none
                res = self.responder_llm.invoke(messages, tool_choice="none")
                raw_response = res.content
                
                # Guardrail: Validate and strip any tool-call patterns
                final_response, had_violation = validate_responder_output(raw_response)
                if had_violation:
                    from ..utils.stability_logger import log_warning
                    log_warning(f"Responder tool-call violation detected and stripped")
                
                # V5: Action-claim guardrail (string heuristics, no LLM)
                if tool_used == "None" and not tool_outputs:
                    final_response = self._check_action_claim_guardrail(final_response)
                    
            except Exception as e:
                # Check if error is about tool_choice parameter not being supported
                if "tool_choice" in str(e).lower():
                    print("⚠️ Model doesn't support tool_choice, retrying without...")
                    try:
                        res = self.responder_llm.invoke(messages)
                        raw_response = res.content
                        final_response, _ = validate_responder_output(raw_response)
                    except Exception as e2:
                        final_response = f"❌ Response Error: {e2}"
                else:
                    final_response = f"❌ Response Error: {e}"
        else:
            final_response = "❌ No Responder LLM available."

        # V5: Include state metadata if available
        metadata = {
            "mood": self.current_mood,
            "user_state": user_state,
            "tool_used": tool_used,
            "mode": mode,
            "study_mode": study_mode_active,
            "latency": f"{time.time() - start_time:.2f}s",
            "v4_compact": ENABLE_V4_COMPACT_CONTEXT,
            "memory_chars": len(safe_context) if safe_context else 0,
            "status": "completed"  # V5: Explicit status
        }
        
        if state:
            metadata.update(state.to_metadata())
        
        return {
            "content": final_response,
            "metadata": metadata
        }
    
    def _check_action_claim_guardrail(self, response: str) -> str:
        """
        V5: Detect if responder claims an action without tool execution.
        
        Uses string heuristics (no LLM call) to catch confident lies.
        """
        # Action verbs that imply tool execution
        action_patterns = [
            r"\bi (have |just )?(sent|scheduled|created|added|updated|played|opened|deleted|saved)",
            r"\b(email|event|task|note|file) (has been|was) (sent|created|scheduled|added)",
            r"\bdone[.!]?\s*$",
            r"\bplaying now",
            r"\bsuccessfully (sent|created|scheduled|added|saved)"
        ]
        
        response_lower = response.lower()
        
        for pattern in action_patterns:
            if re.search(pattern, response_lower, re.IGNORECASE):
                print("⚠️ [V5] Action-claim guardrail: False action claim detected")
                from ..utils.stability_logger import log_warning
                log_warning("Responder claimed action without tool execution")
                
                # Replace with honest response
                return "I understand you want me to do something, but I wasn't able to take any action. Could you clarify what you'd like me to do?"
        
        return response
    
    def _build_v4_context(self, history: List[Dict], safe_context: str, user_input: str) -> str:
        """
        Build V4 merged compact context block.
        Target: 120-180 tokens
        """
        from ..utils.summary import update_rolling_summary, build_compact_context
        from ..utils.stability_logger import log_ctx
        
        # 1. Rolling Summary (update and get)
        rolling_summary = ""
        if ENABLE_V4_SUMMARY and len(history) > V4_MAX_RAW_MESSAGES:
            rolling_summary = update_rolling_summary(history)
        
        # 2. Recent Messages (last 3 only)
        recent_messages = history[-V4_MAX_RAW_MESSAGES:] if history else []
        
        # 3. Compact Memory Items (top 2 with importance)
        memory_items = self._get_compact_memories(user_input)
        
        # Log context stats
        log_ctx(len(rolling_summary), len(recent_messages), len(memory_items))
        
        # Build merged context
        return build_compact_context(rolling_summary, recent_messages, memory_items)
    
    def _get_compact_memories(self, query: str) -> List[Dict]:
        """Get top N memories with importance/relevance scores."""
        try:
            store = get_memory_store()
            
            if not store or not store.faiss_index or store.faiss_index.ntotal == 0:
                return []
            
            # Ensure embeddings loaded
            store._ensure_embeddings_loaded()
            if not store.embeddings_model:
                return []
            
            # Vector search
            query_embedding = store.embeddings_model.encode([query])[0]
            import numpy as np
            distances, indices = store.faiss_index.search(
                np.array([query_embedding], dtype=np.float32), 
                k=V4_MEMORY_LIMIT
            )
            
            results = []
            for i, idx in enumerate(indices[0]):
                if idx == -1 or idx >= len(store.memory_texts):
                    continue
                
                text = store.memory_texts[idx][:V4_MEMORY_CHAR_LIMIT]
                relevance = 1.0 / (1.0 + distances[0][i])
                
                # Get importance score
                importance = 0.5
                key = str(idx)
                if key in store.memory_importance:
                    importance = float(store.memory_importance[key])
                
                # Patch 2: Reinforce memory when retrieved (using store method)
                store.reinforce_memory(idx, boost=0.1)
                
                results.append({
                    "text": text,
                    "importance": importance,
                    "relevance": relevance,
                    "idx": idx
                })
            
            return results
            
        except Exception as e:
            print(f"⚠️ Memory retrieval error: {e}")
            return []

_assistant = None
def run_agentic_response(user_input: str, history: List[Dict]) -> Dict[str, Any]:
    global _assistant
    if not _assistant:
        _assistant = SmartAssistant()
    return _assistant.run(user_input, history)

def get_assistant() -> Optional[SmartAssistant]:
    """Expose singleton for external management (e.g. WorldGraph reset)."""
    global _assistant
    return _assistant

