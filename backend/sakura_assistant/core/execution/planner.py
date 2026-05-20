"""
Sakura Multi-Step Planner (ReAct Loop)
=====================================
A clean, lightweight planning engine that handles complex multi-step tool calls
when the Router classifies the query as a PLAN task.
"""

import time
import logging
from typing import Dict, Any, Optional, List
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from .context import ExecutionResult, ExecutionStatus

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are Sakura's reasoning engine. Your goal is to solve the user's request using the available tools.
Solve the request step-by-step. You can run one or more tools sequentially to gather information or perform actions.

Guidelines:
1. Be direct. Run tools as needed.
2. Analyze the tool outputs objectively.
3. Once you have all the necessary information, output your final conclusion.
4. Do not narrate your thoughts to the user, keep your responses factual and direct.
"""

class MultiStepPlanner:
    def __init__(self, tool_map: Dict[str, Any], llm: Any):
        self.tool_map = tool_map
        self.llm = llm

    async def aexecute(self, ctx: Any, llm_overrides: Optional[Dict[str, Any]] = None) -> ExecutionResult:
        start_time = time.time()
        user_input = ctx.user_input
        logger.info(f"[MultiStepPlanner] Starting planning loop for: {user_input[:80]}")

        # Bind all tools to the LLM
        tools_list = list(self.tool_map.values())
        bound_llm = self.llm.bind_tools(tools_list)

        # Initialize messages for the loop
        messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=user_input)
        ]

        tool_messages = []
        last_tool_used = "None"
        last_output = ""
        success = True
        max_turns = 4
        
        for turn in range(max_turns):
            logger.info(f"[MultiStepPlanner] Turn {turn + 1}/{max_turns}")
            try:
                response = await bound_llm.ainvoke(messages)
            except Exception as e:
                logger.error(f"[MultiStepPlanner] LLM invocation failed: {e}")
                return ExecutionResult.error(f"Planning failed: {e}")

            messages.append(response)

            # If there are no tool calls, we are done
            if not response.tool_calls:
                logger.info("[MultiStepPlanner] Loop finished: no further tools requested.")
                last_output = response.content
                break

            # Process tool calls
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                logger.info(f"[MultiStepPlanner] LLM requested tool: {tool_name} with args: {tool_args}")

                if tool_name not in self.tool_map:
                    from ..routing.micro_toolsets import resolve_tool_hint
                    resolved_name = resolve_tool_hint(tool_name)
                    if resolved_name in self.tool_map:
                        tool_name = resolved_name
                    else:
                        output = f"Error: Tool '{tool_name}' not found."
                        t_msg = ToolMessage(content=output, name=tool_name, tool_call_id=tool_call.get("id", "plan_err"))
                        messages.append(t_msg)
                        tool_messages.append(t_msg)
                        continue

                tool_instance = self.tool_map[tool_name]
                last_tool_used = tool_name

                # Check security pathing for system files
                if tool_name in ["file_read", "file_write", "open_app"]:
                    from .oneshot_runner import _sanitize_path, SecurityError
                    path_key = "path" if "path" in tool_args else ("app_name" if "app_name" in tool_args else "filename")
                    if path_key in tool_args:
                        try:
                            tool_args[path_key] = _sanitize_path(tool_args[path_key])
                        except SecurityError as sec_err:
                            output = str(sec_err)
                            t_msg = ToolMessage(content=output, name=tool_name, tool_call_id=tool_call.get("id", "plan_sec"))
                            messages.append(t_msg)
                            tool_messages.append(t_msg)
                            success = False
                            continue
                
                # Execute tool
                try:
                    import asyncio
                    if hasattr(tool_instance, 'ainvoke'):
                        res = await tool_instance.ainvoke(tool_args)
                    else:
                        res = await asyncio.to_thread(tool_instance.invoke, tool_args)
                    output = str(res)
                except Exception as ex:
                    logger.error(f"[MultiStepPlanner] Tool {tool_name} failed: {ex}")
                    output = f"Error running tool '{tool_name}': {ex}"
                    success = False

                t_msg = ToolMessage(
                    content=output,
                    name=tool_name,
                    tool_call_id=tool_call.get("id", f"plan_{tool_name}_{int(time.time())}")
                )
                messages.append(t_msg)
                tool_messages.append(t_msg)
                last_output = output
        
        # Log to Flight Recorder
        try:
            from ...utils.flight_recorder import get_recorder
            recorder = get_recorder()
            recorder.span(
                stage="Planner",
                status="SUCCESS" if success else "FAILED",
                content=f"MultiStepPlanner execution completed in {time.time() - start_time:.2f}s",
                trace_id=recorder.trace_id,
                tool=last_tool_used,
                args={"max_turns": max_turns, "turns_run": len(tool_messages)},
                result=last_output[:500]
            )
        except Exception as log_err:
            logger.warning(f"[MultiStepPlanner] Logging failed: {log_err}")

        return ExecutionResult(
            outputs=last_output,
            tool_messages=tool_messages,
            tool_used=last_tool_used,
            last_result={
                "tool": last_tool_used,
                "output": last_output,
                "success": success
            },
            status=ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED
        )
