"""
Sakura V20.0: One-Shot Runner
===========================
Execute a single tool without invoking a ReAct loop or Planner.
Uses fast regex extraction where possible, falling back to a single LLM tool-calling call if needed.
"""

import re
import os
import time
import logging
import json
import uuid
import unicodedata
from typing import Dict, Any, Optional, Set, List, TYPE_CHECKING
from dataclasses import dataclass

from ..routing.micro_toolsets import resolve_tool_hint

if TYPE_CHECKING:
    from .context import ExecutionContext, ExecutionResult, ExecutionStatus

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when a security policy is violated."""
    pass


class OneShotArgsIncomplete(Exception):
    """Raised when regex extraction cannot produce complete args."""
    def __init__(self, tool_name: str, extracted_args: Dict[str, Any], missing_fields: List[str]):
        self.tool_name = tool_name
        self.extracted_args = extracted_args
        self.missing_fields = missing_fields
        super().__init__(
            f"ONE_SHOT failed for '{tool_name}': missing {missing_fields}. "
            f"Extracted: {extracted_args}"
        )


@dataclass
class ToolRunResult:
    """Result from running a single tool."""
    output: str
    success: bool
    error: Optional[str] = None


# Path Traversal Security
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
    """Normalize and sanitize paths to prevent traversal."""
    path = unicodedata.normalize('NFKC', path)
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            print(f"   [Security] Blocked path traversal attempt: {path}")
            raise SecurityError(f"Blocked dangerous path: {path[:50]}")
    return os.path.normpath(os.path.abspath(path))


def _validate_tool_input(tool_name: str, args: Dict[str, Any]) -> bool:
    """Blocks malformed tool inputs before execution."""
    for key, val in args.items():
        if isinstance(val, str) and (val.startswith("http://") or val.startswith("https://")):
            if tool_name not in ["web_search", "web_scrape", "play_youtube", "open_site", "search_wikipedia", "search_arxiv"]:
                raise SecurityError(f"Hallucination detected: URL provided as argument to {tool_name}")
    if tool_name in ["file_read", "file_write", "open_app"] and not args.get("path") and not args.get("app_name") and not args.get("filename"):
        raise SecurityError(f"Missing critical argument for {tool_name}")
    return True


class OneShotRunner:
    """
    Execute a single tool call directly.
    First tries regex-only extraction for zero LLM overhead.
    Falls back to single-turn LLM binding if regex is not applicable or fails.
    """
    
    # Tools with known extraction patterns
    EXTRACTABLE_TOOLS: Set[str] = {
        "open_app",
        "spotify_control",
        "play_youtube",
        "get_weather",
        "set_reminder",
        "set_timer",
        "get_time",
        "get_battery",
        "get_system_info",
        "volume_control",
        "screenshot",
    }

    # Required fields per tool
    REQUIRED_FIELDS: Dict[str, List[str]] = {
        "open_app": ["app_name"],
        "spotify_control": ["action"],
        "play_youtube": ["topic"],
        "get_weather": [],
        "set_reminder": ["message"],
        "set_timer": ["duration"],
        "get_time": [],
        "get_battery": [],
        "get_system_info": [],
        "volume_control": ["action"],
        "screenshot": [],
    }
    
    def __init__(self, tool_map: Dict[str, Any], llm: Any, output_handler: Any = None):
        """
        Initialize OneShotRunner.
        
        Args:
            tool_map: Map of available tools
            llm: ReliableLLM instance for single-turn extraction
            output_handler: Optional handler for outputs
        """
        self.tool_map = tool_map
        self.llm = llm
        self.output_handler = output_handler
        
    @classmethod
    def can_handle(cls, tool_name: str) -> bool:
        """Check if a tool can be handled by regex extraction."""
        actual_name = resolve_tool_hint(tool_name)
        return actual_name in cls.EXTRACTABLE_TOOLS

    def _normalize_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize string keys and values."""
        normalized = {}
        for k, v in args.items():
            norm_k = k.lower() if isinstance(k, str) else k
            if isinstance(v, str):
                normalized[norm_k] = v.strip()
            elif isinstance(v, dict):
                normalized[norm_k] = self._normalize_args(v)
            elif isinstance(v, list):
                normalized[norm_k] = [
                    self._normalize_args(item) if isinstance(item, dict)
                    else (item.strip() if isinstance(item, str) else item)
                    for item in v
                ]
            else:
                normalized[norm_k] = v
        return normalized

    def _is_nonsense_output(self, output: str) -> bool:
        """Detect nonsense output."""
        if not output or not output.strip():
            return True
        if len(output.strip()) < 2:
            return True
        if re.search(r'(.)\1{10,}', output):
            return True
        return False

    async def aexecute(
        self,
        tool_name: str,
        ctx: "ExecutionContext",
        llm_overrides: Optional[Dict[str, Any]] = None
    ) -> "ExecutionResult":
        """
        Async execution path.
        """
        from .context import ExecutionResult, ExecutionStatus
        from langchain_core.messages import ToolMessage, HumanMessage, SystemMessage
        
        start_time = time.time()
        user_input = ctx.user_input
        
        # Resolve tool name from hint
        actual_tool = resolve_tool_hint(tool_name)
        
        if actual_tool not in self.tool_map:
            logger.error(f" [OneShotRunner] Tool {actual_tool} not found in tool_map.")
            return ExecutionResult.error(f"Tool '{actual_tool}' not found.")
            
        logger.info(f" [OneShotRunner] Executing {actual_tool} for: {user_input[:50]}...")
        
        # 1. Try regex extraction first (fast lane)
        args = {}
        use_llm_extraction = True
        
        if actual_tool in self.EXTRACTABLE_TOOLS:
            args = self._extract_args(actual_tool, user_input)
            missing = self._get_missing_fields(actual_tool, args)
            if not missing:
                use_llm_extraction = False
                logger.info(f" [OneShotRunner] Regex extraction successful: {args}")
                
        # 2. Fallback to LLM tool call extraction (single turn)
        if use_llm_extraction:
            logger.info(f" [OneShotRunner] Regex incomplete/unsupported. Using LLM single-turn extraction.")
            try:
                tool_instance = self.tool_map[actual_tool]
                # Bind target tool to ReliableLLM
                bound_llm = self.llm.bind_tools([tool_instance])
                
                system_instruction = (
                    f"You are a precise tool parameter extractor. Extract the parameters for the '{actual_tool}' tool "
                    f"based on the user request. Do not answer the query itself, only call the tool with correct arguments."
                )
                messages = [
                    SystemMessage(content=system_instruction),
                    HumanMessage(content=user_input)
                ]
                
                response = await bound_llm.ainvoke(messages)
                
                if hasattr(response, 'tool_calls') and response.tool_calls:
                    args = response.tool_calls[0]["args"]
                    logger.info(f" [OneShotRunner] LLM extraction successful: {args}")
                else:
                    logger.warning(" [OneShotRunner] LLM extraction did not generate tool calls.")
                    args = {}
            except Exception as e:
                logger.error(f" [OneShotRunner] LLM argument extraction failed: {e}")
                args = {}

        # 3. Path Traversal & Sanity Protection
        # Normalize arguments
        args = self._normalize_args(args)
        
        try:
            _validate_tool_input(actual_tool, args)
        except SecurityError as sec_err:
            logger.error(f" [OneShotRunner] Security validation failed: {sec_err}")
            return ExecutionResult.error(str(sec_err))
            
        # Path Traversal Defense
        if actual_tool in ["file_read", "file_write", "open_app"]:
            path_key = "path" if "path" in args else ("app_name" if "app_name" in args else "filename")
            if path_key in args:
                try:
                    args[path_key] = _sanitize_path(args[path_key])
                except SecurityError as sec_err:
                    logger.error(f" [OneShotRunner] Path traversal blocked: {sec_err}")
                    return ExecutionResult.error(str(sec_err))
                
        # Duplicate Call Prevention (Cache Check)
        cache_key = f"{actual_tool}:{json.dumps(args, sort_keys=True)}"
        if ctx and hasattr(ctx, 'tool_call_cache') and cache_key in ctx.tool_call_cache:
            logger.info(f"   [OneShotRunner CACHE HIT] {actual_tool}({args})")
            return ctx.tool_call_cache[cache_key]

        logger.info(f" [OneShotRunner] Final Arguments: {args}")
        
        # 4. Execute tool
        try:
            tool_instance = self.tool_map[actual_tool]
            
            import asyncio
            if hasattr(tool_instance, 'ainvoke'):
                result = await tool_instance.ainvoke(args)
            else:
                result = await asyncio.to_thread(tool_instance.invoke, args)
                
            output = str(result)
            success = True
            
            if self._is_nonsense_output(output):
                # Try once more
                if hasattr(tool_instance, 'ainvoke'):
                    result = await tool_instance.ainvoke(args)
                else:
                    result = await asyncio.to_thread(tool_instance.invoke, args)
                output = str(result)
                if self._is_nonsense_output(output):
                    output = f"[LOW_CONFIDENCE] The tool returned invalid output: {output[:100]}"
                    success = False
        except Exception as e:
            logger.error(f" [OneShotRunner] Tool execution failed: {e}")
            return ExecutionResult.error(f"Tool '{actual_tool}' failed: {e}")
            
        # 5. Context Overflow Protection (Ephemeral Interceptor)
        if len(output) > 2000:
            try:
                from ..memory.ephemeral_store import get_ephemeral_manager
                eph = get_ephemeral_manager()
                if eph:
                    eph_id = eph.ingest_text(output, source_tool=actual_tool)
                    if eph_id and not eph_id.startswith("error"):
                        output = (
                            f"[System: Context Overflow Protection]\n"
                            f"Output too large ({len(output)} chars) to fit in context.\n"
                            f"Content has been securely indexed to Ephemeral Store ID: {eph_id}\n"
                            f"You MUST use the tool 'query_ephemeral(ephemeral_id=\"{eph_id}\", query=\"...\")' "
                            f"to retrieve specific details/sections."
                        )
            except Exception as e:
                logger.warning(f"   [OneShotRunner] Ephemeral ingestion failed: {e}")
                
        # 6. Flight Recorder spans
        try:
            from ...utils.flight_recorder import get_recorder
            recorder = get_recorder()
            result_preview = output[:500] + "... (truncated)" if len(output) > 500 else output
            recorder.span(
                stage="Executor",
                status="SUCCESS" if success else "ERROR",
                content=f"Tool {actual_tool} {'succeeded' if success else 'failed'}",
                trace_id=recorder.trace_id,
                tool=actual_tool,
                args=args,
                result=result_preview,
                error=output if not success else None
            )
        except Exception as log_err:
            logger.warning(f"   [OneShotRunner] Flight recorder logging failed: {log_err}")
            
        # 7. Create ToolMessage
        tool_msg = ToolMessage(
            tool_call_id=f"oneshot_{actual_tool}_{int(time.time())}",
            content=output,
            name=actual_tool,
            status="success" if success else "error"
        )
        
        exec_res = ExecutionResult(
            outputs=output,
            tool_messages=[tool_msg],
            tool_used=actual_tool,
            last_result={
                "tool": actual_tool,
                "args": args,
                "output": output,
                "success": success
            },
            status=ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED
        )
        
        # Populate Cache
        if ctx and hasattr(ctx, 'tool_call_cache'):
            ctx.tool_call_cache[cache_key] = exec_res

        total_time = (time.time() - start_time) * 1000
        logger.info(f" [OneShotRunner] Completed in {total_time:.1f}ms")
        
        return exec_res
        
    def _extract_args(self, tool_name: str, user_input: str) -> Dict[str, Any]:
        """Extract tool arguments using REGEX ONLY."""
        text = user_input.lower()
        args: Dict[str, Any] = {}
        
        if tool_name == "open_app":
            patterns = [
                r'(?:open|launch|start|run)\s+(.+?)(?:\s+app|\s+application)?(?:\s*,|$)',
                r'(?:open|launch|start|run)\s+(.+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, user_input, re.I)
                if match:
                    app_name = match.group(1).strip()
                    app_name = re.sub(r'\s+(please|for me|now)$', '', app_name, flags=re.I)
                    args["app_name"] = app_name
                    break
        
        elif tool_name == "spotify_control":
            if any(w in text for w in ["pause", "stop"]):
                args["action"] = "pause"
            elif "resume" in text or "continue" in text:
                args["action"] = "resume"
            elif "next" in text or "skip" in text:
                args["action"] = "next"
            elif "previous" in text or "prev" in text:
                args["action"] = "previous"
            elif "play" in text:
                args["action"] = "play"
                match = re.search(
                    r'play\s+(.+?)(?:\s+on\s+spotify)?(?:\s*,|$)', 
                    user_input, re.I
                )
                if match:
                    song = match.group(1).strip()
                    song = re.sub(r'^(some\s+)?(music|song|track)s?$', '', song, flags=re.I).strip()
                    if song:
                        args["song_name"] = song
        
        elif tool_name == "play_youtube":
            match = re.search(
                r'play\s+(.+?)\s+(?:on\s+)?youtube', 
                user_input, re.I
            )
            if match:
                args["topic"] = match.group(1).strip()
            else:
                match = re.search(r'youtube\s+(.+?)(?:\s*,|$)', user_input, re.I)
                if match:
                    args["topic"] = match.group(1).strip()
        
        elif tool_name == "get_weather":
            match = re.search(
                r'weather\s+(?:in\s+|for\s+)?(.+?)(?:\?|$)', 
                user_input, re.I
            )
            if match:
                args["city"] = match.group(1).strip()
        
        elif tool_name == "set_reminder":
            match = re.search(
                r'remind\s+(?:me\s+)?(?:to\s+)?(.+?)\s+in\s+(\d+)\s*(min|hour|sec)',
                user_input, re.I
            )
            if match:
                args["message"] = match.group(1).strip()
                amount = int(match.group(2))
                unit = match.group(3).lower()
                if "hour" in unit:
                    args["delay_minutes"] = amount * 60
                elif "sec" in unit:
                    args["delay_minutes"] = amount / 60
                else:
                    args["delay_minutes"] = amount
            else:
                match = re.search(r'remind\s+(?:me\s+)?(?:to\s+)?(.+)', user_input, re.I)
                if match:
                    args["message"] = match.group(1).strip()
                    args["delay_minutes"] = 5  # Default 5 min
        
        elif tool_name == "set_timer":
            match = re.search(r'(\d+)\s*(min|sec|hour|m|s|h)', user_input, re.I)
            if match:
                amount = int(match.group(1))
                unit = match.group(2).lower()
                if unit in ("hour", "h"):
                    args["duration"] = amount * 3600
                elif unit in ("min", "m"):
                    args["duration"] = amount * 60
                else:
                    args["duration"] = amount
        
        elif tool_name == "volume_control":
            if "mute" in text:
                args["action"] = "mute"
            elif "unmute" in text:
                args["action"] = "unmute"
            elif "up" in text or "increase" in text or "louder" in text:
                args["action"] = "up"
            elif "down" in text or "decrease" in text or "quieter" in text:
                args["action"] = "down"
            else:
                match = re.search(r'(\d+)\s*%', user_input)
                if match:
                    args["action"] = "set"
                    args["level"] = int(match.group(1))
        
        return args
    
    def _get_missing_fields(self, tool_name: str, args: Dict[str, Any]) -> List[str]:
        """Check which required fields are missing."""
        required = self.REQUIRED_FIELDS.get(tool_name, [])
        return [f for f in required if f not in args or not args[f]]
