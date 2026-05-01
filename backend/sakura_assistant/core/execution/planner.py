"""
Planner Module - Single Responsibility Refactor

Core Responsibility:
    - Receives user request + context + tool history
    - Decides what logical steps are needed
    - Returns a declarative plan
    
NOT Responsible For:
    - Routing (handled by Intent Router)
    - Tool filtering (handled upstream)
    - Execution (handled by Executor)
    - Caching (handled by Executor or Router)
    - UI state (handled by Executor)
    - Retry logic (handled by Executor)
"""

from typing import Dict, Any, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from ...config import PLANNER_SYSTEM_PROMPT, PLANNER_RETRY_PROMPT


class Planner:
    """
    Minimal planner that decides WHAT to do, not HOW to do it.
    
    Input: User request, context, previous steps
    Output: Ordered list of logical steps
    """
    
    def __init__(self, llm):
        """Initialize planner with an LLM."""
        self.llm = llm
    
    def _build_messages(
        self, 
        user_input: str, 
        context: str = "",
        tool_history: Optional[List] = None,
        history: Optional[List[Dict]] = None,  # V17.1: Conversation history
        hindsight: Optional[str] = None, # FIX-4: Retry feedback
        executed_tools: Optional[List[str]] = None, # BUG-02
        tool_hint: Optional[str] = None # VERIFICATION-03
    ) -> List:
        """
        Build message chain for the LLM.
        
        Args:
            user_input: The user's request
            context: Optional graph context or reference information
            tool_history: Previous tool calls and results (for iterative planning)
            history: V17.1 - Conversation history for reference resolution
            
        Returns:
            List of messages ready for LLM
        """
        #   DEBUG LOGGING FOR HISTORY INJECTION
        print(f"  [Planner] history={history is not None}, len={len(history) if history else 0}")

        # V17.1: Inject conversation context for reference resolution
        full_context = context
        
        # BUG-02: Inject already executed tools
        if executed_tools:
            already_ran_str = ", ".join(executed_tools)
            full_context = f"{full_context}\n\n[ALREADY RAN]: {already_ran_str}"
            
        if history:
            recent_turns = history[-5:]  # VERIFICATION-03: Cap history at 5 turns
            conv_lines = []
            for turn in recent_turns:
                role = turn.get("role", "unknown")
                content = turn.get("content", "")[:200]  # Truncate
                conv_lines.append(f"  {role.upper()}: {content}")
            if conv_lines:
                full_context = f"{context}\n\n[RECENT CONVERSATION CONTEXT]\n" + "\n".join(conv_lines)
        
        messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT.format(context=full_context)),
            HumanMessage(content=f"Request: {user_input}")
        ]
        
        # Add tool history if this is an iterative planning session
        if tool_history:
            messages.extend(tool_history)
            # Remind the planner of the original goal
            messages.append(
                HumanMessage(
                    content=f"Original request: \"{user_input}\"\n\n"
                            f"Based on the results above, what should happen next? "
                            f"If the goal is complete, indicate no further steps are needed."
                )
            )
        
        # FIX-4: Inject Retry Prompt if hindsight provided
        if hindsight:
            messages.append(
                SystemMessage(
                    content=PLANNER_RETRY_PROMPT.format(
                        hindsight=hindsight,
                        user_input=user_input,
                        context=context
                    )
                )
            )
        
        return messages
    
    def _filter_tools(self, available_tools: List, tool_hint: str) -> List:
        """
        Filter tools based on hint while ensuring core capabilities are present
        only if the filtered set is empty or invalid.
        """
        from ..routing.micro_toolsets import MICRO_TOOLSETS, UNIVERSAL_TOOLS, SEARCH_TOOLS, resolve_tool_hint
        
        target_names = set()
        
        # 1. Exact match on resolved hint
        resolved_hint = resolve_tool_hint(tool_hint)
        if resolved_hint:
            target_names.add(resolved_hint)
        
        # 2. Category match
        if tool_hint in MICRO_TOOLSETS:
            target_names.update(MICRO_TOOLSETS[tool_hint]["primary"])
            
        filtered = [t for t in available_tools if t.name in target_names]
        
        # 3. Fallback to baseline if filtered set is empty
        if not filtered:
            print(f"   [Planner] Filtered toolset for hint '{tool_hint}' is empty. Falling back to baseline.")
            baseline_categories = ["music", "search", "system"]
            baseline_tools = set(UNIVERSAL_TOOLS)
            for cat in baseline_categories:
                if cat in MICRO_TOOLSETS:
                    baseline_tools.update(MICRO_TOOLSETS[cat]["primary"])
            baseline_tools.update(SEARCH_TOOLS)
            
            filtered = [t for t in available_tools if t.name in baseline_tools]
            
            # Absolute fallback
            if not filtered:
                filtered = available_tools
                
        return filtered

    def plan(
        self, 
        user_input: str, 
        context: str = "",
        tool_history: Optional[List] = None,
        available_tools: Optional[List] = None,
        intent_mode: str = "action",
        history: Optional[List[Dict]] = None,  # V17.1
        hindsight: Optional[str] = None,  # FIX-4
        executed_tools: Optional[List[str]] = None, # BUG-02
        tool_hint: Optional[str] = None # VERIFICATION-03
    ) -> Dict[str, Any]:
        """
        Generate a plan for the user's request.
        """
        # V18.4 VERIFICATION-03: Filter tools based on hint to save tokens
        filtered_tools = available_tools
        if tool_hint and available_tools:
            filtered_tools = self._filter_tools(available_tools, tool_hint)
            if len(filtered_tools) < len(available_tools):
                print(f"  [Planner] Filtered tools: {len(available_tools)} -> {len(filtered_tools)} (Hint: {tool_hint})")

        # Build conversation context (V17.1: include history)
        messages = self._build_messages(
            user_input, 
            context, 
            tool_history, 
            history, 
            hindsight, 
            executed_tools, 
            tool_hint
        )
        
        # Bind tools if provided
        active_llm = self.llm
        if filtered_tools:
            # V10.2: Enforce tool usage on initial plan
            force_tool = not tool_history
            tool_choice = "any" if force_tool else "auto"
            
            try:
                active_llm = self.llm.bind_tools(filtered_tools, tool_choice=tool_choice)
                if force_tool:
                    print("   [Planner] Enforcing tool usage (tool_choice='any')")
            except TypeError:
                print("   [Planner] Model doesn't support tool_choice, falling back to soft-prompt")
                active_llm = self.llm.bind_tools(filtered_tools)
        
        print(f"  [Planner] Generating plan... ({len(filtered_tools) if filtered_tools else 0} tools available)")
        
        # V18.3 BUG-08: Use invoke directly, self.llm handles retries implicitly
        response = active_llm.invoke(messages)
        
        # Process tool calls
        if hasattr(response, 'tool_calls') and response.tool_calls:
            steps = []
            for i, call in enumerate(response.tool_calls):
                steps.append({
                    "id": i + 1,
                    "tool": call['name'],
                    "args": call['args']
                })
            
            return {
                "steps": steps,
                "complete": False,
                "message": response
            }
        else:
            # V10.2 Anti-Hallucination: If tool forced but ignored
            if filtered_tools and not tool_history:
                print(f"   [Planner] Model ignored tool_choice='any', applying soft-retry")
                messages.append(response)
                
                from langchain_core.messages import HumanMessage
                from ...config import PLANNER_RETRY_PROMPT
                messages.append(HumanMessage(content=PLANNER_RETRY_PROMPT))
                
                retry_resp = active_llm.invoke(messages)
                
                if hasattr(retry_resp, 'tool_calls') and retry_resp.tool_calls:
                    print(f"  [Planner] Soft-retry successful")
                    steps = []
                    for i, call in enumerate(retry_resp.tool_calls):
                        steps.append({
                            "id": i + 1,
                            "tool": call['name'],
                            "args": call['args']
                        })
                    return {
                        "steps": steps,
                        "complete": False,
                        "message": retry_resp
                    }
                else:
                    print(f"   [Planner] Enforcement failed   LLM still refused tools")
            
        # No tool calls = either chat response or task complete
        return {
            "steps": [],
            "complete": True,
            "message": response
        }
    
    async def aplan(
        self, 
        user_input: str, 
        context: str = "",
        tool_history: Optional[List] = None,
        available_tools: Optional[List] = None,
        intent_mode: str = "action",
        history: Optional[List[Dict]] = None,
        hindsight: Optional[str] = None,
        executed_tools: Optional[List[str]] = None,
        tool_hint: Optional[str] = None,
        llm_override: Any = None
    ) -> Dict[str, Any]:
        """Async version of planning."""
        # Use provided override or default
        active_llm = llm_override or self.llm
        # V18.4 VERIFICATION-03: Filter tools based on hint to save tokens
        filtered_tools = available_tools
        if tool_hint and available_tools:
            filtered_tools = self._filter_tools(available_tools, tool_hint)
            if len(filtered_tools) < len(available_tools):
                print(f"  [Planner] Filtered tools: {len(available_tools)} -> {len(filtered_tools)} (Hint: {tool_hint})")

        messages = self._build_messages(
            user_input, 
            context, 
            tool_history, 
            history, 
            hindsight, 
            executed_tools, 
            tool_hint
        )
        
        # Bind tools
        if filtered_tools:
            force_tool = not tool_history
            tool_choice = "any" if force_tool else "auto"
            try:
                active_llm = active_llm.bind_tools(filtered_tools, tool_choice=tool_choice)
                if force_tool:
                    print("   [Planner] Enforcing tool usage (tool_choice='any', async)")
            except TypeError:
                print("   [Planner] Model doesn't support tool_choice, falling back to soft-prompt")
                active_llm = active_llm.bind_tools(filtered_tools)
        
        print(f"  [Planner] Generating plan (async)... ({len(filtered_tools) if filtered_tools else 0} tools available)")
        
        response = await active_llm.ainvoke(messages)
        
        if hasattr(response, 'tool_calls') and response.tool_calls:
            steps = []
            for i, call in enumerate(response.tool_calls):
                steps.append({
                    "id": i + 1,
                    "tool": call['name'],
                    "args": call['args']
                })
            
            return {
                "steps": steps,
                "complete": False,
                "message": response
            }
        else:
            if filtered_tools and not tool_history:
                print(f"   [Planner] Model ignored tool_choice='any', applying soft-retry (async)")
                messages.append(response)
                
                from langchain_core.messages import HumanMessage
                from ...config import PLANNER_RETRY_PROMPT
                messages.append(HumanMessage(content=PLANNER_RETRY_PROMPT))
                
                retry_resp = await active_llm.ainvoke(messages)
                
                if hasattr(retry_resp, 'tool_calls') and retry_resp.tool_calls:
                    print(f"  [Planner] Soft-retry successful (async)")
                    steps = []
                    for i, call in enumerate(retry_resp.tool_calls):
                        steps.append({
                            "id": i + 1,
                            "tool": call['name'],
                            "args": call['args']
                        })
                    return {
                        "steps": steps,
                        "complete": False,
                        "message": retry_resp
                    }
                else:
                    print(f"   [Planner] Enforcement failed   LLM still refused tools (async)")
            
        return {
            "steps": [],
            "complete": True,
            "message": response
        }
