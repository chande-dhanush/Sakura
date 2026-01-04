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
        
        # Initialize Components via Container
        self.router = IntentRouter(self.container.get_router_llm())
        self.executor = ToolExecutor(
            tools=self.tools,
            summarizer_llm=self.container.get_planner_llm()
        )
        self.responder = ResponseGenerator(
            self.container.get_responder_llm(),
            SYSTEM_PERSONALITY
        )
        
        # V7: World Graph (Single Source of Truth)
        from ..config import get_project_root
        self.world_graph = WorldGraph(
            persist_path=os.path.join(get_project_root(), "data", "world_graph.json")
        )
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
        print(f"🚀 [LLM] SmartAssistant.run() STARTED")
        start_time = time.time()
        state = AgentState()
        
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
            route_result = self.router.route(user_input, history, study_mode_active)
            print(f"🚦 Router Decision: {route_result.classification}")
            
            state.current_intent = route_result.classification
            
            # 4. Execution
            tool_outputs = ""
            tool_used = "None"
            
            if route_result.is_complex or route_result.tool_hint:
                print(f"⚙️ Execution Phase: {route_result.classification}")
                state.record_llm_call("execution")
                
                # Fetch Graph Context for Executor
                graph_context = self.world_graph.get_context_for_planner(user_input)
                
                exec_result = self.executor.execute(
                    user_input,
                    route_result,
                    graph_context,
                    state
                )
                
                tool_outputs = exec_result.output
                tool_used = exec_result.main_tool_used
                if exec_result.tool_history:
                     # Log actions to World Graph
                     for action in exec_result.tool_history:
                         # Attempt to parse args if possible, or just raw
                         pass # Executor logs internally? No, need to log here or in executor
                         # Ideally executor should return structured log to record
                         # For now, we trust Executor runs, but WorldGraph recording was inside loop
                         # TODO: Restore granular WorldGraph recording inside Executor or via callback
                         pass
            
            # 5. Response
            state.record_llm_call("responding")
            print(f"🏁 Response Phase")
            
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
            
            response_text = self.responder.generate(resp_context)
            
            # Update Graph Logic
            self.world_graph.advance_turn()
            self.world_graph.save()
            
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
             return {
                "content": "I'm working too hard and hit a rate limit. Please try again in a moment.",
                 "metadata": {"status": "rate_limited"}
             }
        except Exception as e:
            print(f"❌ Pipeline Error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "content": f"I encountered an error: {e}",
                 "metadata": {"status": "error"}
            }

    def _handle_vision(self, user_input: str, image_data: str, start_time: float):
        """Handle image inputs using backup vision model."""
        print("🖼️ Vision Pipeline Active")
        backup = self.container.get_backup_llm()
        if not backup:
             return {"content": "I received an image but don't have a vision-capable model configured."}
        
        try:
             msg = HumanMessage(content=[
                {"type": "text", "text": user_input or "Describe this image."},
                {"type": "image_url", "image_url": {"url": image_data}}
             ])
             response = backup.invoke([msg])
             return {
                "content": response.content,
                "mode": "Vision",
                "tool_used": "VisionModel",
                "metadata": {"latency": f"{time.time()-start_time:.2f}s"}
            }
        except Exception as e:
            print(f"❌ Vision Error: {e}")
            return {"content": f"Vision analysis failed: {e}"}
