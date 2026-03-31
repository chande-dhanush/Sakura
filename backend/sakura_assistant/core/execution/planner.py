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
from ...config import PLANNER_SYSTEM_PROMPT


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
        history: Optional[List[Dict]] = None  # V17.1: Conversation history
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
        # ✅ DEBUG LOGGING FOR HISTORY INJECTION
        print(f"🐛 [Planner] history={history is not None}, len={len(history) if history else 0}")

        # V17.1: Inject conversation context for reference resolution
        full_context = context
        if history:
            recent_turns = history[-4:]  # Last 4 turns
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
        
        return messages
    
    def plan(
        self, 
        user_input: str, 
        context: str = "",
        tool_history: Optional[List] = None,
        available_tools: Optional[List] = None,
        intent_mode: str = "action",
        history: Optional[List[Dict]] = None  # V17.1
    ) -> Dict[str, Any]:
        """
        Generate a plan for the user's request.
        
        Args:
            user_input: What the user wants
            context: Optional context (graph references, etc.)
            tool_history: Previous steps in an iterative session
            available_tools: Tools the LLM can choose from (provided by caller)
            
        Returns:
            {
                "steps": [
                    {"id": 1, "tool": "search_web", "args": {...}},
                    {"id": 2, "tool": "summarize", "args": {...}}
                ],
                "complete": False,  # True if no more steps needed
                "message": <AIMessage>  # Raw LLM response
            }
        """
        try:
            # Build conversation context (V17.1: include history)
            messages = self._build_messages(user_input, context, tool_history, history)
            
            # Bind tools if provided
            if available_tools:
                llm_with_tools = self.llm.bind_tools(available_tools)
            else:
                llm_with_tools = self.llm
            
            # Ask LLM to plan
            response = llm_with_tools.invoke(messages)
            
            # Parse tool calls into clean step format
            if response.tool_calls:
                steps = [
                    {
                        "id": i + 1,
                        "tool": call["name"],
                        "args": call["args"],
                        "tool_call_id": call.get("id")
                    }
                    for i, call in enumerate(response.tool_calls)
                ]
                
                return {
                    "steps": steps,
                    "complete": False,
                    "message": response
                }
            else:
                # V18 FIX-03: Anti-hallucination gate
                # If tools were bound but LLM answered from training data,
                # retry ONCE with a strong enforcement message.
                # Only fires when available_tools were passed (not pure CHAT).
                if available_tools:
                    print(f"⚠️ [Planner] No tool calls despite {len(available_tools)} tools bound. Retrying with enforcement...")
                    tool_names = [t.name for t in available_tools[:10]]
                    enforcement_msg = HumanMessage(
                        content=(
                            "SYSTEM OVERRIDE: You MUST call a tool. You answered from "
                            "training data. Your text answer will be DISCARDED. "
                            "Call the most relevant tool NOW. "
                            f"Available: {tool_names}"
                        )
                    )
                    retry_messages = messages + [response, enforcement_msg]
                    retry_response = llm_with_tools.invoke(retry_messages)
                    
                    if retry_response.tool_calls:
                        print(f"✅ [Planner] Enforcement succeeded: {len(retry_response.tool_calls)} tool call(s)")
                        steps = [
                            {
                                "id": i + 1,
                                "tool": call["name"],
                                "args": call["args"],
                                "tool_call_id": call.get("id")
                            }
                            for i, call in enumerate(retry_response.tool_calls)
                        ]
                        return {
                            "steps": steps,
                            "complete": False,
                            "message": retry_response
                        }
                    else:
                        print(f"⚠️ [Planner] Enforcement failed — LLM still refused tools")
                
                # No tool calls = either chat response or task complete
                return {
                    "steps": [],
                    "complete": True,
                    "message": response
                }
                
        except Exception as e:
            # Let errors bubble up to caller
            # Planner doesn't handle retries - that's Executor's job
            return {
                "steps": [],
                "complete": False,
                "error": str(e),
                "message": None
            }
    
    async def aplan(
        self, 
        user_input: str, 
        context: str = "",
        tool_history: Optional[List] = None,
        available_tools: Optional[List] = None,
        intent_mode: str = "action",
        history: Optional[List[Dict]] = None  # V17.1
    ) -> Dict[str, Any]:
        """
        Async version of plan().
        
        Same interface as plan() but uses ainvoke for async contexts.
        """
        try:
            messages = self._build_messages(user_input, context, tool_history, history)
            
            if available_tools:
                llm_with_tools = self.llm.bind_tools(available_tools)
            else:
                llm_with_tools = self.llm
            
            response = await llm_with_tools.ainvoke(messages)
            
            if response.tool_calls:
                steps = [
                    {
                        "id": i + 1,
                        "tool": call["name"],
                        "args": call["args"],
                        "tool_call_id": call.get("id")
                    }
                    for i, call in enumerate(response.tool_calls)
                ]
                
                return {
                    "steps": steps,
                    "complete": False,
                    "message": response
                }
            else:
                # V18 FIX-03: Anti-hallucination gate (async path)
                # If tools were bound but LLM answered from training data,
                # retry ONCE with a strong enforcement message.
                if available_tools:
                    print(f"⚠️ [Planner] No tool calls despite {len(available_tools)} tools bound. Retrying with enforcement... (async)")
                    tool_names = [t.name for t in available_tools[:10]]
                    enforcement_msg = HumanMessage(
                        content=(
                            "SYSTEM OVERRIDE: You MUST call a tool. You answered from "
                            "training data. Your text answer will be DISCARDED. "
                            "Call the most relevant tool NOW. "
                            f"Available: {tool_names}"
                        )
                    )
                    retry_messages = messages + [response, enforcement_msg]
                    retry_response = await llm_with_tools.ainvoke(retry_messages)
                    
                    if retry_response.tool_calls:
                        print(f"✅ [Planner] Enforcement succeeded: {len(retry_response.tool_calls)} tool call(s) (async)")
                        steps = [
                            {
                                "id": i + 1,
                                "tool": call["name"],
                                "args": call["args"],
                                "tool_call_id": call.get("id")
                            }
                            for i, call in enumerate(retry_response.tool_calls)
                        ]
                        return {
                            "steps": steps,
                            "complete": False,
                            "message": retry_response
                        }
                    else:
                        print(f"⚠️ [Planner] Enforcement failed — LLM still refused tools (async)")
                
                return {
                    "steps": [],
                    "complete": True,
                    "message": response
                }
                
        except Exception as e:
            return {
                "steps": [],
                "complete": False,
                "error": str(e),
                "message": None
            }
