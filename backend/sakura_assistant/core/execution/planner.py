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
        tool_history: Optional[List] = None
    ) -> List:
        """
        Build message chain for the LLM.
        
        Args:
            user_input: The user's request
            context: Optional graph context or reference information
            tool_history: Previous tool calls and results (for iterative planning)
            
        Returns:
            List of messages ready for LLM
        """
        messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT.format(context=context)),
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
        intent_mode: str = "action"
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
            # Build conversation context
            messages = self._build_messages(user_input, context, tool_history)
            
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
        intent_mode: str = "action"
    ) -> Dict[str, Any]:
        """
        Async version of plan().
        
        Same interface as plan() but uses ainvoke for async contexts.
        """
        try:
            messages = self._build_messages(user_input, context, tool_history)
            
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
