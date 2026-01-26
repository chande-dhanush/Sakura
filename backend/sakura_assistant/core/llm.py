import os
import time
import re
from typing import List, Dict, Any, Optional

# V17: Reorganized imports
from .context import ContextManager, get_smart_context
from ..config import SYSTEM_PERSONALITY
from .infrastructure import get_container
from .models import ReliableLLM

# V10 Modular Components
from .routing import IntentRouter
from .execution import ToolExecutor
from .models import ResponseGenerator, ResponseContext
from .tools import get_all_tools

# V17: Execution architecture
from .execution import ExecutionDispatcher, OneShotRunner, ResponseEmitter, EmitterFactory

# V7: World Graph
from .graph import WorldGraph
from ..utils.study_mode import detect_study_mode
from .context import AgentState, RateLimitExceeded
from ..utils.memory import cleanup_memory

# V10.3: Summary Memory for long-context
from ..memory.summary_memory import get_summary_memory

# V10.4: Flight Recorder for observability
from ..utils.flight_recorder import get_recorder, span

from langchain_core.messages import HumanMessage

# V14: Background ReflectionEngine (constraint detection moved to cold path)
from .memory.reflection import get_reflection_engine

class SmartAssistant:
    """
    Sakura V17 Facade
    =================
    Orchestrates the V17 execution architecture:
    Router -> ExecutionDispatcher -> Responder
    
    V17 Changes:
    - ExecutionDispatcher replaces direct ToolExecutor calls
    - ExecutionContext threads mode/budget through pipeline
    - ResponseEmitter guarantees exactly one message per request
    """

    def __init__(self):
        print("️ Initializing SmartAssistant Facade (V17)...")
        self.container = get_container()
        self.tools = get_all_tools()
        self.tool_map = {t.name: t for t in self.tools}
        
        # Get LLMs from container
        router_llm = self.container.get_router_llm()
        planner_llm = self.container.get_planner_llm()
        responder_llm = self.container.get_responder_llm()
        
        # Validate LLMs are available (prevents NoneType errors later)
        if router_llm is None or planner_llm is None or responder_llm is None:
            missing = []
            if router_llm is None: missing.append("Router")
            if planner_llm is None: missing.append("Planner")
            if responder_llm is None: missing.append("Responder")
            raise RuntimeError(
                f" No LLM configured for: {', '.join(missing)}. "
                f"Please set GROQ_API_KEY or OPENROUTER_API_KEY in your .env file."
            )
        
        # Initialize Components via Container
        self.router = IntentRouter(router_llm)
        
        # V17: Keep ToolExecutor for ReActLoop (internal use only)
        self.executor = ToolExecutor(
            tools=self.tools,
            summarizer_llm=planner_llm
        )
        
        # V17: Create OneShotRunner for fast-lane execution
        self.oneshot_runner = OneShotRunner(
            tool_runner=self.executor.tool_runner,
            output_handler=self.executor.output_handler
        )
        
        self.responder = ResponseGenerator(
            responder_llm,
            SYSTEM_PERSONALITY
        )
        
        # V7: World Graph (Single Source of Truth)
        # V17: Inject IdentityManager to remove circular imports
        from ..config import get_project_root
        from .graph import get_identity_manager
        self.world_graph = WorldGraph(
            persist_path=os.path.join(get_project_root(), "data", "world_graph.json"),
            identity_manager=get_identity_manager()
        )
        
        # V17: Create ExecutionDispatcher (unified entry point)
        self.dispatcher = ExecutionDispatcher(
            one_shot_runner=self.oneshot_runner,
            react_loop=self.executor.react_loop,
            world_graph=self.world_graph,
            tools=self.tools
        )
        
        # V10.3: Summary Memory (compresses old turns for long-context)
        self.summary_memory = get_summary_memory(planner_llm)
        
        # V15.4: Centralized ContextManager (Single Source of Truth for Context Hygiene)
        self.context_manager = ContextManager(
            world_graph=self.world_graph,
            summary_memory=self.summary_memory
        )
        
        # V14: Background ReflectionEngine (constraint detection runs after response)
        self.reflection_engine = get_reflection_engine()
        
        # V15: DesireSystem (CPU-based mood tracking)
        from .cognitive.desire import get_desire_system
        self.desire_system = get_desire_system()
        self.desire_system.initialize(
            persist_path=os.path.join(get_project_root(), "data", "desire_state.json")
        )
        
        # V17: ResponseEmitter factory for guaranteed message emission
        self.emitter_factory = EmitterFactory()
        
        # Store last response for async reflection (picked up by server.py BackgroundTask)
        self._last_turn_data = {"user_msg": "", "assistant_response": ""}
        
        print(" SmartAssistant Initialized (V17 - ExecutionDispatcher)")

    def run(self, user_input: str, history: List[Dict], image_data: Optional[str] = None) -> Dict[str, Any]:
        """
        Sync Pipeline (V17): Delegates to async path.
        
        V17: No more split-brain architecture. Sync just wraps async.
        All execution semantics unified through dispatcher.
        """
        print(f" [LLM] SmartAssistant.run() → delegating to arun()")
        
        # V17: Force through async path (unified semantics)
        import asyncio
        try:
            return asyncio.run(self.arun(user_input, history, image_data))
        except RuntimeError as e:
            # Already in event loop (e.g., Jupyter notebook)
            if "asyncio.run() cannot be called from a running event loop" in str(e):
                print("⚠️ [LLM] Already in event loop, using get_event_loop().run_until_complete()")
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(self.arun(user_input, history, image_data))
            raise


    async def arun(self, user_input: str, history: List[Dict], image_data: Optional[str] = None) -> Dict[str, Any]:
        """
        Async Pipeline (V17):
        1. Vision Check
        2. Graph Update (Sync - fast)
        3. Router (Async)
        4. ExecutionDispatcher (Async) - NEW in V17
        5. Responder (Async)
        
        V17 Changes:
        - ExecutionDispatcher replaces Executor
        - ResponseEmitter guarantees exactly one message
        - ExecutionContext threads mode/budget through pipeline
        """
        print(f" [LLM] SmartAssistant.arun() STARTED (V17 Async)")
        start_time = time.time()
        state = AgentState()
        recorder = get_recorder()
        recorder.start_trace(user_input)
        
        # V17: Create ResponseEmitter for guaranteed message emission
        request_id = f"req_{int(time.time()*1000)}"
        emitter = self.emitter_factory.create(request_id)
        
        # 1. Vision Short-Circuit
        if image_data:
            # We can use the sync handle_vision for now, or make an async one. 
            # Ideally wrap it or make async. For now, wrapper.
            import asyncio
            return await asyncio.to_thread(self._handle_vision, user_input, image_data, start_time)
            
        try:
            # 2. Graph & Context (Keep sync for now as it's pure logic + in-memory mostly)
            study_mode_active = detect_study_mode(user_input)
            
            # Update Graph with User Intent
            self.world_graph.resolve_reference(user_input)
            self.world_graph.infer_user_intent(user_input, history)
            
            # V14: Constraint detection moved to background ReflectionEngine
            # (happens after response, not in hot path)
            
            # 3. Routing (Async)
            state.record_llm_call("routing")
            with span("Router"):
                route_result = await self.router.aroute(user_input, history, study_mode_active)
            recorder.log("Router", f"Decision: {route_result.classification} (hint: {route_result.tool_hint})")
            print(f" Async Router Decision: {route_result.classification}")
            
            state.current_intent = route_result.classification
            
            # 4. Execution (V17: Use ExecutionDispatcher)
            tool_outputs = ""
            tool_used = "None"
            exec_result = None
            
            if route_result.needs_tools or route_result.tool_hint:
                print(f"⚙️ V17 Dispatch Phase: {route_result.classification}")
                state.record_llm_call("execution")
                
                with span("ExecutionDispatcher"):
                    exec_result = await self.dispatcher.dispatch(
                        user_input=user_input,
                        classification=route_result.classification,
                        tool_hint=route_result.tool_hint,
                        request_id=request_id
                    )
                
                # V17: Use ExecutionStatus instead of bool
                recorder.log(
                    "Dispatcher", 
                    f"Tool: {exec_result.tool_used}, Status: {exec_result.status.value}", 
                    metadata={"mode": exec_result.last_result.get("mode") if exec_result.last_result else "unknown"}
                )
                
                tool_outputs = exec_result.outputs
                tool_used = exec_result.tool_used
                
                if exec_result.tool_messages:
                     # Log actions to World Graph (Sync)
                     for action in exec_result.tool_messages:
                         try:
                             # Handle ToolMessage objects (LangChain) or dicts
                             tool_name = getattr(action, 'name', None) or action.get('tool', 'unknown')
                             result_content = getattr(action, 'content', None) or action.get('content', '')
                             
                             self.world_graph.record_action(
                                 tool=tool_name,
                                 args={}, # Args not preserved in ToolMessage, acceptable for Graph history
                                 result=str(result_content),
                                 success=True
                             )
                         except Exception as wg_err:
                             print(f"⚠️ World Graph recording failed: {wg_err}")
            
            # V10.3: Record turn (Sync)
            self.summary_memory.add_turn("user", user_input)
            
            # 5. Response (Async)
            state.record_llm_call("responding")
            print(f" Async Response Phase")
            
            # V15.4: Get unified context from ContextManager
            resp_ctx = self.context_manager.get_context_for_llm(
                user_input,
                mode=route_result.classification,
                history=history
            )
            
            # V15: Inject mood from DesireSystem
            mood_prompt = self.desire_system.get_mood_prompt()
            # Hygiene: Use descriptive variable name for responder-specific context
            responder_context = f"{mood_prompt}\n\n{resp_ctx['responder_context']}"
            
            resp_context = ResponseContext(
                user_input=user_input,
                tool_outputs=tool_outputs,
                history=history,
                graph_context=responder_context,
                intent_adjustment=resp_ctx["intent_adjustment"],
                current_mood=resp_ctx["current_mood"],
                study_mode=study_mode_active,
                session_summary=resp_ctx["summary_context"]
            )
            
            with span("Responder"):
                response_text = await self.responder.agenerate(resp_context)
            recorder.log("Responder", f"Generated {len(response_text)} chars")
            
            # V15: Update desire state on messages
            self.desire_system.on_user_message(user_input)
            self.desire_system.on_assistant_message(response_text)
            
            # Record assistant response (Sync)
            self.summary_memory.add_turn("assistant", response_text)
            
            # V13: Store turn data for async reflection
            self._last_turn_data = {"user_msg": user_input, "assistant_response": response_text}
            
            # Update Graph Logic
            self.world_graph.advance_turn()
            self.world_graph.save()
            
            # Collect all unique tools used for UI observability
            all_tools_used = []
            if exec_result and exec_result.tool_messages:
                for action in exec_result.tool_messages:
                    t_name = getattr(action, 'name', None) or action.get('tool', 'unknown')
                    if t_name and t_name not in all_tools_used:
                        all_tools_used.append(t_name)
            
            # Fallback to tool_used if list is empty (single tool case)
            if not all_tools_used and tool_used and tool_used != "None":
                all_tools_used.append(tool_used)

            recorder.end_trace(success=True, response_preview=response_text[:80])
            
            # V17: Emit response via ResponseEmitter (guaranteed emission)
            await emitter.emit(response_text, {
                "status": "success",
                "latency": f"{time.time()-start_time:.2f}s"
            })
            
            return {
                "content": response_text,
                "mode": route_result.classification,
                "tool_used": tool_used, # Legacy single string
                "tools_used": all_tools_used, # V17: Full list for UI
                "metadata": {
                    "latency": f"{time.time()-start_time:.2f}s",
                    "status": "success",
                    "async": True,
                    "execution_status": exec_result.status.value if exec_result else "skipped"
                }
            }
            
        except RateLimitExceeded:
            recorder.end_trace(success=False, response_preview="rate_limited")
            error_response = "I'm working too hard and hit a rate limit. Please try again in a moment."
            await emitter.emit(error_response, {"status": "rate_limited"})
            return {
                "content": error_response,
                 "metadata": {"status": "rate_limited"}
             }
        except Exception as e:
            recorder.end_trace(success=False, response_preview=str(e)[:50])
            print(f" Async Pipeline Error: {e}")
            import traceback
            traceback.print_exc()
            error_response = f"I encountered an error: {e}"
            await emitter.emit(error_response, {"status": "error"})
            return {
                "content": error_response,
                 "metadata": {"status": "error"}
            }
        finally:
            # V17: Guaranteed emission safety net
            if not emitter.was_emitted:
                print(f"⚠️ [V17] Response not emitted - using fallback")
                await emitter.emit(
                    "I processed your request but encountered an issue. Please try again.",
                    {"status": "unknown"}
                )
