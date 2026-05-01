"""
Sakura Tool Executor - V19.5 Hardened
======================================
"""

import os
import re
import json
import time
import asyncio
import hashlib
import warnings
import psutil
import unicodedata
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass

from langchain_core.messages import ToolMessage
from ...config import PLANNER_RETRY_PROMPT

# V17: Import ExecutionResult from execution_context (uses ExecutionStatus)
from .context import ExecutionResult, ExecutionStatus, is_cancelled
from ...utils.flight_recorder import get_recorder


def _get_int_env(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < min_value or value > max_value:
        return default
    return value

if TYPE_CHECKING:
    from .context import ExecutionContext


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY LAYER
# ═══════════════════════════════════════════════════════════════════════════════

class SecurityError(Exception):
    """Raised when a security policy is violated."""
    pass


DANGEROUS_PATTERNS = [
    r"\.\.", r"/etc/", r"\\windows\\", r"c:\\windows", r"program files",
    r"\.ssh", r"\.bashrc", r"autostart", r"cron", r"passwd",
    r"\.zshrc", r"\.profile", r"\.bash_profile",
    r"LaunchAgent", r"LaunchDaemon",
    r"cron\.d", r"crontab", r"systemd", r"\.service$",
    r"\.aws", r"\.kube", r"\.docker",
    r"\.git-credentials", r"\.netrc", r"\.npmrc",
    r"System32", r"/usr/bin", r"/usr/local/bin",
    r"\.mozilla", r"\.chrome", r"AppData.*Local.*Google",
    r"\.config/", r"\.local/share",
]

def _sanitize_path(path: str) -> str:
    """
    V19.5 Security Sandbox.
    Prevents path traversal and normalizes unicode.
    """
    # 1. Normalize Unicode (NFC) to prevent homograph attacks
    path = unicodedata.normalize('NFC', path)
    
    # 2. Block dangerous patterns
    import re
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            print(f"⚠️ [Security] Blocked path traversal attempt: {path}")
            raise SecurityError(f"Blocked dangerous path: {path[:50]}")
            
    # 3. Secure normalization
    safe_path = os.path.normpath(os.path.abspath(path))
    return safe_path


def validate_path(path: str) -> str:
    """Legacy alias for _sanitize_path."""
    return _sanitize_path(path)


def _validate_tool_input(tool_name: str, args: Dict[str, Any]) -> bool:
    """
    V19.5 Hallucination Gateway.
    Blocks malformed tool inputs before execution.
    """
    # 1. Block URLs in arguments that expect local paths or simple strings
    for key, val in args.items():
        if isinstance(val, str) and (val.startswith("http://") or val.startswith("https://")):
            # Exempt web tools
            if tool_name not in ["web_search", "web_scrape", "play_youtube", "open_site", "search_wikipedia", "search_arxiv"]:
                raise SecurityError(f"Hallucination detected: URL provided as argument to {tool_name}")
    
    # 2. Block missing critical arguments (V19.5 Audit)
    if tool_name in ["file_read", "file_write", "open_app"] and not args.get("path") and not args.get("app_name") and not args.get("filename"):
        raise SecurityError(f"Missing critical argument for {tool_name}")
        
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
        "clipboard_read", "clipboard_write", "read_clipboard", "write_clipboard",
        "tasks_create", "note_create", "set_timer", "set_reminder"
    }
    
    # Tools whose output content should NOT trigger soft-failure recovery
    SOFT_FAILURE_EXEMPTIONS = {"read_screen", "execute_python", "web_scrape", "web_search"}
    
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
    def is_soft_failure(output: str, tool_name: str = None) -> bool:
        """Detect if output indicates a soft failure."""
        if tool_name in ExecutionPolicy.SOFT_FAILURE_EXEMPTIONS:
            return False
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
            # V19.5: Hallucination Gateway
            _validate_tool_input(tool_name, args)
            
            # V15.2.2: Path Traversal Defense
            if tool_name in ["file_read", "file_write", "open_app"]:
                path_key = "path" if "path" in args else ("app_name" if "app_name" in args else "filename")
                if path_key in args:
                    args[path_key] = _sanitize_path(args[path_key])
            
            result = self.tool_map[tool_name].invoke(args)
            result_str = str(result)
            
            # Check for soft failure
            if self.policy.is_soft_failure(result_str, tool_name):
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
            # V19.5: Hallucination Gateway
            _validate_tool_input(tool_name, args)
            
            # V15.2.2: Path Traversal Defense
            if tool_name in ["file_read", "file_write", "open_app"]:
                path_key = "path" if "path" in args else ("app_name" if "app_name" in args else "filename")
                if path_key in args:
                    args[path_key] = _sanitize_path(args[path_key])
            
            tool_instance = self.tool_map[tool_name]
            
            # Use ainvoke if available, otherwise run sync in thread
            if hasattr(tool_instance, 'ainvoke'):
                result = await tool_instance.ainvoke(args)
            else:
                result = await asyncio.to_thread(tool_instance.invoke, args)
            
            result_str = str(result)
            
            # Check for soft failure
            if self.policy.is_soft_failure(result_str, tool_name):
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


def _is_empty_or_failed(output: str) -> bool:
    """Returns True if a tool output indicates no useful result was found."""
    if not output or not output.strip():
        return True
    failure_phrases = [
        "no results", "not found", "no article", "disambiguation",
        "may refer to", "does not exist", "could not find",
        "no information", "no matches", "0 results",
    ]
    output_lower = output.lower()
    return any(phrase in output_lower for phrase in failure_phrases)


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
        max_iterations: int = 5
    ):
        self.planner = planner
        self.tool_runner = tool_runner
        self.output_handler = output_handler
        self.policy = policy
        self.max_iterations = _get_int_env("MAX_PLANNER_ITERATIONS", max_iterations, 1, 8)
    
    def run(
        self,
        user_input: str,
        graph_context: str,
        available_tools: List,
        # V17.1: Pass tool_hint for Planner optimization
        tool_hint: Optional[str] = None
    ) -> ExecutionResult:
        """Run the ReAct loop synchronously."""
        all_tool_messages = []
        all_outputs = []
        final_tool_used = "None"
        final_last_result = None
        cascade_activated = False  # V18 FIX-04 SYNC
        
        print(f" [ReActLoop] Starting for: {user_input[:50]}...")
        
        for iteration in range(self.max_iterations):
            print(f" [ReActLoop] Iteration {iteration + 1}/{self.max_iterations}")
            
            # 1. PLAN
            plan_result = self.planner.plan(
                user_input=user_input,
                context=graph_context,
                tool_history=all_tool_messages,
                available_tools=available_tools,
                history=None, # Legacy sync path
                tool_hint=tool_hint
            )
            
            steps = plan_result.get("steps", []) or plan_result.get("plan", [])
            
            if not steps:
                # V18 BUG-07: If no steps in first iteration, it's a planning failure
                if iteration == 0:
                    status_msg = "Planning failed: No tools selected for action request"
                    print(f"❌ [ReActLoop] {status_msg}")
                    res = ExecutionResult.error(status_msg)
                    return res
                
                error = plan_result.get("error")
                if error:
                    print(f"❌ [ReActLoop] Planner error: {error}")
                    res = ExecutionResult.error(f"Planning failed: {error}")
                    return res
                print("⏹️ [ReActLoop] No more steps - complete")
                break
            
            # 2. ACT
            exec_result = self._execute_steps(steps, user_input, None)
            
            # 3. OBSERVE
            all_tool_messages.extend(exec_result.tool_messages)
            if exec_result.outputs:
                all_outputs.append(exec_result.outputs)
            
            final_tool_used = exec_result.tool_used
            final_last_result = exec_result.last_result
            
            # V18 FIX-04 SYNC: Search Cascade Activation
            TIER_1_SEARCH_TOOLS = {"search_wikipedia", "search_arxiv"}
            if (
                final_tool_used in TIER_1_SEARCH_TOOLS
                and not cascade_activated
                and _is_empty_or_failed(exec_result.outputs)
            ):
                from ..routing.micro_toolsets import get_micro_toolset, detect_semantic_intent
                intent, hint = detect_semantic_intent(user_input)
                all_tools_list = list(self.tool_runner.tool_map.values())
                expanded = get_micro_toolset(
                    intent, all_tools_list, tool_hint=hint, fallback_mode=True
                )
                available_tools = expanded if expanded else all_tools_list
                cascade_activated = True
                print(f"🔄 [Cascade SYNC] Tier-1 empty/failed → expanded to {len(available_tools)} tools")
            
            # Terminal actions should end the loop
            if self.policy.is_terminal(final_tool_used) and exec_result.status == ExecutionStatus.SUCCESS:
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
        ctx: "ExecutionContext" = None,
        user_input: str = None,
        graph_context: str = None,
        available_tools: List = None,
        state=None,
        tool_hint: Optional[str] = None,
        llm_overrides: Optional[Dict[str, Any]] = None,
        timeout: int = 60 # Added for audit compliance
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
            
            # FIX-7: Populate graph_context from context snapshot
            graph_context_parts = []
            
            if ctx.reference_context:
                graph_context_parts.append(ctx.reference_context)
                
            if ctx.snapshot:
                actions = ctx.snapshot.recent_actions
                action_lines = [f"  - {a['tool']}({a['args']}) -> {a['summary']}" for a in actions]
                graph_context_parts.append(f"[SYSTEM CONTEXT]\nRecent Actions:\n" + "\n".join(action_lines))
                graph_context_parts.append(f"User Strategy: Focus on {ctx.snapshot.user_identity.get('name', 'User')}")
                
            graph_context = "\n\n".join(graph_context_parts)
        
        all_tool_messages = []
        all_outputs = []
        final_last_result = None
        final_tool_used = "None"
        cascade_activated = False  # V18 FIX-04
        prev_hindsight = None # FIX-4
        executed_tools = []   # BUG-02
        
        print(f" [ReActLoop] Starting async for: {user_input[:50]}...")
        
        for iteration in range(self.max_iterations):
            # V19: CHECK CANCELLATION before each iteration
            if is_cancelled():
                print(f"🛑 [ReActLoop] Generation cancelled by user at iteration {iteration + 1}")
                return ExecutionResult.cancelled(
                    outputs="\n".join(all_outputs) if all_outputs else "",
                    tool_messages=all_tool_messages
                )
            
            # V17: CHECK BUDGET & LLM CALL LIMIT BEFORE EACH ITERATION
            if ctx:
                if ctx.is_expired():
                    print(f"⏱️ [ReActLoop] Budget exceeded ({ctx.elapsed_ms():.0f}ms / {ctx.budget_ms}ms)")
                    return ExecutionResult.timeout(
                        outputs="\n".join(all_outputs) if all_outputs else "",
                        tool_messages=all_tool_messages
                    )
                
                # V18 FIX-08: Check LLM call limit (Plan + optional Verify)
                # We check BEFORE we make the next planner call
                if ctx.llm_call_count >= ctx.max_llm_calls:
                    print(f"🛑 [ReActLoop] LLM call limit ({ctx.max_llm_calls}) reached at iteration {iteration + 1}")
                    return ExecutionResult.timeout(
                        outputs="\n".join(all_outputs) if all_outputs else "",
                        tool_messages=all_tool_messages
                    )
            
            print(f" [ReActLoop] Async iteration {iteration + 1}/{self.max_iterations}")
            
            # 1. PLAN (with timeout if we have budget)
            try:
                # V18: Record planner call in context and check limit
                if ctx and not ctx.record_and_check_llm_call():
                    print(f"🛑 [ReActLoop] LLM call limit ({ctx.max_llm_calls}) reached during iteration {iteration + 1}")
                    return ExecutionResult.timeout(
                        outputs="\n".join(all_outputs) if all_outputs else "",
                        tool_messages=all_tool_messages
                    )
                
                # V19: Resolve planner LLM with overrides
                from ..infrastructure import get_container
                planner_llm = get_container().get_planner_llm(overrides=llm_overrides) if llm_overrides else self.planner.llm

                if ctx and ctx.remaining_budget_ms() > 0:
                    # Use asyncio.wait_for with remaining budget
                    step_timeout_ms = _get_int_env("PLANNER_STEP_TIMEOUT_MS", 10000, 1000, 60000)
                    timeout_secs = min(ctx.remaining_budget_ms() / 1000, step_timeout_ms / 1000.0)
                    plan_result = await asyncio.wait_for(
                        self.planner.aplan(
                            user_input=user_input,
                            context=graph_context or "",
                            tool_history=all_tool_messages,
                            available_tools=available_tools,
                            history=ctx.history, # V17.1
                            hindsight=prev_hindsight,  # FIX-4
                            executed_tools=executed_tools, # BUG-02
                            tool_hint=tool_hint, # VERIFICATION-03
                            llm_override=planner_llm if llm_overrides else None
                        ),
                        timeout=timeout_secs
                    )
                else:
                    # No budget context, run without timeout (legacy path)
                    plan_result = await self.planner.aplan(
                        user_input=user_input,
                        context=graph_context or "",
                        tool_history=all_tool_messages,
                        available_tools=available_tools,
                        history=ctx.history if ctx else None, # V17.1
                        hindsight=prev_hindsight,  # FIX-4
                        executed_tools=executed_tools, # BUG-02
                        tool_hint=tool_hint, # VERIFICATION-03
                        llm_override=planner_llm if llm_overrides else None
                    )
            
            except asyncio.TimeoutError:
                print(f"⏱️ [ReActLoop] Planner timeout at iteration {iteration + 1}")
                return ExecutionResult.timeout(
                    outputs="\n".join(all_outputs) if all_outputs else "",
                    tool_messages=all_tool_messages
                )
            
            steps = plan_result.get("steps", []) or plan_result.get("plan", [])
            
            if not steps:
                # V18 BUG-07: If no steps in first iteration, it's a planning failure
                if iteration == 0:
                    status_msg = "Planning failed: No tools selected for action request (async)"
                    print(f"❌ [ReActLoop] {status_msg}")
                    res = ExecutionResult.error(status_msg)
                    if ctx: res.last_result = {"mode": ctx.mode.value}
                    return res

                error = plan_result.get("error")
                if error:
                    print(f"❌ [ReActLoop] Planner error: {error}")
                    res = ExecutionResult.error(f"Planning failed: {error}")
                    if ctx: res.last_result = {"mode": ctx.mode.value}
                    return res
                print("⏹️ [ReActLoop] No more steps - complete")
                break
            
            # 2. ACT
            exec_result = await self._aexecute_steps(steps, user_input, state, trace_id=ctx.request_id if ctx else None)
            
            # 3. OBSERVE
            all_tool_messages.extend(exec_result.tool_messages)
            if exec_result.outputs:
                all_outputs.append(exec_result.outputs)
            
            final_tool_used = exec_result.tool_used
            final_last_result = exec_result.last_result
            
            # BUG-02: minimal track tool name on success
            if exec_result.status == ExecutionStatus.SUCCESS:
                executed_tools.append(f"{final_tool_used} ✓")
            
            # V18 FIX-04: Search Cascade Activation
            TIER_1_SEARCH_TOOLS = {"search_wikipedia", "search_arxiv"}
            if (
                final_tool_used in TIER_1_SEARCH_TOOLS
                and not cascade_activated
                and _is_empty_or_failed(exec_result.outputs)
            ):
                from ..routing.micro_toolsets import get_micro_toolset, detect_semantic_intent
                intent, hint = detect_semantic_intent(user_input)
                # Note: mapped self.all_tools to list(self.tool_runner.tool_map.values())
                all_tools_list = list(self.tool_runner.tool_map.values())
                expanded = get_micro_toolset(
                    intent, all_tools_list, tool_hint=hint, fallback_mode=True
                )
                available_tools = expanded if expanded else all_tools_list
                cascade_activated = True
                print(f"🔄 [Cascade] Tier-1 empty/failed → expanded toolset to {len(available_tools)} tools")
            
            # FIX-4: Update hindsight for next iteration if not complete
            if exec_result.status != ExecutionStatus.SUCCESS:
                prev_hindsight = f"Iteration {iteration + 1} failed: {exec_result.outputs}"
            else:
                prev_hindsight = f"Iteration {iteration + 1} produced: {exec_result.outputs[:200]}"
            
            # Terminal actions should end the loop
            if self.policy.is_terminal(final_tool_used) and exec_result.status == ExecutionStatus.SUCCESS:
                print(f" [ReActLoop] Async terminal action '{final_tool_used}' completed")
                break  # V17.1: RESTORED terminal break
        
        # V19: Determine final status from tool execution
        # If any tool in any iteration succeeded, we consider it at least PARTIAL
        any_success = any(msg.get('status') == 'success' for msg in all_tool_messages if isinstance(msg, dict))
        if not any_success:
            # Check for LangChain ToolMessage objects too
            any_success = any(getattr(msg, 'status', None) == 'success' for msg in all_tool_messages)

        if 'exec_result' in locals() and exec_result:
            final_status = exec_result.status
        elif iteration == 0 and not steps:
            final_status = ExecutionStatus.FAILED
        else:
            final_status = ExecutionStatus.SUCCESS if any_success else ExecutionStatus.FAILED
            
        return ExecutionResult(
            outputs="\n".join(all_outputs),
            tool_messages=all_tool_messages,
            tool_used=final_tool_used,
            last_result=final_last_result,
            status=final_status
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
        state,
        trace_id: Optional[str] = None
    ) -> ExecutionResult:
        """Execute a list of steps asynchronously."""
        recorder = get_recorder()
        # Ensure trace_id exists for UI correlation
        trace_id = trace_id or f"trace_{int(time.time() * 1000)}"
        
        results_text = []
        tool_messages = []
        tool_used = "None"
        last_result = None
        all_succeeded = True
        any_succeeded = False
        
        for i, step in enumerate(steps[:self.max_iterations]):
            tool_name = step.get("tool")
            tool_args = step.get("args", {})
            call_id = step.get("tool_call_id", f"call_{step.get('id', 0)}")
            
            # Log step start to FlightRecorder
            recorder.log(
                stage="Planner",
                status="INFO",
                content=f"Step {i+1}/{len(steps)}: {tool_name}({tool_args})",
            )
            
            print(f"▶️ Async Executing Step {step.get('id')}: {tool_name} {tool_args}")
            
            # Pacing between steps
            if step.get('id', 0) > 1:
                try:
                    from ..infrastructure.broadcaster import broadcast
                    # V17.2: Propagate trace_id to broadcaster for UI real-time sync
                    broadcast("pacing", {"step": step.get('id'), "tool": tool_name, "trace_id": trace_id})
                except ImportError:
                    pass
                await asyncio.sleep(0.5)
            
            # Broadcast tool start
            try:
                from ..infrastructure.broadcaster import broadcast
                broadcast("tool_start", {"tool": tool_name, "args": tool_args, "trace_id": trace_id})
            except ImportError:
                pass
            
            # Run tool
            run_result = await self.tool_runner.arun(tool_name, tool_args, user_input)
            
            # V17.4: Truncate result for metadata safety
            result_str = str(run_result.output) if run_result.output else ""
            result_preview = result_str[:500] if len(result_str) > 500 else result_str
            if len(result_str) > 500:
                result_preview += "... (truncated)"

            # Log to FlightRecorder with enhanced metadata
            recorder.span(
                stage="Executor",
                status="SUCCESS" if run_result.success else "ERROR",
                content=f"Tool {tool_name} {'succeeded' if run_result.success else 'failed'}",
                trace_id=trace_id,
                tool=tool_name,
                args=tool_args,
                result=result_preview,
                error=result_str if not run_result.success else None
            )

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
