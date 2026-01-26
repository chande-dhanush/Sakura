"""
Sakura Tool Executor - Composable Architecture Refactor
========================================================

Core Responsibility: Execution orchestration via ReAct loop

Architecture:
    1. ReActLoop - Controls Plan → Act → Observe iteration
    2. ToolRunner - Runs individual tool calls with fallback
    3. OutputHandler - Prunes/summarizes large outputs
    4. ExecutionPolicy - Defines behavior rules (terminal actions, etc.)

V17: ExecutionResult moved to execution_context.py (uses ExecutionStatus enum)
"""

import os
import re
import json
import time
import asyncio
import unicodedata
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass

from langchain_core.messages import ToolMessage

# V17: Import ExecutionResult from execution_context (uses ExecutionStatus)
from .context import ExecutionResult, ExecutionStatus

if TYPE_CHECKING:
    from .context import ExecutionContext


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY LAYER
# ═══════════════════════════════════════════════════════════════════════════════

class SecurityError(Exception):
    """Raised when a security violation is detected."""
    pass


DANGEROUS_PATTERNS = [
    r"\.bashrc", r"\.zshrc", r"\.profile", r"\.bash_profile",
    r"autostart", r"LaunchAgent", r"LaunchDaemon",
    r"cron\.d", r"crontab", r"systemd", r"\.service$",
    r"\.ssh", r"\.aws", r"\.kube", r"\.docker",
    r"\.git-credentials", r"\.netrc", r"\.npmrc",
    r"/etc/", r"C:[/\\]Windows", r"System32",
    r"/usr/bin", r"/usr/local/bin",
    r"\.mozilla", r"\.chrome", r"AppData.*Local.*Google",
    r"\.config/", r"\.local/share",
]


def validate_path(path: str) -> bool:
    """Validate path for security. Raises SecurityError if dangerous."""
    normalized = unicodedata.normalize('NFC', path)
    nfkd = unicodedata.normalize('NFKD', path)
    
    if nfkd != normalized.encode('ascii', 'ignore').decode('ascii'):
        print(f"️ [Security] Potential homoglyph in path: {path}")
    
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            raise SecurityError(f"Blocked dangerous path pattern: {pattern}")
    
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTION POLICY (Behavior Rules)
# ═══════════════════════════════════════════════════════════════════════════════

class ExecutionPolicy:
    """
    Defines behavior rules for tool execution.
    
    No logic - just data and predicates.
    """
    
    # Tools that complete a request (don't need follow-up)
    TERMINAL_ACTIONS = {
        "play_youtube", "spotify_control", "open_app", "open_site",
        "file_open", "gmail_send_email", "calendar_create_event",
        "tasks_create", "note_create", "set_timer", "set_reminder"
    }
    
    # Fallback chain for soft failures
    FALLBACK_MAP = {
        "spotify_control": "play_youtube",
        "play_youtube": "web_search",
    }
    
    # Indicators that a tool "ran" but didn't complete successfully
    FAILURE_INDICATORS = [
        "not found", "failed", "error", "couldn't", "unable"
    ]
    
    @staticmethod
    def is_terminal(tool_name: str) -> bool:
        """Check if tool is a terminal action."""
        return tool_name in ExecutionPolicy.TERMINAL_ACTIONS
    
    @staticmethod
    def get_fallback(tool_name: str) -> Optional[str]:
        """Get fallback tool for a given tool."""
        return ExecutionPolicy.FALLBACK_MAP.get(tool_name)
    
    @staticmethod
    def is_soft_failure(output: str) -> bool:
        """Detect if output indicates a soft failure."""
        output_lower = output.lower()
        return any(ind in output_lower for ind in ExecutionPolicy.FAILURE_INDICATORS)


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT HANDLER (Pruning & Summarization)
# ═══════════════════════════════════════════════════════════════════════════════

class OutputHandler:
    """
    Handles output pruning, summarization, and ephemeral interception.
    
    Single Responsibility: Transform large/complex outputs into manageable forms.
    """
    
    def __init__(self, summarizer_llm=None, ephemeral_manager=None):
        self.summarizer_llm = summarizer_llm
        self.ephemeral_manager = ephemeral_manager
    
    def intercept_large_output(self, output: str, tool_name: str, threshold: int = 2000) -> str:
        """
        Intercept outputs larger than threshold and store in ephemeral context.
        
        Returns: Either the original output or a reference to ephemeral storage.
        """
        if len(output) <= threshold or not self.ephemeral_manager:
            return output
        
        print(f"️ [OutputHandler] Intercepting large output ({len(output)} chars)")
        
        try:
            eph_id = self.ephemeral_manager.ingest_text(output, source_tool=tool_name)
            
            if eph_id and not eph_id.startswith("error"):
                return (
                    f"[System: Context Overflow Protection]\n"
                    f"Output too large ({len(output)} chars) to fit in context.\n"
                    f"Content has been securely indexed to Ephemeral Store ID: {eph_id}\n"
                    f"You MUST use the tool 'query_ephemeral(ephemeral_id=\"{eph_id}\", query=\"...\")' "
                    f"to retrieve specific details/sections."
                )
            else:
                print(f"⚠️ Ephemeral ingest failed: {eph_id}")
                return output
                
        except Exception as e:
            print(f"⚠️ Ephemeral intercept error: {e}")
            return output
    
    def prune(self, output: str, max_chars: int = 1000) -> str:
        """
        Smart pruner with summarization fallback.
        
        Strategy:
        1. If small enough, return as-is
        2. If very large + LLM available, summarize
        3. If JSON, prune structure-aware
        4. Otherwise, truncate at word boundary
        """
        if len(output) <= max_chars:
            return output
        
        # Try LLM summarization for very large outputs
        if len(output) > 2000 and self.summarizer_llm:
            summary = self._summarize(output)
            if summary:
                return f"[SUMMARY of {len(output)} chars]\n{summary}"
        
        # JSON-aware pruning
        if self._looks_like_json(output):
            try:
                data = json.loads(output)
                pruned_data = self._prune_json(data)
                pruned_json = json.dumps(pruned_data, indent=2, ensure_ascii=False)
                
                if len(pruned_json) <= max_chars:
                    return pruned_json
                return json.dumps({"_truncated": True, "preview": str(data)[:500]})
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Text truncation
        return self._truncate_text(output, max_chars)
    
    def _looks_like_json(self, text: str) -> bool:
        """Check if text looks like JSON."""
        stripped = text.strip()
        return ((stripped.startswith('{') and stripped.endswith('}')) or
                (stripped.startswith('[') and stripped.endswith(']')))
    
    def _prune_json(self, obj: Any, depth: int = 0) -> Any:
        """Recursively prune large values in JSON."""
        if depth > 5:
            return "[NESTED]"
        
        if isinstance(obj, dict):
            pruned = {}
            for k, v in obj.items():
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
    
    def _summarize(self, output: str) -> Optional[str]:
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
                HumanMessage(content=output[:4000])
            ]
            response = self.summarizer_llm.invoke(messages)
            return response.content
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL RUNNER (Single Tool Execution)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ToolRunResult:
    """Result of a single tool execution."""
    output: str
    success: bool
    tool_name: str  # May differ from requested (due to fallback)
    original_tool: str


class ToolRunner:
    """
    Executes individual tool calls with fallback recovery.
    
    Single Responsibility: Run one tool, handle failures, return result.
    """
    
    def __init__(self, tool_map: Dict[str, Any], policy: ExecutionPolicy):
        self.tool_map = tool_map
        self.policy = policy
    
    def run(self, tool_name: str, args: Dict[str, Any], user_input: str = "") -> ToolRunResult:
        """Execute a tool synchronously with fallback recovery."""
        if tool_name not in self.tool_map:
            return ToolRunResult(
                output=f"Error: Tool '{tool_name}' not found.",
                success=False,
                tool_name=tool_name,
                original_tool=tool_name
            )
        
        try:
            result = self.tool_map[tool_name].invoke(args)
            result_str = str(result)
            
            # Check for soft failure
            if self.policy.is_soft_failure(result_str):
                fallback_result = self._try_fallback(tool_name, args, user_input)
                if fallback_result:
                    return fallback_result
            
            return ToolRunResult(
                output=result_str,
                success=True,
                tool_name=tool_name,
                original_tool=tool_name
            )
            
        except Exception as e:
            import traceback
            print(f" TOOL EXECUTION ERROR ")
            print(f"   Tool: {tool_name}")
            print(f"   Args: {args}")
            print(f"   Error: {e}")
            traceback.print_exc()
            
            return ToolRunResult(
                output=f"Error: {e}",
                success=False,
                tool_name=tool_name,
                original_tool=tool_name
            )
    
    async def arun(self, tool_name: str, args: Dict[str, Any], user_input: str = "") -> ToolRunResult:
        """Execute a tool asynchronously with fallback recovery."""
        if tool_name not in self.tool_map:
            return ToolRunResult(
                output=f"Error: Tool '{tool_name}' not found.",
                success=False,
                tool_name=tool_name,
                original_tool=tool_name
            )
        
        try:
            tool_instance = self.tool_map[tool_name]
            
            # Use ainvoke if available, otherwise run sync in thread
            if hasattr(tool_instance, 'ainvoke'):
                result = await tool_instance.ainvoke(args)
            else:
                result = await asyncio.to_thread(tool_instance.invoke, args)
            
            result_str = str(result)
            
            # Check for soft failure
            if self.policy.is_soft_failure(result_str):
                fallback_result = await self._atry_fallback(tool_name, args, user_input)
                if fallback_result:
                    return fallback_result
            
            return ToolRunResult(
                output=result_str,
                success=True,
                tool_name=tool_name,
                original_tool=tool_name
            )
            
        except Exception as e:
            import traceback
            print(f" ASYNC TOOL EXECUTION ERROR ")
            print(f"   Tool: {tool_name}")
            print(f"   Args: {args}")
            print(f"   Error: {e}")
            traceback.print_exc()
            
            return ToolRunResult(
                output=f"Error: {e}",
                success=False,
                tool_name=tool_name,
                original_tool=tool_name
            )
    
    def _try_fallback(self, tool_name: str, args: Dict, user_input: str) -> Optional[ToolRunResult]:
        """Attempt fallback tool on soft failure."""
        fallback_tool = self.policy.get_fallback(tool_name)
        
        if not fallback_tool or fallback_tool not in self.tool_map:
            return None
        
        search_term = self._extract_search_term(tool_name, args, user_input)
        if not search_term:
            return None
        
        print(f" [Recovery] {tool_name} → {fallback_tool} ('{search_term}')")
        
        fallback_args = self._build_fallback_args(fallback_tool, search_term)
        
        try:
            result = self.tool_map[fallback_tool].invoke(fallback_args)
            return ToolRunResult(
                output=f"[Fallback: {fallback_tool}] {result}",
                success=True,
                tool_name=fallback_tool,
                original_tool=tool_name
            )
        except Exception as e:
            print(f"⚠️ Fallback also failed: {e}")
            return None
    
    async def _atry_fallback(self, tool_name: str, args: Dict, user_input: str) -> Optional[ToolRunResult]:
        """Async version of fallback."""
        fallback_tool = self.policy.get_fallback(tool_name)
        
        if not fallback_tool or fallback_tool not in self.tool_map:
            return None
        
        search_term = self._extract_search_term(tool_name, args, user_input)
        if not search_term:
            return None
        
        print(f" [Async Recovery] {tool_name} → {fallback_tool} ('{search_term}')")
        
        fallback_args = self._build_fallback_args(fallback_tool, search_term)
        
        try:
            result = await asyncio.to_thread(self.tool_map[fallback_tool].invoke, fallback_args)
            return ToolRunResult(
                output=f"[Fallback: {fallback_tool}] {result}",
                success=True,
                tool_name=fallback_tool,
                original_tool=tool_name
            )
        except Exception as e:
            print(f"⚠️ Async fallback also failed: {e}")
            return None
    
    def _extract_search_term(self, tool_name: str, args: Dict, user_input: str) -> str:
        """Extract human-readable search term from tool args."""
        search_keys = ["query", "topic", "song", "track", "search_term", "q"]
        
        for key in search_keys:
            if key in args and args[key]:
                return str(args[key])
        
        if tool_name == "spotify_control" and args.get("action") == "play":
            if args.get("track_name"):
                return args["track_name"]
            if args.get("query"):
                return args["query"]
        
        if user_input:
            return user_input
        
        for key, val in args.items():
            if key not in ["action", "uri"] and val:
                return str(val)
        
        return ""
    
    def _build_fallback_args(self, fallback_tool: str, search_term: str) -> Dict:
        """Build arguments for fallback tool."""
        if fallback_tool == "play_youtube":
            return {"topic": search_term}
        elif fallback_tool == "web_search":
            return {"query": search_term}
        else:
            return {"query": search_term}


# ═══════════════════════════════════════════════════════════════════════════════
# REACT LOOP (Iteration Controller)
# ═══════════════════════════════════════════════════════════════════════════════

class ReActLoop:
    """
    Controls Plan → Act → Observe iteration.
    
    Single Responsibility: Orchestrate the loop, not the details.
    """
    
    def __init__(
        self,
        planner,
        tool_runner: ToolRunner,
        output_handler: OutputHandler,
        policy: ExecutionPolicy,
        max_iterations: int = 3
    ):
        self.planner = planner
        self.tool_runner = tool_runner
        self.output_handler = output_handler
        self.policy = policy
        self.max_iterations = max_iterations
    
    def run(
        self,
        user_input: str,
        graph_context: str,
        available_tools: List,
        state=None
    ) -> ExecutionResult:
        """Run the ReAct loop synchronously."""
        all_tool_messages = []
        all_outputs = []
        final_tool_used = "None"
        final_last_result = None
        
        print(f" [ReActLoop] Starting for: {user_input[:50]}...")
        
        for iteration in range(self.max_iterations):
            print(f" [ReActLoop] Iteration {iteration + 1}/{self.max_iterations}")
            
            # 1. PLAN
            plan_result = self.planner.plan(
                user_input=user_input,
                context=graph_context,
                tool_history=all_tool_messages,
                available_tools=available_tools
            )
            
            steps = plan_result.get("steps", []) or plan_result.get("plan", [])
            
            if not steps:
                print("⏹️ [ReActLoop] No more steps - complete")
                break
            
            # 2. ACT
            exec_result = self._execute_steps(steps, user_input, state)
            
            # 3. OBSERVE
            all_tool_messages.extend(exec_result.tool_messages)
            if exec_result.outputs:
                all_outputs.append(exec_result.outputs)
            
            final_tool_used = exec_result.tool_used
            final_last_result = exec_result.last_result
            
            # Terminal actions should end the loop
            if self.policy.is_terminal(final_tool_used) and exec_result.success:
                print(f" [ReActLoop] Terminal action '{final_tool_used}' completed")
                break  # V17.1: RESTORED terminal break
        
        return ExecutionResult(
            outputs="\n".join(all_outputs),
            tool_messages=all_tool_messages,
            tool_used=final_tool_used,
            last_result=final_last_result,
            status=ExecutionStatus.SUCCESS
        )
    
    async def arun(
        self,
        ctx: "ExecutionContext" = None,  # V17: NEW - ExecutionContext with budget
        user_input: str = None,  # Legacy fallback
        graph_context: str = None,  # Legacy fallback
        available_tools: List = None,
        state=None
    ) -> ExecutionResult:
        """
        Run the ReAct loop asynchronously.
        
        V17: Now accepts ExecutionContext for budget enforcement.
        Legacy signature still supported for backward compat.
        """
        # V17: Extract from ExecutionContext if provided
        if ctx:
            user_input = ctx.user_input
            available_tools = available_tools or []
            # TODO: Get graph_context from ctx.snapshot when ReferenceResolver updated
        
        all_tool_messages = []
        all_outputs = []
        final_tool_used = "None"
        final_last_result = None
        
        print(f" [ReActLoop] Starting async for: {user_input[:50]}...")
        
        for iteration in range(self.max_iterations):
            # V17: CHECK BUDGET BEFORE EACH ITERATION
            if ctx and ctx.is_expired():
                print(f"⏱️ [ReActLoop] Budget exceeded ({ctx.elapsed_ms():.0f}ms / {ctx.budget_ms}ms)")
                # Return partial results
                return ExecutionResult.timeout(
                    outputs="\n".join(all_outputs) if all_outputs else "",
                    tool_messages=all_tool_messages
                )
            
            print(f" [ReActLoop] Async iteration {iteration + 1}/{self.max_iterations}")
            
            # 1. PLAN (with timeout if we have budget)
            try:
                if ctx and ctx.remaining_budget_ms() > 0:
                    # Use asyncio.wait_for with remaining budget
                    timeout_secs = min(ctx.remaining_budget_ms() / 1000, 10.0)  # Max 10s per iteration
                    plan_result = await asyncio.wait_for(
                        self.planner.aplan(
                            user_input=user_input,
                            context=graph_context or "",
                            tool_history=all_tool_messages,
                            available_tools=available_tools
                        ),
                        timeout=timeout_secs
                    )
                else:
                    # No budget context, run without timeout (legacy path)
                    plan_result = await self.planner.aplan(
                        user_input=user_input,
                        context=graph_context or "",
                        tool_history=all_tool_messages,
                        available_tools=available_tools
                    )
            
            except asyncio.TimeoutError:
                print(f"⏱️ [ReActLoop] Planner timeout at iteration {iteration + 1}")
                return ExecutionResult.timeout(
                    outputs="\n".join(all_outputs) if all_outputs else "",
                    tool_messages=all_tool_messages
                )
            
            steps = plan_result.get("steps", []) or plan_result.get("plan", [])
            
            if not steps:
                print("⏹️ [ReActLoop] No more steps - complete")
                break
            
            # 2. ACT
            exec_result = await self._aexecute_steps(steps, user_input, state)
            
            # 3. OBSERVE
            all_tool_messages.extend(exec_result.tool_messages)
            if exec_result.outputs:
                all_outputs.append(exec_result.outputs)
            
            final_tool_used = exec_result.tool_used
            final_last_result = exec_result.last_result
            
            # Terminal actions should end the loop
            if self.policy.is_terminal(final_tool_used) and exec_result.succeeded:
                print(f" [ReActLoop] Async terminal action '{final_tool_used}' completed")
                break  # V17.1: RESTORED terminal break
        
        return ExecutionResult(
            outputs="\n".join(all_outputs),
            tool_messages=all_tool_messages,
            tool_used=final_tool_used,
            last_result=final_last_result,
            status=ExecutionStatus.SUCCESS
        )
    
    def _execute_steps(
        self,
        steps: List[Dict],
        user_input: str,
        state
    ) -> ExecutionResult:
        """Execute a list of steps synchronously."""
        results_text = []
        tool_messages = []
        tool_used = "None"
        last_result = None
        all_succeeded = True
        any_succeeded = False
        
        for step in steps[:self.max_iterations]:  # Cap steps
            tool_name = step.get("tool")
            tool_args = step.get("args", {})
            call_id = step.get("tool_call_id", f"call_{step.get('id', 0)}")
            
            print(f"▶️ Executing Step {step.get('id')}: {tool_name} {tool_args}")
            
            # Run tool
            run_result = self.tool_runner.run(tool_name, tool_args, user_input)
            
            if run_result.success:
                any_succeeded = True
            else:
                all_succeeded = False

            # Process output
            intercepted_output = self.output_handler.intercept_large_output(
                run_result.output,
                run_result.tool_name
            )
            pruned_output = self.output_handler.prune(intercepted_output)
            
            # Create ToolMessage
            tool_messages.append(ToolMessage(
                tool_call_id=call_id,
                content=pruned_output,
                name=run_result.tool_name,
                status="error" if not run_result.success else "success"
            ))
            
            # Truncate for display
            display_output = intercepted_output
            if len(display_output) > 2000:
                display_output = display_output[:2000] + "... [truncated]"
            
            results_text.append(f"Step {step.get('id')} ({run_result.tool_name}): {display_output}")
            
            tool_used = run_result.tool_name
            last_result = {
                "tool": run_result.tool_name,
                "args": tool_args,
                "output": intercepted_output,
                "success": run_result.success
            }
            
            if state:
                state.record_tool_result(success=run_result.success)
            
            if self.policy.is_terminal(run_result.tool_name):
                print(f" [Executor] Terminal action '{run_result.tool_name}' completed")
        
        outputs = ""
        if results_text:
            outputs = "\n\n=== TOOL EXECUTION LOG ===\n" + "\n".join(results_text)
        
        # Determine final status
        if all_succeeded:
            status = ExecutionStatus.SUCCESS
        elif any_succeeded:
            status = ExecutionStatus.PARTIAL
        else:
            status = ExecutionStatus.FAILED
            
        return ExecutionResult(
            outputs=outputs,
            tool_messages=tool_messages,
            tool_used=tool_used,
            last_result=last_result,
            status=status
        )
    
    async def _aexecute_steps(
        self,
        steps: List[Dict],
        user_input: str,
        state
    ) -> ExecutionResult:
        """Execute a list of steps asynchronously."""
        results_text = []
        tool_messages = []
        tool_used = "None"
        last_result = None
        all_succeeded = True
        any_succeeded = False
        
        for step in steps[:self.max_iterations]:
            tool_name = step.get("tool")
            tool_args = step.get("args", {})
            call_id = step.get("tool_call_id", f"call_{step.get('id', 0)}")
            
            print(f"▶️ Async Executing Step {step.get('id')}: {tool_name} {tool_args}")
            
            # Pacing between steps
            if step.get('id', 0) > 1:
                try:
                    from ..infrastructure.broadcaster import broadcast
                    broadcast("pacing", {"step": step.get('id'), "tool": tool_name})
                except ImportError:
                    pass
                await asyncio.sleep(0.5)
            
            # Broadcast tool start
            try:
                from ..infrastructure.broadcaster import broadcast
                broadcast("tool_start", {"tool": tool_name, "args": tool_args})
            except ImportError:
                pass
            
            # Run tool
            run_result = await self.tool_runner.arun(tool_name, tool_args, user_input)
            
            if run_result.success:
                any_succeeded = True
            else:
                all_succeeded = False

            # Process output
            intercepted_output = self.output_handler.intercept_large_output(
                run_result.output,
                run_result.tool_name
            )
            pruned_output = self.output_handler.prune(intercepted_output)
            
            # Create ToolMessage
            tool_messages.append(ToolMessage(
                tool_call_id=call_id,
                content=pruned_output,
                name=run_result.tool_name,
                status="error" if not run_result.success else "success"
            ))
            
            # Truncate for display
            display_output = intercepted_output
            if len(display_output) > 2000:
                display_output = display_output[:2000] + "... [truncated]"
            
            results_text.append(f"Step {step.get('id')} ({run_result.tool_name}): {display_output}")
            
            tool_used = run_result.tool_name
            last_result = {
                "tool": run_result.tool_name,
                "args": tool_args,
                "output": intercepted_output,
                "success": run_result.success
            }
            
            if state:
                state.record_tool_result(success=run_result.success)
            
            if self.policy.is_terminal(run_result.tool_name):
                print(f" [Async Executor] Terminal action '{run_result.tool_name}' completed")
        
        outputs = ""
        if results_text:
            outputs = "\n\n=== TOOL EXECUTION LOG ===\n" + "\n".join(results_text)
        
        # Determine final status
        if all_succeeded:
            status = ExecutionStatus.SUCCESS
        elif any_succeeded:
            status = ExecutionStatus.PARTIAL
        else:
            status = ExecutionStatus.FAILED
            
        return ExecutionResult(
            outputs=outputs,
            tool_messages=tool_messages,
            tool_used=tool_used,
            last_result=last_result,
            status=status
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL EXECUTOR (Facade)
# ═══════════════════════════════════════════════════════════════════════════════

class ToolExecutor:
    """
    Facade that wires together all execution components.
    
    Exposes simple interface:
        - execute() - sync
        - aexecute() - async
    
    Contains almost no logic itself - just composition.
    """
    
    def __init__(self, tools: List, summarizer_llm=None):
        """
        Args:
            tools: List of LangChain tools
            summarizer_llm: Optional LLM for summarizing large outputs
        """
        # Build tool map
        self.tools = tools
        self.tool_map = {t.name: t for t in tools}
        
        # Initialize components
        self.policy = ExecutionPolicy()
        self.tool_runner = ToolRunner(self.tool_map, self.policy)
        
        # Get ephemeral manager if available
        try:
            from ..graph.ephemeral import get_ephemeral_manager
            ephemeral_manager = get_ephemeral_manager()
        except ImportError:
            ephemeral_manager = None
        
        self.output_handler = OutputHandler(summarizer_llm, ephemeral_manager)
        
        # Initialize planner
        if summarizer_llm:
            from .planner import Planner
            self.planner = Planner(summarizer_llm)
        else:
            self.planner = None
        
        # Initialize ReAct loop
        if self.planner:
            self.react_loop = ReActLoop(
                self.planner,
                self.tool_runner,
                self.output_handler,
                self.policy
            )
        else:
            self.react_loop = None

    def execute(self, user_input: str, route_result: Any, graph_context: str, state: Any = None) -> ExecutionResult:
        """
        Main execution entry point. Delegating to ReActLoop.
        """
        if not self.react_loop:
            return ExecutionResult("Error: No planner configured", [], "Error", None, ExecutionStatus.FAILED)
            
        return self.react_loop.run(
            user_input=user_input,
            graph_context=graph_context,
            available_tools=self.tools,
            state=state
        )

    async def aexecute(self, user_input: str, route_result: Any, graph_context: str, state: Any = None) -> ExecutionResult:
        """
        Async version of execute. Delegating to ReActLoop.
        """
        if not self.react_loop:
            return ExecutionResult("Error: No planner configured", [], "Error", None, ExecutionStatus.FAILED)
            
        return await self.react_loop.arun(
            user_input=user_input,
            graph_context=graph_context,
            available_tools=self.tools,
            state=state
        )
