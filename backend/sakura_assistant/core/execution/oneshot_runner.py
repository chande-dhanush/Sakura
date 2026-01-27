"""
Sakura V17: One-Shot Runner
===========================
Execute a single tool without invoking the Planner.

v2.1 HARD CONSTRAINTS:
- Zero LLM calls (regex-only arg extraction)
- Zero retries
- Zero context/memory access for args
- If args incomplete → fail fast, raise exception for downgrade to ITERATIVE

This is the FAST LANE for simple, obvious tool calls.
"""

import re
import time
import logging
from typing import Dict, Any, Optional, Set, List, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from .context import ExecutionContext, ExecutionResult, ExecutionStatus

logger = logging.getLogger(__name__)


class OneShotArgsIncomplete(Exception):
    """
    Raised when regex extraction cannot produce complete args.
    
    Caller should catch this and downgrade to ITERATIVE mode.
    """
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


class OneShotRunner:
    """
    Execute a single, pre-determined tool call.
    
    v2.1 Design:
    - Used when Router provides a definitive tool_hint
    - Does NOT invoke Planner or ReAct loop
    - Regex-only arg extraction (NO LLM FALLBACK)
    - Fails fast if args incomplete
    
    EXTRACTABLE_TOOLS: Only tools with known regex patterns.
    Adding a new tool requires adding its pattern here.
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
    
    # Mapping for router hints to actual tool names
    HINT_MAPPING: Dict[str, str] = {
        "youtube_control": "play_youtube",
        "google_search": "web_search",
        "wikipedia": "search_wikipedia",
        "weather": "get_weather",
        "remind": "set_reminder",
        "timer": "set_timer",
    }
    
    # Required fields per tool
    REQUIRED_FIELDS: Dict[str, List[str]] = {
        "open_app": ["app_name"],
        "spotify_control": ["action"],
        "play_youtube": ["topic"],
        "get_weather": [],  # Location optional, uses default
        "set_reminder": ["message"],
        "set_timer": ["duration"],
        "get_time": [],
        "get_battery": [],
        "get_system_info": [],
        "volume_control": ["action"],
        "screenshot": [],
    }
    
    # Max time for extraction (should be <50ms, pure CPU)
    MAX_EXTRACTION_TIME_MS = 100
    
    def __init__(self, tool_runner: Any, output_handler: Any):
        """
        Initialize OneShotRunner.
        
        Args:
            tool_runner: ToolRunner instance for executing tools
            output_handler: OutputHandler for processing large outputs
        """
        self.tool_runner = tool_runner
        self.output_handler = output_handler
    
    @classmethod
    def can_handle(cls, tool_name: str) -> bool:
        """Check if a tool (or its hint) can be handled by ONE_SHOT."""
        # Resolve hint if necessary
        actual_name = cls.HINT_MAPPING.get(tool_name, tool_name)
        return actual_name in cls.EXTRACTABLE_TOOLS
    
    async def aexecute(
        self,
        tool_name: str,
        ctx: "ExecutionContext"
    ) -> "ExecutionResult":
        """
        Async execution path.
        
        Args:
            tool_name: Name of tool to execute
            ctx: ExecutionContext with user_input and snapshot
        
        Returns:
            ExecutionResult
        
        Raises:
            OneShotArgsIncomplete: If args cannot be extracted
        """
        from .context import ExecutionResult, ExecutionStatus
        from langchain_core.messages import ToolMessage
        
        start_time = time.time()
        user_input = ctx.user_input
        
        # Resolve tool name from hint (e.g., youtube_control -> play_youtube)
        actual_tool = self.HINT_MAPPING.get(tool_name, tool_name)
        
        logger.info(f" [OneShotRunner] Executing {actual_tool} (via {tool_name}) for: {user_input[:50]}...")
        
        # 1. Extract args (regex-only, NO LLM)
        args = self._extract_args(actual_tool, user_input)
        
        extraction_time = (time.time() - start_time) * 1000
        if extraction_time > self.MAX_EXTRACTION_TIME_MS:
            logger.warning(f"⚠️ [OneShotRunner] Slow extraction: {extraction_time:.1f}ms")
        
        # 2. Validate args completeness
        missing = self._get_missing_fields(tool_name, args)
        if missing:
            raise OneShotArgsIncomplete(tool_name, args, missing)
        
        logger.info(f" [OneShotRunner] Extracted args: {args}")
        
        # 3. Run tool
        try:
            result = await self.tool_runner.arun(tool_name, args, user_input)
        except Exception as e:
            logger.error(f" [OneShotRunner] Tool execution failed: {e}")
            return ExecutionResult.error(f"Tool '{tool_name}' failed: {e}")
        
        # 4. Process output
        output = result.output if hasattr(result, 'output') else str(result)
        if self.output_handler:
            output = self.output_handler.intercept_large_output(output, tool_name)
        
        success = result.success if hasattr(result, 'success') else True
        
        # V17.4: Log to FlightRecorder with enhanced metadata (same as ReActLoop)
        try:
            from ...utils.flight_recorder import get_recorder
            recorder = get_recorder()
            
            # Truncate result for metadata safety
            result_preview = output[:500] if len(output) > 500 else output
            if len(output) > 500:
                result_preview += "... (truncated)"
            
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
            logger.warning(f"⚠️ [OneShotRunner] Flight recorder logging failed: {log_err}")
        
        # 5. Create ToolMessage
        tool_msg = ToolMessage(
            tool_call_id=f"oneshot_{tool_name}_{int(time.time())}",
            content=output,
            name=tool_name,
            status="success" if success else "error"
        )
        
        total_time = (time.time() - start_time) * 1000
        logger.info(f" [OneShotRunner] Completed in {total_time:.1f}ms")
        
        return ExecutionResult(
            outputs=output,
            tool_messages=[tool_msg],
            tool_used=tool_name,
            last_result={
                "tool": tool_name, 
                "args": args, 
                "output": output, 
                "success": success
            },
            status=ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED
        )
    
    def _extract_args(self, tool_name: str, user_input: str) -> Dict[str, Any]:
        """
        Extract tool arguments using REGEX ONLY.
        
        NO LLM FALLBACK. If extraction fails, return incomplete args.
        Caller will check completeness and raise OneShotArgsIncomplete.
        """
        text = user_input.lower()
        args: Dict[str, Any] = {}
        
        # ───────────────────────────────────────────────────────────────────
        # OPEN APP
        # ───────────────────────────────────────────────────────────────────
        if tool_name == "open_app":
            # "open X", "launch X", "start X"
            patterns = [
                r'(?:open|launch|start|run)\s+(.+?)(?:\s+app|\s+application)?(?:\s*,|$)',
                r'(?:open|launch|start|run)\s+(.+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, user_input, re.I)
                if match:
                    app_name = match.group(1).strip()
                    # Clean up common suffixes
                    app_name = re.sub(r'\s+(please|for me|now)$', '', app_name, flags=re.I)
                    args["app_name"] = app_name
                    break
        
        # ───────────────────────────────────────────────────────────────────
        # SPOTIFY CONTROL
        # ───────────────────────────────────────────────────────────────────
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
                # Extract song name
                match = re.search(
                    r'play\s+(.+?)(?:\s+on\s+spotify)?(?:\s*,|$)', 
                    user_input, re.I
                )
                if match:
                    song = match.group(1).strip()
                    # Clean up
                    song = re.sub(r'^(some\s+)?(music|song|track)s?$', '', song, flags=re.I).strip()
                    if song:
                        args["song_name"] = song
        
        # ───────────────────────────────────────────────────────────────────
        # PLAY YOUTUBE
        # ───────────────────────────────────────────────────────────────────
        elif tool_name == "play_youtube":
            match = re.search(
                r'play\s+(.+?)\s+(?:on\s+)?youtube', 
                user_input, re.I
            )
            if match:
                args["topic"] = match.group(1).strip()
            else:
                # Fallback: "youtube X"
                match = re.search(r'youtube\s+(.+?)(?:\s*,|$)', user_input, re.I)
                if match:
                    args["topic"] = match.group(1).strip()
        
        # ───────────────────────────────────────────────────────────────────
        # GET WEATHER
        # ───────────────────────────────────────────────────────────────────
        elif tool_name == "get_weather":
            match = re.search(
                r'weather\s+(?:in\s+|for\s+)?(.+?)(?:\?|$)', 
                user_input, re.I
            )
            if match:
                args["city"] = match.group(1).strip()
            # Empty is OK - will use default location
        
        # ───────────────────────────────────────────────────────────────────
        # SET REMINDER
        # ───────────────────────────────────────────────────────────────────
        elif tool_name == "set_reminder":
            # "remind me to X in Y minutes"
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
                # Simpler: "remind me to X"
                match = re.search(r'remind\s+(?:me\s+)?(?:to\s+)?(.+)', user_input, re.I)
                if match:
                    args["message"] = match.group(1).strip()
                    args["delay_minutes"] = 5  # Default 5 min
        
        # ───────────────────────────────────────────────────────────────────
        # SET TIMER
        # ───────────────────────────────────────────────────────────────────
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
        
        # ───────────────────────────────────────────────────────────────────
        # VOLUME CONTROL
        # ───────────────────────────────────────────────────────────────────
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
                # Try to extract percentage
                match = re.search(r'(\d+)\s*%', user_input)
                if match:
                    args["action"] = "set"
                    args["level"] = int(match.group(1))
        
        # ───────────────────────────────────────────────────────────────────
        # NO-ARG TOOLS
        # ───────────────────────────────────────────────────────────────────
        elif tool_name in ("get_time", "get_battery", "get_system_info", "screenshot"):
            # These tools require no args
            pass
        
        return args
    
    def _get_missing_fields(self, tool_name: str, args: Dict[str, Any]) -> List[str]:
        """Check which required fields are missing."""
        required = self.REQUIRED_FIELDS.get(tool_name, [])
        return [f for f in required if f not in args or not args[f]]
