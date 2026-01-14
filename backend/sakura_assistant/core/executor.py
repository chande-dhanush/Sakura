"""
Sakura V10 Tool Executor
========================
Executes tool plans with ReAct loop support.

Extracted from llm.py as part of SOLID refactoring.
- Single Responsibility: Only handles tool execution
- Manages output pruning and summarization
"""
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from langchain_core.messages import ToolMessage
from langchain_core.messages import ToolMessage
from .planner import Planner
from .ephemeral_manager import get_ephemeral_manager # V11.3 Context Valve


@dataclass
class ExecutionResult:
    """Result of tool execution."""
    outputs: str                    # Formatted tool output text
    tool_messages: List[ToolMessage]  # For ReAct loop history
    tool_used: str                  # Last tool name used
    last_result: Optional[Dict]     # Last tool result details
    success: bool                   # Overall success status


class ToolExecutor:
    """
    Executes tool plans with ReAct loop support.
    
    Features:
    - Single and multi-step execution
    - Smart output pruning (JSON-aware)
    - Summarization for large outputs
    - ReAct-compatible ToolMessage history
    """
    
    def __init__(self, tools: List, summarizer_llm=None):
        """
        Args:
            tools: List of LangChain tools
            summarizer_llm: Optional LLM for summarizing large outputs
        """
        self.tools = tools
        self.tool_map = {t.name: t for t in tools}
        self.summarizer_llm = summarizer_llm
        if summarizer_llm:
            self.planner = Planner(summarizer_llm)
        else:
            self.planner = None
    
    # V10.3: Misclassification Recovery - Fallback chain for failed tools
    FALLBACK_MAP = {
        "spotify_control": "play_youtube",     # Spotify fails → try YouTube
        "play_youtube": "web_search",          # YouTube fails → search
    }
    
    def _extract_search_term(self, tool_name: str, args: Dict, original_query: str = "") -> str:
        """
        Extract the human-readable search term from tool args.
        Gemini's insight: Can't pass Spotify URI to YouTube - need original query.
        """
        # Priority 1: Named search parameters
        search_keys = ["query", "topic", "song", "track", "search_term", "q"]
        for key in search_keys:
            if key in args and args[key]:
                return str(args[key])
        
        # Priority 2: Action args for Spotify
        if tool_name == "spotify_control" and args.get("action") == "play":
            # If there's a track_name or artist, use that
            if args.get("track_name"):
                return args["track_name"]
            if args.get("query"):
                return args["query"]
        
        # Priority 3: Fall back to original user query
        if original_query:
            return original_query
        
        # Priority 4: Stringify first non-action arg
        for key, val in args.items():
            if key not in ["action", "uri"] and val:
                return str(val)
        
        return ""
    
    def execute_single(self, tool_name: str, args: Dict) -> Tuple[str, bool]:
        """
        Execute a single tool call.
        
        Returns:
            Tuple of (result_string, success_boolean)
        """
        if tool_name not in self.tool_map:
            return f"Error: Tool '{tool_name}' not found.", False
        
        try:
            result = self.tool_map[tool_name].invoke(args)
            return str(result), True
        except Exception as e:
            import traceback
            print(f"❌ TOOL EXECUTION ERROR ❌")
            print(f"   Tool: {tool_name}")
            print(f"   Args: {args}")
            print(f"   Error: {e}")
            traceback.print_exc()
            return f"Error: {e}", False

    async def aexecute(self, user_input: str, route_result: Any, graph_context: str, state: Any = None) -> ExecutionResult:
        """Async version of execute (ReAct loop)."""
        print(f"🔄 [Executor] Starting Async ReAct loop for: {user_input[:50]}...")
        
        all_tool_messages = []
        all_outputs = []
        final_tool_used = "None"
        final_last_result = None
        MAX_REACT_STEPS = 5
        
        for i in range(MAX_REACT_STEPS):
            print(f"🔄 [Executor] Async Iteration {i+1}/{MAX_REACT_STEPS}")
            
            # 1. PLAN (Async)
            if not self.planner:
                return ExecutionResult("Error: No planner configured", [], "Error", None, False)
                
            plan_result = await self.planner.aplan(
                user_input=user_input,
                context=graph_context,
                tool_history=all_tool_messages,
                intent_mode=route_result.classification if hasattr(route_result, 'classification') else "action"
            )
            
            steps = plan_result.get("plan", [])
            if not steps:
                print("⏹️ [Executor] Checkmate - No more steps needed.")
                break
                
            # 2. EXECUTE (Async)
            exec_res = await self.aexecute_plan(steps, state=state)
            
            # 3. OBSERVE
            all_tool_messages.extend(exec_res.tool_messages)
            if exec_res.outputs:
                all_outputs.append(exec_res.outputs)
            
            final_tool_used = exec_res.tool_used
            
            # 4. TERMINAL CHECK
            TERMINAL_ACTIONS = {
                "play_youtube", "spotify_control", "open_app",
                "file_open", "gmail_send_email", "calendar_create_event",
                "tasks_create", "note_create", "set_timer", "set_reminder"
            }
            if final_tool_used in TERMINAL_ACTIONS and exec_res.success:
                print(f"⏹️ [Executor] Terminal action '{final_tool_used}' completed - stopping loop.")
                final_last_result = exec_res.last_result
                break
            
            # Track the last result from each iteration
            final_last_result = exec_res.last_result
            
        return ExecutionResult(
            outputs="\n".join(all_outputs),
            tool_messages=all_tool_messages,
            tool_used=final_tool_used,
            last_result=final_last_result,
            success=True
        )

    async def aexecute_plan(self, steps: List[Dict], state=None, 
                     max_iterations: int = 5,
                     max_output_chars: int = 2000) -> ExecutionResult:
        """Async version of execute_plan."""
        import asyncio
        results_text = []
        tool_messages = []
        tool_used = "None"
        last_result = None
        all_success = True
        
        TERMINAL_ACTIONS = {
            "play_youtube", "spotify_control", "open_app", "open_site",
            "file_open", "gmail_send_email", "calendar_create_event",
            "tasks_create", "note_create", "set_timer", "set_reminder"
        }
        
        steps = steps[:max_iterations]
        
        for step in steps:
            tool_name = step.get("tool")
            tool_args = step.get("args", {})
            call_id = step.get("tool_call_id", f"call_{step.get('id', 0)}")
            
            if tool_name not in self.tool_map:
                err = f"Tool '{tool_name}' not found."
                results_text.append(f"Step {step.get('id')} Error: {err}")
                tool_messages.append(ToolMessage(tool_call_id=call_id, content=err, name=tool_name, status="error"))
                continue
            
            print(f"▶️ Async Executing Step {step.get('id')}: {tool_name} {tool_args}")
            
            # V12: Wait & See Hook (Pacing)
            # Short pause to prevent API blasting and allow UI updates
            import time
            from .broadcaster import broadcast
            
            # Don't sleep on first step, only subsequent
            if step.get('id', 0) > 1:
                broadcast("pacing", {"step": step.get('id'), "tool": tool_name})
                await asyncio.sleep(0.5) 

            # V12: Generic Tool Start Broadcast
            broadcast("tool_start", {"tool": tool_name, "args": tool_args})
            
            try:
                # Run sync tool in thread
                tool_instance = self.tool_map[tool_name]
                if hasattr(tool_instance, 'ainvoke'):
                    # Some tools might support ainvoke natively? Most LangChain tools fallback to sync.
                    # Use ainvoke if available, else tool.invoke
                    res = await tool_instance.ainvoke(tool_args)
                else:
                    res = await asyncio.to_thread(tool_instance.invoke, tool_args)
                
                res_str = str(res)
                
                # Misclassification Recovery Logic (Same as sync)
                failure_indicators = ["not found", "failed", "error", "couldn't", "unable"]
                is_soft_failure = any(ind in res_str.lower() for ind in failure_indicators)
                
                if is_soft_failure and tool_name in self.FALLBACK_MAP:
                    fallback_tool = self.FALLBACK_MAP[tool_name]
                    if fallback_tool in self.tool_map:
                        search_term = self._extract_search_term(tool_name, tool_args)
                        if search_term:
                            print(f"🔄 [Async Recovery] {tool_name} → {fallback_tool} ('{search_term}')")
                            if fallback_tool == "play_youtube": fallback_args = {"topic": search_term}
                            elif fallback_tool == "web_search": fallback_args = {"query": search_term}
                            else: fallback_args = {"query": search_term}
                            
                            fallback_res = await asyncio.to_thread(self.tool_map[fallback_tool].invoke, fallback_args)
                            res_str = f"[Fallback: {fallback_tool}] {fallback_res}"
                            tool_name = fallback_tool
                            is_soft_failure = False
                
                # V11.3 Context Valve: Intercept Large Outputs (Async)
                INTERCEPT_THRESHOLD = 2000
                if len(res_str) > INTERCEPT_THRESHOLD:
                    print(f"🛡️ [Async Executor] Output too large ({len(res_str)} chars). Intercepting...")
                    try:
                        eph_man = get_ephemeral_manager()
                        eph_id = eph_man.ingest_text(res_str, source_tool=tool_name)
                        
                        if eph_id and not eph_id.startswith("error"):
                            # Replace output with handle
                            res_str = (
                                f"[System: Context Overflow Protection]\n"
                                f"Output too large ({len(res_str)} chars) to fit in context.\n"
                                f"Content has been securely indexed to Ephemeral Store ID: {eph_id}\n"
                                f"You MUST use the tool 'query_ephemeral(ephemeral_id=\"{eph_id}\", query=\"...\")' "
                                f"to retrieve specific details/sections."
                            )
                        else:
                            print(f"⚠️ Ephemeral Ingest Failed: {eph_id}")
                    except Exception as ex:
                        print(f"⚠️ Ephemeral Intercept Error: {ex}")

                pruned_res = self.prune_output(res_str)
                tool_messages.append(ToolMessage(tool_call_id=call_id, content=pruned_res, name=tool_name))
                
                if len(res_str) > max_output_chars:
                    res_str = res_str[:max_output_chars] + "... [truncated]"
                
                results_text.append(f"Step {step.get('id')} ({tool_name}): {res_str}")
                tool_used = tool_name
                last_result = {"tool": tool_name, "args": tool_args, "output": res_str, "success": not is_soft_failure}
                
                if state: state.record_tool_result(success=not is_soft_failure)
                
                if tool_name in TERMINAL_ACTIONS:
                    print(f"⏹️ [Async Executor] Terminal action '{tool_name}' completed.")
                    break
                    
            except Exception as e:
                err_msg = f"Error: {e}"
                tool_messages.append(ToolMessage(tool_call_id=call_id, content=err_msg, name=tool_name, status="error"))
                results_text.append(f"Step {step.get('id')} Error: {e}")
                last_result = {"tool": tool_name, "args": tool_args, "output": str(e), "success": False}
                if state: state.record_tool_result(success=False)
        
        outputs = ""
        if results_text:
            outputs = "\n\n=== TOOL EXECUTION LOG ===\n" + "\n".join(results_text)
        
        return ExecutionResult(outputs=outputs, tool_messages=tool_messages, tool_used=tool_used, last_result=last_result, success=all_success)

    def execute(self, user_input: str, route_result: Any, graph_context: str, state: Any = None) -> ExecutionResult:
        """
        Main execution entry point. Runs the ReAct loop.
        """
        print(f"🔄 [Executor] Starting ReAct loop for: {user_input[:50]}...")
        
        all_tool_messages = []
        all_outputs = []
        final_tool_used = "None"
        
        # Max iterations for the loop (Plan -> Act -> Observe -> Plan)
        MAX_REACT_STEPS = 5
        
        for i in range(MAX_REACT_STEPS):
            print(f"🔄 [Executor] Iteration {i+1}/{MAX_REACT_STEPS}")
            
            # 1. PLAN
            if not self.planner:
                return ExecutionResult("Error: No planner configured", [], "Error", None, False)
                
            plan_result = self.planner.plan(
                user_input=user_input,
                context=graph_context,
                tool_history=all_tool_messages,
                intent_mode=route_result.classification if hasattr(route_result, 'classification') else "action"
            )
            
            steps = plan_result.get("plan", [])
            if not steps:
                print("⏹️ [Executor] Checkmate - No more steps needed.")
                break
                
            # 2. EXECUTE
            exec_res = self.execute_plan(steps, state=state)
            
            # 3. OBSERVE (Accumulate history)
            # V11.3: Auto-cleanup of ephemeral stores at end of turn?
            # Ideally handled by server, but we can do a quick check here if needed.
            
            all_tool_messages.extend(exec_res.tool_messages)
            if exec_res.outputs:
                all_outputs.append(exec_res.outputs)
            
            final_tool_used = exec_res.tool_used
            
            # 4. CHECK FOR TERMINAL ACTIONS (Stop loop after completion)
            # These tools complete the user's request - no need for more iterations
            TERMINAL_ACTIONS = {
                "play_youtube", "spotify_control", "open_app",
                "file_open", "gmail_send_email", "calendar_create_event",
                "tasks_create", "note_create", "set_timer", "set_reminder"
            }
            if final_tool_used in TERMINAL_ACTIONS and exec_res.success:
                print(f"⏹️ [Executor] Terminal action '{final_tool_used}' completed - stopping loop.")
                break
            
        return ExecutionResult(
            outputs="\n".join(all_outputs),
            tool_messages=all_tool_messages,
            tool_used=final_tool_used,
            last_result=None,
            success=True
        )
    
    def execute_plan(self, steps: List[Dict], state=None, 
                     max_iterations: int = 5,
                     max_output_chars: int = 2000) -> ExecutionResult:
        """
        Execute multiple tool steps from a plan.
        
        Args:
            steps: List of {"tool": name, "args": {}, "id": n} dicts
            state: Optional AgentState for tracking
            max_iterations: Cap on number of steps
            max_output_chars: Max chars per output
            
        Returns:
            ExecutionResult with all outputs and history
        """
        results_text = []
        tool_messages = []
        tool_used = "None"
        last_result = None
        all_success = True
        
        # V10: Terminal actions that complete a request - stop after first one
        TERMINAL_ACTIONS = {
            "play_youtube", "spotify_control", "open_app", "open_site",
            "file_open", "gmail_send_email", "calendar_create_event",
            "tasks_create", "note_create", "set_timer", "set_reminder"
        }
        terminal_executed = False
        
        # Cap iterations
        steps = steps[:max_iterations]
        if len(steps) > max_iterations:
            print(f"⚠️ Executor: Capped at {max_iterations} steps")
        
        for step in steps:
            tool_name = step.get("tool")
            tool_args = step.get("args", {})
            call_id = step.get("tool_call_id", f"call_{step.get('id', 0)}")
            
            if tool_name not in self.tool_map:
                err = f"Tool '{tool_name}' not found."
                results_text.append(f"Step {step.get('id')} Error: {err}")
                tool_messages.append(ToolMessage(
                    tool_call_id=call_id, 
                    content=err, 
                    name=tool_name, 
                    status="error"
                ))
                all_success = False
                if state:
                    state.record_tool_result(success=False)
                continue
            
            print(f"▶️ Executing Step {step.get('id')}: {tool_name} {tool_args}")
            
            try:
                res = self.tool_map[tool_name].invoke(tool_args)
                res_str = str(res)
                
                # V10.3: Check for "soft failures" (tool ran but couldn't complete)
                failure_indicators = ["not found", "failed", "error", "couldn't", "unable"]
                is_soft_failure = any(ind in res_str.lower() for ind in failure_indicators)
                
                # Try fallback if soft failure and fallback exists
                if is_soft_failure and tool_name in self.FALLBACK_MAP:
                    fallback_tool = self.FALLBACK_MAP[tool_name]
                    if fallback_tool in self.tool_map:
                        # Extract original search term (don't pass Spotify URI to YouTube!)
                        search_term = self._extract_search_term(tool_name, tool_args)
                        if search_term:
                            print(f"🔄 [V10.3] Misclassification recovery: {tool_name} → {fallback_tool}")
                            print(f"   Extracted term: '{search_term}'")
                            
                            # Build fallback args
                            if fallback_tool == "play_youtube":
                                fallback_args = {"topic": search_term}
                            elif fallback_tool == "web_search":
                                fallback_args = {"query": search_term}
                            else:
                                fallback_args = {"query": search_term}
                            
                            # Execute fallback
                            fallback_res = self.tool_map[fallback_tool].invoke(fallback_args)
                            res_str = f"[Fallback: {fallback_tool}] {fallback_res}"
                            tool_name = fallback_tool  # Update for logging
                            is_soft_failure = False  # Recovery succeeded
                
                            is_soft_failure = False  # Recovery succeeded
                
                # V11.3 Context Valve: Intercept Large Outputs
                INTERCEPT_THRESHOLD = 2000
                if len(res_str) > INTERCEPT_THRESHOLD:
                    print(f"🛡️ [Executor] Output too large ({len(res_str)} chars). Intercepting...")
                    try:
                        eph_man = get_ephemeral_manager()
                        eph_id = eph_man.ingest_text(res_str, source_tool=tool_name)
                        
                        if eph_id and not eph_id.startswith("error"):
                            # Replace output with handle
                            res_str = (
                                f"[System: Context Overflow Protection]\n"
                                f"Output too large ({len(res_str)} chars) to fit in context.\n"
                                f"Content has been securely indexed to Ephemeral Store ID: {eph_id}\n"
                                f"You MUST use the tool 'query_ephemeral(ephemeral_id=\"{eph_id}\", query=\"...\")' "
                                f"to retrieve specific details/sections."
                            )
                            # Ensure we update the log buffer with the NEW res_str, not the old one.
                            # We need to pop the last entry or modify it, but we haven't appended yet.
                            # Ah, we append at line 426 (original code).
                            
                        else:
                            print(f"⚠️ Ephemeral Ingest Failed: {eph_id}")
                    except Exception as ex:
                        print(f"⚠️ Ephemeral Intercept Error: {ex}")

                # Prune output for ReAct history
                pruned_res = self.prune_output(res_str)
                
                # Create ToolMessage for history
                tool_messages.append(ToolMessage(
                    tool_call_id=call_id,
                    content=pruned_res,
                    name=tool_name
                ))
                
                # Truncate for display
                if len(res_str) > max_output_chars:
                    res_str = res_str[:max_output_chars] + "... [truncated]"
                
                results_text.append(f"Step {step.get('id')} ({tool_name}): {res_str}")
                tool_used = tool_name
                last_result = {
                    "tool": tool_name, 
                    "args": tool_args, 
                    "output": res_str, 
                    "success": not is_soft_failure
                }
                
                if state:
                    state.record_tool_result(success=not is_soft_failure)
                
                # V10: Stop after terminal actions (prevent multiple YouTube tabs)
                if tool_name in TERMINAL_ACTIONS:
                    print(f"⏹️ [Executor] Terminal action '{tool_name}' completed - stopping plan execution.")
                    break
                    
            except Exception as e:
                err_msg = f"Error: {e}"
                tool_messages.append(ToolMessage(
                    tool_call_id=call_id,
                    content=err_msg,
                    name=tool_name,
                    status="error"
                ))
                results_text.append(f"Step {step.get('id')} Error: {e}")
                last_result = {
                    "tool": tool_name, 
                    "args": tool_args, 
                    "output": str(e), 
                    "success": False
                }
                all_success = False
                
                if state:
                    state.record_tool_result(success=False)
        
        # Format outputs
        outputs = ""
        if results_text:
            outputs = "\n\n=== TOOL EXECUTION LOG ===\n" + "\n".join(results_text)
        
        return ExecutionResult(
            outputs=outputs,
            tool_messages=tool_messages,
            tool_used=tool_used,
            last_result=last_result,
            success=all_success
        )
    
    def prune_output(self, output: str, max_chars: int = 1000) -> str:
        """
        Smart pruner with summarization fallback.
        
        For large outputs, preserves structure while reducing size:
        - JSON: Prunes large keys, truncates arrays
        - Text: Word-boundary truncation
        - Very large: LLM summarization (if available)
        """
        if len(output) <= max_chars:
            return output
        
        # Try LLM summarization for very large outputs
        if len(output) > 2000 and self.summarizer_llm:
            try:
                summary = self._summarize_output(output)
                if summary:
                    return f"[SUMMARY of {len(output)} chars]\n{summary}"
            except Exception as e:
                print(f"⚠️ Summarization failed: {e}")
        
        # Try JSON-aware pruning
        stripped = output.strip()
        if self._looks_like_json(stripped):
            try:
                data = json.loads(output)
                pruned_data = self._prune_json(data)
                pruned_json = json.dumps(pruned_data, indent=2, ensure_ascii=False)
                
                if len(pruned_json) <= max_chars:
                    return pruned_json
                return json.dumps({"_truncated": True, "preview": str(data)[:500]})
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Text truncation at word boundary
        return self._truncate_text(output, max_chars)
    
    def _looks_like_json(self, text: str) -> bool:
        """Check if text looks like JSON."""
        return ((text.startswith('{') and text.endswith('}')) or
                (text.startswith('[') and text.endswith(']')))
    
    def _prune_json(self, obj, depth: int = 0) -> Any:
        """Recursively prune large values in JSON."""
        if depth > 5:
            return "[NESTED]"
        
        if isinstance(obj, dict):
            pruned = {}
            for k, v in obj.items():
                # Skip known large keys
                if k.lower() in ('html', 'html_body', 'raw_content', 'body', 'content'):
                    pruned[k] = f"[{len(str(v))} chars - use retrieve_document_context()]"
                else:
                    pruned[k] = self._prune_json(v, depth + 1)
            return pruned
        
        elif isinstance(obj, list):
            if len(obj) > 5:
                return [self._prune_json(obj[0], depth + 1), f"... [{len(obj) - 1} more items]"]
            return [self._prune_json(item, depth + 1) for item in obj]
        
        elif isinstance(obj, str) and len(obj) > 200:
            return obj[:200] + "..."
        
        return obj
    
    def _truncate_text(self, text: str, max_chars: int) -> str:
        """Truncate text at word/sentence boundary."""
        truncated = text[:max_chars]
        
        last_space = truncated.rfind(' ')
        last_newline = truncated.rfind('\n')
        cut_point = max(last_space, last_newline, max_chars - 100)
        
        if cut_point > 0:
            truncated = text[:cut_point]
        
        remaining = len(text) - len(truncated)
        return f"{truncated}\n... [TRUNCATED: {remaining} chars]"
    
    def _summarize_output(self, output: str) -> Optional[str]:
        """Use LLM to summarize large output."""
        if not self.summarizer_llm:
            return None
        
        from langchain_core.messages import SystemMessage, HumanMessage
        
        prompt = """Summarize this tool output in 2-3 sentences.
Focus on: key facts, numbers, names, and actionable information.
Do NOT add information not present in the output."""
        
        try:
            messages = [
                SystemMessage(content=prompt),
                HumanMessage(content=output[:4000])  # Cap context
            ]
            response = self.summarizer_llm.invoke(messages)
            return response.content
        except Exception:
            return None
