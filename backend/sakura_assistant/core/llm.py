import os
import time
import re
from typing import List, Dict, Any, Optional

from ..core.context_manager import get_smart_context
from ..config import SYSTEM_PERSONALITY
from ..core.container import get_container
from ..core.model_wrapper import ReliableLLM

# V10 Modular Components
from .router import IntentRouter
from .executor import ToolExecutor
from .responder import ResponseGenerator
from .tools import get_all_tools

# V7: World Graph
from .world_graph import WorldGraph
from ..utils.study_mode import detect_study_mode
from .agent_state import AgentState, RateLimitExceeded
from ..utils.memory import cleanup_memory

# V10.3: Summary Memory for long-context
from ..memory.summary_memory import get_summary_memory

# V10.4: Flight Recorder for observability
from ..utils.flight_recorder import get_recorder, span

from langchain_core.messages import HumanMessage

class SmartAssistant:
    """
    Sakura V10 Facade
    =================
    Orchestrates the new modular architecture:
    Router -> Executor -> Responder
    
    This class now delegates all logic to specialized components.
    """

    def __init__(self):
        print("🏗️ Initializing SmartAssistant Facade...")
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
                f"❌ No LLM configured for: {', '.join(missing)}. "
                f"Please set GROQ_API_KEY or OPENROUTER_API_KEY in your .env file."
            )
        
        # Initialize Components via Container
        self.router = IntentRouter(router_llm)
        self.executor = ToolExecutor(
            tools=self.tools,
            summarizer_llm=planner_llm
        )
        self.responder = ResponseGenerator(
            responder_llm,
            SYSTEM_PERSONALITY
        )
        
        # V7: World Graph (Single Source of Truth)
        from ..config import get_project_root
        self.world_graph = WorldGraph(
            persist_path=os.path.join(get_project_root(), "data", "world_graph.json")
        )
        
        # V10.3: Summary Memory (compresses old turns for long-context)
        self.summary_memory = get_summary_memory(planner_llm)
        
        print("✅ SmartAssistant Initialized (Modular V10 Architecture)")

    def run(self, user_input: str, history: List[Dict], image_data: Optional[str] = None) -> Dict[str, Any]:
        """
        Main Pipeline:
        1. Vision Check
        2. Graph Update (Intent/Refs)
        3. Router (Direct/Plan/Chat)
        4. Executor (Tools)
        5. Responder (Final Answer)
        """
        print(f"\U0001f680 [LLM] SmartAssistant.run() STARTED")
        start_time = time.time()
        state = AgentState()
        recorder = get_recorder()
        recorder.start_trace(user_input)
        
        # 1. Vision Short-Circuit
        if image_data:
            return self._handle_vision(user_input, image_data, start_time)
            
        try:
            # 2. Graph & Context
            study_mode_active = detect_study_mode(user_input)
            
            # Update Graph with User Intent
            self.world_graph.resolve_reference(user_input)
            self.world_graph.infer_user_intent(user_input, history)
            
            # 3. Routing
            state.record_llm_call("routing")
            with span("Router"):
                route_result = self.router.route(user_input, history, study_mode_active)
            recorder.log("Router", f"Decision: {route_result.classification} (hint: {route_result.tool_hint})")
            print(f"\U0001f6a6 Router Decision: {route_result.classification}")
            
            state.current_intent = route_result.classification
            
            # 4. Execution
            tool_outputs = ""
            tool_used = "None"
            
            # DEBUG: Log route result details
            print(f"🔍 DEBUG: route_result.needs_tools = {route_result.needs_tools}")
            print(f"🔍 DEBUG: route_result.tool_hint = {route_result.tool_hint}")
            print(f"🔍 DEBUG: route_result.classification = {route_result.classification}")
            
            if route_result.needs_tools or route_result.tool_hint:
                print(f"⚙️ Execution Phase: {route_result.classification}")
                state.record_llm_call("execution")
                
                # Fetch Graph Context for Executor
                graph_context = self.world_graph.get_context_for_planner(user_input)
                
                with span("Executor"):
                    exec_result = self.executor.execute(
                        user_input,
                        route_result,
                        graph_context,
                        state
                    )
                recorder.log("Executor", f"Tool: {exec_result.tool_used}, Success: {exec_result.success}")
                
                tool_outputs = exec_result.outputs
                tool_used = exec_result.tool_used
                
                # DEBUG: Log execution result
                print(f"🔍 DEBUG: exec_result.outputs = '{tool_outputs[:100]}...' (len={len(tool_outputs)})")
                print(f"🔍 DEBUG: exec_result.tool_used = {tool_used}")
                print(f"🔍 DEBUG: exec_result.success = {exec_result.success}")
                
                if exec_result.tool_messages:
                     # Log actions to World Graph
                     for action in exec_result.tool_messages:
                         try:
                             # action is a ToolMessage or similar dict
                             tool_name = action.get("tool", "unknown")
                             tool_args = action.get("args", {})
                             tool_result = action.get("content", "")
                             
                             self.world_graph.record_action(
                                 tool=tool_name,
                                 args=tool_args,
                                 result=str(tool_result),
                                 success=True # Assumed if we got a result
                             )
                         except Exception as wg_err:
                             print(f"⚠️ World Graph recording failed: {wg_err}")
            
            # V10.3: Record turn in Summary Memory
            self.summary_memory.add_turn("user", user_input)
            
            # 5. Response
            state.record_llm_call("responding")
            print(f"🏁 Response Phase")
            
            # V10.3: Get compressed summary for context injection
            summary_context = self.summary_memory.get_context_injection()
            
            # Prepare Responder Context
            from .responder import ResponseContext
            resp_context = ResponseContext(
                user_input=user_input,
                tool_outputs=tool_outputs,
                history=history,
                graph_context=self.world_graph.get_context_for_responder(),
                intent_adjustment=self.world_graph.get_intent_adjustment(),
                current_mood=self.world_graph.get_current_mood(),
                study_mode=study_mode_active
            )
            
            with span("Responder"):
                response_text = self.responder.generate(resp_context)
            recorder.log("Responder", f"Generated {len(response_text)} chars")
            
            # V10.3: Record assistant response in Summary Memory
            self.summary_memory.add_turn("assistant", response_text)
            
            # Update Graph Logic
            self.world_graph.advance_turn()
            self.world_graph.save()
            
            recorder.end_trace(success=True, response_preview=response_text[:80])
            
            return {
                "content": response_text,
                "mode": route_result.classification,
                "tool_used": tool_used,
                "metadata": {
                    "latency": f"{time.time()-start_time:.2f}s",
                    "status": "success"
                }
            }
            
        except RateLimitExceeded:
            recorder.end_trace(success=False, response_preview="rate_limited")
            return {
                "content": "I'm working too hard and hit a rate limit. Please try again in a moment.",
                 "metadata": {"status": "rate_limited"}
             }
        except Exception as e:
            recorder.end_trace(success=False, response_preview=str(e)[:50])
            print(f"\u274c Pipeline Error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "content": f"I encountered an error: {e}",
                 "metadata": {"status": "error"}
            }

    async def arun(self, user_input: str, history: List[Dict], image_data: Optional[str] = None) -> Dict[str, Any]:
        """
        Async Pipeline (V10.4):
        1. Vision Check
        2. Graph Update (Sync - fast)
        3. Router (Async)
        4. Executor (Async)
        5. Responder (Async)
        """
        print(f"\U0001f680 [LLM] SmartAssistant.arun() STARTED (Async)")
        start_time = time.time()
        state = AgentState()
        recorder = get_recorder()
        recorder.start_trace(user_input)
        
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
            
            # 3. Routing (Async)
            state.record_llm_call("routing")
            with span("Router"):
                route_result = await self.router.aroute(user_input, history, study_mode_active)
            recorder.log("Router", f"Decision: {route_result.classification} (hint: {route_result.tool_hint})")
            print(f"\U0001f6a6 Async Router Decision: {route_result.classification}")
            
            state.current_intent = route_result.classification
            
            # 4. Execution (Async)
            tool_outputs = ""
            tool_used = "None"
            
            if route_result.needs_tools or route_result.tool_hint:
                print(f"⚙️ Async Execution Phase: {route_result.classification}")
                state.record_llm_call("execution")
                
                # Fetch Graph Context
                graph_context = self.world_graph.get_context_for_planner(user_input)
                
                with span("Executor"):
                    exec_result = await self.executor.aexecute(
                        user_input,
                        route_result,
                        graph_context,
                        state
                    )
                recorder.log("Executor", f"Tool: {exec_result.tool_used}, Success: {exec_result.success}")
                
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
            print(f"🏁 Async Response Phase")
            
            summary_context = self.summary_memory.get_context_injection()
            
            from .responder import ResponseContext
            resp_context = ResponseContext(
                user_input=user_input,
                tool_outputs=tool_outputs,
                history=history,
                graph_context=self.world_graph.get_context_for_responder(),
                intent_adjustment=self.world_graph.get_intent_adjustment(),
                current_mood=self.world_graph.get_current_mood(),
                study_mode=study_mode_active
            )
            
            with span("Responder"):
                response_text = await self.responder.agenerate(resp_context)
            recorder.log("Responder", f"Generated {len(response_text)} chars")
            
            # Record assistant response (Sync)
            self.summary_memory.add_turn("assistant", response_text)
            
            # Update Graph Logic
            self.world_graph.advance_turn()
            self.world_graph.save()
            
            recorder.end_trace(success=True, response_preview=response_text[:80])
            
            return {
                "content": response_text,
                "mode": route_result.classification,
                "tool_used": tool_used,
                "metadata": {
                    "latency": f"{time.time()-start_time:.2f}s",
                    "status": "success",
                    "async": True
                }
            }
            
        except RateLimitExceeded:
            recorder.end_trace(success=False, response_preview="rate_limited")
            return {
                "content": "I'm working too hard and hit a rate limit. Please try again in a moment.",
                 "metadata": {"status": "rate_limited"}
             }
        except Exception as e:
            recorder.end_trace(success=False, response_preview=str(e)[:50])
            print(f"\u274c Async Pipeline Error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "content": f"I encountered an error: {e}",
                 "metadata": {"status": "error"}
            }
