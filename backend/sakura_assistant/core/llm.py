import os
import time
import re
import json
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
from .models.request import RequestState
from .tools import get_all_tools

# V17: Execution architecture
from .execution import Executor, OneShotRunner, ResponseEmitter, EmitterFactory

# V7: World Graph
from .graph import WorldGraph
from ..utils.study_mode import detect_study_mode
from .context import AgentState, RateLimitExceeded
from .execution.context import LLMBudgetExceededError, ExecutionContext, ExecutionMode, GraphSnapshot
from .execution.verifier import PlanVerifier  # FIX-5
from ..utils.memory import cleanup_memory

# V10.3: Summary Memory for long-context
from ..memory.summary_memory import get_summary_memory

# V10.4: Flight Recorder for observability
from ..utils.flight_recorder import get_recorder, span

from langchain_core.messages import HumanMessage

# V14: Background ReflectionEngine (constraint detection moved to cold path)
from .memory.reflection import get_reflection_engine

# V18.2: Memory Judger for long-term FAISS persistence (BUG-03 FIX)
from .memory.judger import MemoryJudger

class SmartAssistant:
    """
    Sakura V19.0 Facade
    =================
    Orchestrates the V17 execution architecture:
    Router -> Executor -> Responder
    
    V17 Changes:
    - Executor replaces direct ToolExecutor calls
    - ExecutionContext threads mode/budget through pipeline
    - ResponseEmitter guarantees exactly one message per request
    """

    def __init__(self):
        print("Initializing SmartAssistant Facade (V17)...")
        self.container = get_container()
        self.tools = get_all_tools()
        self.tool_map = {t.name: t for t in self.tools}
        
        # Get LLMs from container
        try:
            router_llm = self.container.get_router_llm()
            planner_llm = self.container.get_planner_llm()
            responder_llm = self.container.get_responder_llm()
            verifier_llm = self.container.get_verifier_llm()
            
            # Validate LLMs are available (prevents NoneType errors later)
            if router_llm is None or planner_llm is None or responder_llm is None or verifier_llm is None:
                missing = []
                if router_llm is None: missing.append("Router")
                if planner_llm is None: missing.append("Planner")
                if responder_llm is None: missing.append("Responder")
                if verifier_llm is None: missing.append("Verifier")
                raise RuntimeError(
                    f"No LLM configured for: {', '.join(missing)}. "
                    f"Please check your provider keys and stage-specific model settings."
                )
        except RuntimeError as config_err:
             print(f"  [CRITICAL] SmartAssistant configuration failed: {config_err}")
             # We re-raise to prevent starting in a broken state
             raise
        
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
        
        # V18.2: Memory Judger (BUG-03 FIX)
        self.memory_judger = MemoryJudger(router_llm)
        
        # V17: Create Executor (unified entry point)
        self.executor_layer = Executor(
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
        
        # V18 FIX-05: Plan Verifier
        self.plan_verifier = PlanVerifier(verifier_llm)
        
        # Store last response for async reflection (picked up by server.py BackgroundTask)
        self._last_turn_data = {"user_msg": "", "assistant_response": ""}
        
        print(" SmartAssistant Initialized (V17 - Executor)")

    def run(self, user_input: str, history: List[Dict], image_data: Optional[str] = None) -> Dict[str, Any]:
        """
        Sync Pipeline (V17): Delegates to async path.
        
        V17: No more split-brain architecture. Sync just wraps async.
        All execution semantics unified through dispatcher.
        """
        print(f" [LLM] SmartAssistant.run()   delegating to arun()")
        
        # V17: Force through async path (unified semantics)
        import asyncio
        try:
            return asyncio.run(self.arun(user_input, history, image_data))
        except RuntimeError as e:
            # Already in event loop (e.g., Jupyter notebook)
            if "asyncio.run() cannot be called from a running event loop" in str(e):
                print("   [LLM] Already in event loop, using get_event_loop().run_until_complete()")
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(self.arun(user_input, history, image_data))
            raise


    async def arun(self, user_input: str, history: List[Dict], image_data: Optional[str] = None, llm_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Async Pipeline (V17):
        1. Vision Check
        2. Graph Update (Sync - fast)
        3. Router (Async)
        4. Executor (Async) - NEW in V17
        5. Responder (Async)
        
        V17 Changes:
        - Executor replaces ToolExecutor calls
        - ResponseEmitter guarantees exactly one message
        - ExecutionContext threads mode/budget through pipeline
        - V19: Support optional request-time llm_overrides
        """
        print(f" [LLM] SmartAssistant.arun() STARTED (V17 Async)")
        if llm_overrides:
            print(f" [LLM] Applying request-time overrides: {llm_overrides}")
        start_time = time.time()
        state = AgentState()
        recorder = get_recorder()
        recorder.start_trace(user_input)
        
        # V17: Create ResponseEmitter for guaranteed message emission
        request_id = f"req_{int(time.time()*1000)}"
        emitter = self.emitter_factory.create(request_id)
        
        # V19-FIX: Initialize RequestState container
        req_state = RequestState(
            query=user_input,
            history=history if history else [],
            image_data=image_data,
            request_id=request_id
        )
        
        # 1. Vision Short-Circuit
        if image_data:
            # We can use the sync handle_vision for now, or make an async one. 
            # Ideally wrap it or make async. For now, wrapper.
            import asyncio
            return await asyncio.to_thread(self._handle_vision, user_input, image_data, start_time)
            
        try:
            # V18.3: Dynamic Personalization (FIX-C)
            # Load FRESH user settings on every request
            from sakura_assistant.utils.pathing import get_project_root
            settings_path = os.path.join(get_project_root(), "data", "user_settings.json")
            user_settings = {}
            if os.path.exists(settings_path):
                try:
                    with open(settings_path, "r", encoding="utf-8") as f:
                        user_settings = json.load(f)
                except Exception as e:
                    print(f"   [Settings] Load failed: {e}")

            # 1. Identity Override
            sakura_name = user_settings.get("sakura_name", "Sakura")
            
            # 2. Base Personality Override
            custom_prompt = user_settings.get("system_prompt_override", "")
            base_personality = custom_prompt if custom_prompt else SYSTEM_PERSONALITY
            
            # Inject sakura_name so the responder knows its identity
            if sakura_name and sakura_name != "Sakura":
                base_personality = f"Your name is {sakura_name}. Respond as {sakura_name}.\n\n{base_personality}"
            
            # 3. Response Style Enforcement
            style = user_settings.get("response_style", "balanced").lower()
            style_blocks = {
                "concise": "[STYLE: CONCISE] Keep responses under 2 sentences. No fluff, no filler.",
                "balanced": "[STYLE: BALANCED] Normal response length. Be conversational but not verbose.",
                "detailed": "[STYLE: DETAILED] Be thorough. Explain fully, use examples where helpful."
            }
            style_constraint = style_blocks.get(style, style_blocks["balanced"])
            
            # Update Responder Personality for THIS request
            # (Note: self.responder is shared, but we update it here safely since 
            # we are in an async task. For true thread-safety with concurrent requests 
            # might need a more isolated approach, but this matches V17 singleton pattern)
            self.responder.personality = f"{base_personality}\n\n{style_constraint}"
            
            # 2. Graph & Context (Keep sync for now as it's pure logic + in-memory mostly)
            req_state.study_mode = detect_study_mode(user_input)
            
            # V19-FIX-01: Capture reference resolution result
            resolution = self.world_graph.resolve_reference(user_input)
            self.world_graph.infer_user_intent(user_input, history)
            
            # V19-FIX-02: Format resolved reference for downstream context injection
            reference_context = ""
            if resolution.resolved and resolution.confidence > 0.4:
                from .graph.world_graph import EntityNode, ActionNode
                if isinstance(resolution.resolved, EntityNode):
                    reference_context = (
                        f"[REFERENCE RESOLVED] \"{user_input}\" refers to: "
                        f"{resolution.resolved.name}   {resolution.resolved.summary or 'No description'} "
                        f"(confidence: {resolution.confidence:.0%})"
                    )
                elif isinstance(resolution.resolved, ActionNode):
                    reference_context = (
                        f"[REFERENCE RESOLVED] \"{user_input}\" refers to previous action: "
                        f"{resolution.resolved.tool or 'chat'}   {resolution.resolved.summary or 'No description'} "
                        f"(confidence: {resolution.confidence:.0%})"
                    )
                if resolution.ban_external_search:
                    reference_context += " [DO NOT search externally for this   use graph data]"
                if resolution.action:
                    reference_context += f" [Suggested action: {resolution.action}]"
                
                req_state.reference_context = reference_context
                recorder.log("ReferenceResolution", f"Resolved: {reference_context[:80]}")
            else:
                recorder.log("ReferenceResolution", f"No match (confidence={resolution.confidence:.2f})")
            
            # V14: Constraint detection moved to background ReflectionEngine
            # (happens after response, not in hot path)

            # ExecutionContext.create() intentionally sets execution_context_var as a side effect,
            # so the Router LLM call below is counted by ReliableLLM's budget hook.
            ExecutionContext.create(
                mode=ExecutionMode.ITERATIVE,
                request_id=request_id,
                user_input=user_input,
                snapshot=GraphSnapshot.from_graph(self.world_graph),
                history=history,
                reference_context=req_state.reference_context
            )
            
            # 3. Routing (Async)
            # V19-FIX-01: Use keyword arguments to prevent positional mismatch.
            # Previous bug: aroute(user_input, history, study_mode_active) passed
            # history as 'context' (str) and study_mode_active (bool) as 'history' (List),
            # causing TypeError crash when router tried history[-3:] on a boolean.
            state.record_llm_call("routing")
            with span("Router"):
                # Use override LLM if provided
                r_llm = self.container.get_router_llm(overrides=llm_overrides) if llm_overrides else self.router.llm
                route_result = await self.router.aroute(
                    query=user_input,
                    history=history,
                    llm_override=r_llm if llm_overrides else None
                )
            
            req_state.classification = route_result.classification
            req_state.tool_hint = route_result.tool_hint
            
            recorder.log("Router", f"Decision: {route_result.classification} (hint: {route_result.tool_hint}), study_mode={req_state.study_mode}")
            print(f" Async Router Decision: {route_result.classification}")
            
            state.current_intent = route_result.classification
            
            # 4. Execution (V17: Use Executor)
            tool_outputs = ""
            tool_used = "None"
            exec_result = None
            
            if route_result.needs_tools or route_result.tool_hint:
                print(f"   V17 Dispatch Phase: {route_result.classification}")
                state.record_llm_call("execution")
                
                with span("Executor"):
                    # Pass overrides to dispatch
                    exec_result = await self.executor_layer.dispatch(
                        user_input=user_input,
                        classification=route_result.classification,
                        tool_hint=route_result.tool_hint,
                        request_id=request_id,
                        history=history,
                        reference_context=req_state.reference_context,
                        llm_overrides=llm_overrides
                    )
                
                # V17: Use ExecutionStatus instead of bool
                recorder.log(
                    "Dispatcher", 
                    f"Tool: {exec_result.tool_used}, Status: {exec_result.status.value}", 
                    metadata={"mode": exec_result.last_result.get("mode") if exec_result.last_result else "unknown"}
                )
                
                # V18 FIX-05: Ensure tool result is unconditionally assigned for Responder acknowledgment
                tool_outputs = str(exec_result.outputs) if exec_result and exec_result.outputs else ""
                tool_used = exec_result.tool_used if exec_result else "None"
                
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
                             print(f"   World Graph recording failed: {wg_err}")
                
                # V18 FIX-05: Plan Verification
                if route_result.classification == "PLAN" and exec_result:
                    with span("Verifier"):
                        # Convert steps (List[Dict]) to a readable summary for the Verifier
                        plan_steps = exec_result.last_result.get("steps", []) if exec_result.last_result else []
                        # V19: Resolve verifier LLM with overrides
                        v_llm = self.container.get_verifier_llm(overrides=llm_overrides) if llm_overrides else self.plan_verifier.llm
                        verification = await self.plan_verifier.averify(
                            user_query=user_input,
                            plan=plan_steps,
                            tool_results=tool_outputs,
                            llm_override=v_llm if llm_overrides else None
                        )
                        recorder.log(
                            "Verifier", 
                            f"Verdict: {verification['verdict']}", 
                            metadata={"reason": verification['reason']}
                        )
            
            # V10.3: Record turn (Sync)
            self.summary_memory.add_turn("user", user_input, trace_id=request_id)
            
            # 5. Response (Async)
            state.record_llm_call("responding")
            print(f" Async Response Phase")
            
            # V15.4: Get unified context from ContextManager
            # V19-FIX: Thread RequestState through ContextManager
            resp_ctx = self.context_manager.get_context_for_llm(
                user_input,
                state=req_state
            )
            
            # V15: Inject mood from DesireSystem
            mood_prompt = self.desire_system.get_mood_prompt()
            # V19-FIX-02: Inject reference resolution into responder context
            # This ensures the LLM actually sees what "that"/"it" refers to
            responder_parts = [mood_prompt, resp_ctx['responder_context']]
            if reference_context:
                responder_parts.insert(1, reference_context)
            responder_context = "\n\n".join(filter(None, responder_parts))
            
            # V18 FIX-12: Detect ephemeral handle in tool outputs
            has_ephemeral = (
                "Ephemeral Store ID:" in tool_outputs 
                if tool_outputs else False
            )
            
            resp_context = ResponseContext(
                user_input=user_input,
                tool_outputs=tool_outputs,
                history=history,
                graph_context=responder_context,
                intent_adjustment=mood_prompt,
                current_mood=resp_ctx.get("current_mood", "Neutral"),
                study_mode=req_state.study_mode,
                data_reasoning=has_ephemeral,
                session_summary=resp_ctx.get("summary_context", ""),
                requires_facts=(route_result.classification in ("DIRECT", "PLAN"))
            )
            
            with span("Responder"):
                # Use override LLM if provided
                res_llm = self.container.get_responder_llm(overrides=llm_overrides) if llm_overrides else self.responder.llm
                response_text = await self.responder.agenerate(resp_context, llm_override=res_llm if llm_overrides else None)
            recorder.log("Responder", f"Generated {len(response_text)} chars")
            
            # V15: Update desire state on messages
            self.desire_system.on_user_message(user_input)
            self.desire_system.on_assistant_message(response_text)
            
            # Record assistant response (Sync)
            self.summary_memory.add_turn("assistant", response_text, trace_id=request_id)
            
            # V18.2: Memory Judger (BUG-03 FIX)
            # Fire-and-forget: Evaluate if this turn should be stored in long-term memory.
            # Runs on ALL routes (CHAT, DIRECT, PLAN).
            import asyncio
            asyncio.create_task(
                self.memory_judger.evaluate(
                    user_input=user_input,
                    assistant_response=response_text,
                    trace_id=recorder.current_trace_id()
                )
            )
            
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
            
            # V17.5: Calculate token usage
            from ..utils.token_counter import count_messages_tokens
            
            # Reconstruct prompt messages for verified counting
            prompt_msgs = history + [{"role": "user", "content": user_input}]
            
            # Get model name from container config
            model_name = self.container.config.responder_model
            
            usage = count_messages_tokens(prompt_msgs + [{"role": "assistant", "content": response_text}], model_name)
            
            # V17: Emit response via ResponseEmitter (guaranteed emission)
            await emitter.emit(response_text, {
                "status": "success",
                "latency": f"{time.time()-start_time:.2f}s",
                "tokens": usage  # Inject token metrics
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
            
        except (RateLimitExceeded, LLMBudgetExceededError):
            recorder.end_trace(success=False, response_preview="budget_exceeded")
            error_response = "I'm working too hard and hit a rate limit. Please try again in a moment."
            await emitter.emit(error_response, {"status": "budget_exceeded"})
            mode_val = route_result.classification if 'route_result' in locals() else "unknown"
            return {
                "content": error_response,
                "mode": mode_val,
                "tool_used": "None",
                "tools_used": [],
                "metadata": {
                    "status": "error",
                    "execution_status": "failed",
                    "tool_used": "None",
                    "tools_used": [],
                    "error": "budget_exceeded"
                }
            }
        except Exception as e:
            recorder.end_trace(success=False, response_preview=str(e)[:50])
            print(f" Async Pipeline Error: {e}")
            import traceback
            traceback.print_exc()
            error_response = f"I encountered an error: {e}"
            await emitter.emit(error_response, {"status": "error"})
            mode_val = route_result.classification if 'route_result' in locals() else "unknown"
            return {
                "content": error_response,
                "mode": mode_val,
                "tool_used": "None",
                "tools_used": [],
                "metadata": {
                    "status": "error",
                    "execution_status": "failed",
                    "tool_used": "None",
                    "tools_used": [],
                    "error": str(e)
                }
            }
        finally:
            # V17: Guaranteed emission safety net
            if not emitter.was_emitted:
                print(f"   [V17] Response not emitted - using fallback")
                await emitter.emit(
                    "I processed your request but encountered an issue. Please try again.",
                    {"status": "unknown"}
                )
            
            # V19: Clear execution context to prevent leakage across requests in the same thread
            from .execution.context import execution_context_var
            execution_context_var.set(None)
