"""
Sakura V18.0: Executor
================================
Single entry point for execution mode dispatch.

v2.1 Design:
- Determines mode using DETERMINISTIC heuristics (no confidence)
- Takes GraphSnapshot at entry
- Threads ExecutionContext through entire pipeline
- Async-only core (no sync wrappers in production)
"""

import re
import time
import uuid
from typing import Optional, List, Dict, Any, Set, TYPE_CHECKING

from ...utils.logging import get_logger

if TYPE_CHECKING:
    from .planner import Planner
    from ..graph.world_graph import WorldGraph

from .context import (
    ExecutionMode, 
    ExecutionContext, 
    ExecutionResult, 
    ExecutionStatus,
    GraphSnapshot,
    execution_context_var,
    LLMBudgetExceededError
)
from .oneshot_runner import OneShotRunner, OneShotArgsIncomplete
from ..routing.micro_toolsets import get_micro_toolset, detect_semantic_intent, resolve_tool_hint

logger = get_logger(__name__)


class Executor:
    """
    Single Responsibility: Decide HOW to execute, then delegate.
    
    v2.1 Design:
    - ASYNC-ONLY (no sync wrappers)
    - DETERMINISTIC mode selection (no confidence gating)
    - Takes GraphSnapshot at entry point
    - Threads ExecutionContext everywhere
    
    Mode Determination:
        CHAT: No tools needed (router classification)
        ONE_SHOT: Single obvious tool with extractable args
        ITERATIVE: Everything else (multi-tool, complex, research)
    """
    
    # Research keywords that trigger extended budget
    RESEARCH_KEYWORDS: Set[str] = {
        "research", "compare", "summarize", "analyze", "deep dive",
        "investigate", "study", "explore", "find all", "comprehensive"
    }
    
    def __init__(
        self,
        one_shot_runner: OneShotRunner,
        react_loop: Any,  # ReActLoop
        world_graph: "WorldGraph",
        tools: List[Any]
    ):
        """
        Initialize Executor.
        
        Args:
            one_shot_runner: OneShotRunner for fast-lane execution
            react_loop: ReActLoop for iterative execution
            world_graph: WorldGraph for snapshotting
            tools: List of available tools
        """
        self.one_shot_runner = one_shot_runner
        self.react_loop = react_loop
        self.world_graph = world_graph
        self.tools = tools
        self.tool_names = {t.name for t in tools}
    
    async def dispatch(
        self,
        user_input: str,
        classification: str,
        tool_hint: Optional[str] = None,
        request_id: Optional[str] = None,
        history: Optional[List[Dict]] = None,  # V17.1: Conversation history
        reference_context: str = "",           # V19-FIX: Threaded reference context
        llm_overrides: Optional[Dict[str, Any]] = None  # V19: request-time overrides
    ) -> ExecutionResult:
        """
        Main dispatch entry point.
        """
        # Generate request ID if not provided
        if not request_id:
            request_id = f"exec_{uuid.uuid4().hex[:8]}"
        
        start_time = time.time()
        
        # 1. Take graph snapshot at entry
        snapshot = GraphSnapshot.from_graph(self.world_graph)
        
        # Resolve tool hint alias before anything else
        tool_hint = resolve_tool_hint(tool_hint)
        
        # 2. Determine execution mode (deterministic)
        mode = self._determine_mode(classification, tool_hint, user_input)
        
        # 3. Check if research query (affects budget)
        is_research = self._is_research_query(user_input)
        
        # 4. Create execution context
        previous_ctx = execution_context_var.get()
        ctx = ExecutionContext.create(
            mode=mode,
            request_id=request_id,
            user_input=user_input,
            snapshot=snapshot,
            is_research=is_research,
            history=history,
            reference_context=reference_context
        )
        if previous_ctx and getattr(previous_ctx, "request_id", None) == request_id:
            ctx.llm_call_count = previous_ctx.llm_call_count
        
        logger.info(
            f" [Executor] Mode: {mode.value}, "
            f"Tool: {tool_hint or 'None'}, "
            f"Budget: {ctx.budget_ms}ms, "
            f"Research: {is_research}"
        )
        
        # 5. Dispatch based on mode
        try:
            if mode == ExecutionMode.CHAT:
                result = ExecutionResult.empty(mode=mode.value)
            
            elif mode == ExecutionMode.ONE_SHOT:
                result = await self._dispatch_one_shot(tool_hint, ctx, llm_overrides=llm_overrides)
            
            elif mode == ExecutionMode.ITERATIVE:
                # V17.3 PRODUCTION GUARD: Disable sharding for complex queries
                is_complex = self._is_multi_step_query(user_input)
                
                if is_complex:
                    logger.info(" [Executor] Complex query detected: Bypassing sharding to provide full toolset")
                    available_tools = self.tools
                else:
                    # V17: TOOL SHARDING
                    intent, hint = detect_semantic_intent(user_input)
                    micro_tools = get_micro_toolset(intent, self.tools, tool_hint=hint or tool_hint)
                    available_tools = micro_tools if micro_tools else self.tools
                    logger.info(f" [Executor] Sharded {len(available_tools)} tools for intent: {intent}")
                
                result = await self._dispatch_iterative(ctx, available_tools, tool_hint=tool_hint, llm_overrides=llm_overrides)
            
            else:
                result = ExecutionResult.error(f"Unknown mode: {mode}")
                result.last_result = {"mode": mode.value}
        
        except LLMBudgetExceededError:
            raise
        except Exception as e:
            logger.error(f" [Executor] Execution failed: {e}")
            result = ExecutionResult.error(str(e), mode=mode.value if 'mode' in locals() else "unknown")
        
        # 6. Log completion
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f" [Executor] Completed in {elapsed_ms:.0f}ms, "
            f"Status: {result.status.value}"
        )
        
        return result
    
    async def _dispatch_one_shot(
        self, 
        tool_name: str, 
        ctx: ExecutionContext,
        llm_overrides: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """Dispatch to ONE_SHOT runner."""
        try:
            return await self.one_shot_runner.aexecute(tool_name, ctx, llm_overrides=llm_overrides)
        except OneShotArgsIncomplete as e:
            logger.warning(f"⚠️ [Executor] ONE_SHOT failed for '{e.tool_name}', missing: {e.missing_fields}. Falling back to ITERATIVE.")
            new_ctx = ExecutionContext.create(
                mode=ExecutionMode.ITERATIVE,
                request_id=ctx.request_id,
                user_input=ctx.user_input,
                snapshot=ctx.snapshot,
                is_research=False
            )
            new_ctx.llm_call_count = ctx.llm_call_count
            return await self._dispatch_iterative(new_ctx, llm_overrides=llm_overrides)
    
    async def _dispatch_iterative(self, ctx: ExecutionContext, available_tools: Optional[List] = None, tool_hint: Optional[str] = None, llm_overrides: Optional[Dict[str, Any]] = None) -> ExecutionResult:
        """Dispatch to ReAct loop."""
        result = await self.react_loop.arun(
            ctx=ctx,
            available_tools=available_tools or self.tools,
            tool_hint=tool_hint,
            llm_overrides=llm_overrides
        )

        # V19.5: PlanVerifier Integration
        try:
            from .verifier import PlanVerifier
            from ..infrastructure import get_container
            
            # Use the verifier LLM from container
            verifier = PlanVerifier(get_container().get_verifier_llm())
            
            # Format executed steps for verifier
            executed_steps = []
            for msg in result.tool_messages:
                # msg is a ToolMessage or dict
                name = getattr(msg, 'name', msg.get('name') if isinstance(msg, dict) else 'unknown')
                executed_steps.append({"tool": name, "args": "Arguments not captured in trace"})

            verification = await verifier.averify(
                user_query=ctx.user_input,
                plan=executed_steps,
                tool_results=result.outputs
            )
            
            if verification.get("verdict") == "FAIL":
                logger.warning(f"⚠️ [Verifier] Plan failed validation: {verification.get('reason')}")
                result.status = ExecutionStatus.FAILED
                
        except Exception as e:
            logger.warning(f" [Verifier] Integration error: {e}")

        return result

    def _determine_mode(
        self, 
        classification: str, 
        tool_hint: Optional[str],
        user_input: str
    ) -> ExecutionMode:
        """Determine execution mode."""
        if classification == "CHAT":
            return ExecutionMode.CHAT
        
        if classification == "DIRECT" and tool_hint:
            actual_tool = tool_hint
            if actual_tool not in self.tool_names:
                return ExecutionMode.ITERATIVE
            
            if not OneShotRunner.can_handle(tool_hint):
                return ExecutionMode.ITERATIVE
            
            if self._is_multi_step_query(user_input):
                return ExecutionMode.ITERATIVE
            
            return ExecutionMode.ONE_SHOT
        
        return ExecutionMode.ITERATIVE
    
    def _is_multi_step_query(self, text: str) -> bool:
        """Detect if query requires multiple steps."""
        text_lower = text.lower()
        connectors = ["then", "after that", "and then", "and also", "as well as", "followed by", "afterwards", "later"]
        if any(c in text_lower for c in connectors):
            return True
        
        action_verbs = ["open", "play", "search", "find", "get", "set", "create", "send", "check", "read", "write", "delete", "show", "launch", "start", "run", "look up", "google", "remind", "timer"]
        found_verbs = []
        for v in action_verbs:
            if re.search(r'\b' + re.escape(v) + r'\b', text_lower):
                found_verbs.append(v)
        
        if len(set(found_verbs)) >= 2:
            return True
        
        if (" and " in text_lower or ", " in text_lower or " also " in text_lower) and len(found_verbs) >= 1:
            return True

        return False
    
    def _is_research_query(self, text: str) -> bool:
        """Check if this is a research query."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.RESEARCH_KEYWORDS)
