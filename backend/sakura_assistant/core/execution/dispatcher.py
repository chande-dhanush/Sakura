"""
Sakura V17: Executor
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
from typing import Optional, List, Any, Set, TYPE_CHECKING

from ...utils.logging import get_logger

if TYPE_CHECKING:
    from .planner import Planner
    from ..graph.world_graph import WorldGraph

from .context import (
    ExecutionMode, 
    ExecutionContext, 
    ExecutionResult, 
    ExecutionStatus,
    GraphSnapshot
)
from .oneshot_runner import OneShotRunner, OneShotArgsIncomplete
from ..routing.micro_toolsets import get_micro_toolset, detect_semantic_intent

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
        request_id: Optional[str] = None
    ) -> ExecutionResult:
        """
        Main dispatch entry point.
        
        Args:
            user_input: User's query
            classification: Router classification (CHAT, DIRECT, PLAN)
            tool_hint: Optional tool hint from router
            request_id: Optional request ID for tracing
        
        Returns:
            ExecutionResult
        """
        # Generate request ID if not provided
        if not request_id:
            request_id = f"exec_{uuid.uuid4().hex[:8]}"
        
        start_time = time.time()
        
        # 1. Take graph snapshot at entry
        snapshot = GraphSnapshot.from_graph(self.world_graph)
        
        # 2. Determine execution mode (deterministic)
        mode = self._determine_mode(classification, tool_hint, user_input)
        
        # 3. Check if research query (affects budget)
        is_research = self._is_research_query(user_input)
        
        # 4. Create execution context
        ctx = ExecutionContext.create(
            mode=mode,
            request_id=request_id,
            user_input=user_input,
            snapshot=snapshot,
            is_research=is_research
        )
        
        logger.info(
            f" [Executor] Mode: {mode.value}, "
            f"Tool: {tool_hint or 'None'}, "
            f"Budget: {ctx.budget_ms}ms, "
            f"Research: {is_research}"
        )
        
        # 5. Dispatch based on mode
        try:
            if mode == ExecutionMode.CHAT:
                result = ExecutionResult.empty()
            
            elif mode == ExecutionMode.ONE_SHOT:
                result = await self._dispatch_one_shot(tool_hint, ctx)
            
            elif mode == ExecutionMode.ITERATIVE:
                # V17.3 PRODUCTION GUARD: Disable sharding for complex queries
                is_complex = self._is_multi_step_query(user_input)
                
                if is_complex:
                    logger.info(" [Executor] Complex query detected: Bypassing sharding to provide full toolset")
                    available_tools = self.tools
                else:
                    # V17: TOOL SHARDING (Optimization for single-intent iterative)
                    intent, hint = detect_semantic_intent(user_input)
                    micro_tools = get_micro_toolset(intent, self.tools, tool_hint=hint or tool_hint)
                    available_tools = micro_tools if micro_tools else self.tools
                    logger.info(f" [Executor] Sharded {len(available_tools)} tools for intent: {intent}")
                
                result = await self._dispatch_iterative(ctx, available_tools)
            
            else:
                result = ExecutionResult.error(f"Unknown mode: {mode}")
        
        except Exception as e:
            logger.error(f" [Executor] Execution failed: {e}")
            result = ExecutionResult.error(str(e))
        
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
        ctx: ExecutionContext
    ) -> ExecutionResult:
        """
        Dispatch to ONE_SHOT runner.
        
        If ONE_SHOT fails (args incomplete), falls back to ITERATIVE.
        """
        try:
            return await self.one_shot_runner.aexecute(tool_name, ctx)
        
        except OneShotArgsIncomplete as e:
            logger.warning(
                f"⚠️ [Executor] ONE_SHOT failed for '{e.tool_name}', "
                f"missing: {e.missing_fields}. Falling back to ITERATIVE."
            )
            # Create new context with ITERATIVE mode
            new_ctx = ExecutionContext.create(
                mode=ExecutionMode.ITERATIVE,
                request_id=ctx.request_id,
                user_input=ctx.user_input,
                snapshot=ctx.snapshot,
                is_research=False
            )
            return await self._dispatch_iterative(new_ctx)
    
    async def _dispatch_iterative(self, ctx: ExecutionContext, available_tools: Optional[List] = None) -> ExecutionResult:
        """Dispatch to ReAct loop."""
        return await self.react_loop.arun(
            ctx=ctx,
            available_tools=available_tools or self.tools
        )
    
    def _determine_mode(
        self, 
        classification: str, 
        tool_hint: Optional[str],
        user_input: str
    ) -> ExecutionMode:
        """
        Determine execution mode using DETERMINISTIC heuristics.
        
        v2.1: NO confidence gating. Pure logic.
        
        Rules:
            CHAT → CHAT (no execution)
            DIRECT + tool_hint + extractable → ONE_SHOT
            Otherwise → ITERATIVE (safe fallback)
        """
        # Rule 1: CHAT classification → CHAT mode
        if classification == "CHAT":
            return ExecutionMode.CHAT
        
        # Rule 2: DIRECT with valid, extractable tool → ONE_SHOT
        if classification == "DIRECT" and tool_hint:
            # V17.3: Resolve hint before checking existence (e.g., youtube_control -> play_youtube)
            actual_tool = OneShotRunner.HINT_MAPPING.get(tool_hint, tool_hint)
            
            # Check 1: Tool exists
            if actual_tool not in self.tool_names:
                logger.warning(
                    f"⚠️ [Executor] Tool '{tool_hint}' (resolved to '{actual_tool}') not found, "
                    f"downgrading to ITERATIVE"
                )
                return ExecutionMode.ITERATIVE
            
            # Check 2: Tool is extractable (has known regex patterns)
            if not OneShotRunner.can_handle(tool_hint):
                logger.info(
                    f"ℹ️ [Executor] Tool '{tool_hint}' not in EXTRACTABLE_TOOLS, "
                    f"using ITERATIVE"
                )
                return ExecutionMode.ITERATIVE
            
            # Check 3: Query isn't too complex (multi-step)
            if self._is_multi_step_query(user_input):
                logger.info(
                    f"ℹ️ [Executor] Multi-step query detected, "
                    f"using ITERATIVE"
                )
                return ExecutionMode.ITERATIVE
            
            return ExecutionMode.ONE_SHOT
        
        # Rule 3: Everything else → ITERATIVE (safe fallback)
        return ExecutionMode.ITERATIVE
    
    def _is_multi_step_query(self, text: str) -> bool:
        """
        Detect if query requires multiple steps.
        
        V17.3 PRODUCTION GUARD: 
        - Catches subtle conjunctions
        - Enforces multi-verb rule
        - Higher sensitivity for commas
        """
        text_lower = text.lower()
        
        # 1. Explicit Sequential Connectors (Guaranteed Multi-Step)
        connectors = [
            "then", "after that", "and then", "and also", "as well as", 
            "followed by", "afterwards", "later"
        ]
        if any(c in text_lower for c in connectors):
            return True
        
        # 2. Subtle Conjunctions (High Probability)
        # Search for " and ", " also ", " plus " but exclude simple object lists
        if " and " in text_lower or ", " in text_lower or " also " in text_lower:
            # If we find a conjunction, we check for multi-verb patterns
            pass
        
        # 3. Action Verb Counting (State Machine of Intent)
        action_verbs = [
            "open", "play", "search", "find", "get", "set", "create",
            "send", "check", "read", "write", "delete", "show", "launch",
            "start", "run", "look up", "google", "remind", "timer"
        ]
        
        # We look for verbs that are NOT part of the same phrase
        # e.g., "play music" (1), "play music and open code" (2)
        found_verbs = []
        for v in action_verbs:
            if re.search(r'\b' + re.escape(v) + r'\b', text_lower):
                found_verbs.append(v)
        
        # Deduplicate and check count
        unique_verbs = set(found_verbs)
        if len(unique_verbs) >= 2:
            return True
        
        # 4. Conjunction + Any Action Verb (e.g., "Check mail and alert me")
        if (" and " in text_lower or ", " in text_lower or " also " in text_lower) and len(unique_verbs) >= 1:
            # Special case: "play music and songs" vs "play music and open app"
            # If 2+ verbs, it's definitely multi-step (handled in section 3)
            # If 1 verb + "and", we check if the sentence looks like a command list
            if len(unique_verbs) == 1:
                # If the conjunction appears after the first verb and object, it might be a new command
                # But for safety in V17.3, we'll force ITERATIVE for any 'and' with an action verb
                # to ensure the Planner can resolve any hidden intent.
                return True
            return True

        return False
    
    def _is_research_query(self, text: str) -> bool:
        """Check if this is a research query (extended budget)."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.RESEARCH_KEYWORDS)
