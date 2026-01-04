"""
Tier-1 Forced Tool Router V9.2
Deterministic pattern matching for common actions.

This bypasses LLM discretion entirely for high-confidence patterns.
When a pattern matches, the tool is FORCED - no LLM decides.

V9.2 Audit Fixes:
- Fixed tool names to match tools.py exactly
- Added YouTube pattern BEFORE generic play
- Fixed "stop" pattern to require music context
- Added empty input guard
"""
import re
from typing import Optional, Dict, Any, List


# ═══════════════════════════════════════════════════════════════════════════
# FORCED TOOL PATTERNS - ORDER MATTERS (first match wins)
# ═══════════════════════════════════════════════════════════════════════════
# These patterns guarantee a specific tool is called. No LLM hallucination possible.
# Tool names must EXACTLY match function names in tools.py

FORCED_PATTERNS: List[Dict[str, Any]] = [
    # ═══════════════════════════════════════════════════════════════════════
    # WEB SEARCH (High priority - explicit search requests)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "pattern": r"\b(search|google|look\s*up|find\s*out|browse)\s+(the\s+)?(web|internet|online)\s*(for|about)?\s*(.+)?",
        "tool": "web_search",
        "args_extractor": lambda m, text: {"query": _extract_search_query(text)},
        "description": "search the web for X",
    },
    {
        "pattern": r"\bsearch\s+(for\s+)?(.+)$",
        "tool": "web_search",
        "args_extractor": lambda m, text: {"query": m.group(2).strip() if m.group(2) else text},
        "description": "search for X",
    },
    
    # ═══════════════════════════════════════════════════════════════════════
    # YOUTUBE (Must come BEFORE generic "play X" pattern!)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "pattern": r"\b(play|open|watch)\s+(.+?)\s+on\s+youtube\b",
        "tool": "play_youtube",
        "args_extractor": lambda m, text: {"topic": m.group(2).strip()},
        "description": "play X on youtube",
    },
    {
        "pattern": r"\b(play|open)\s+youtube\b",
        "tool": "play_youtube",
        "args_extractor": lambda m, text: {"topic": ""},
        "description": "open youtube",
    },
    
    # ═══════════════════════════════════════════════════════════════════════
    # MUSIC/SPOTIFY CONTROL
    # ═══════════════════════════════════════════════════════════════════════
    {
        "pattern": r"\b(play|start)\s+(some\s+)?(music|songs?|spotify|tracks?|playlist)\s*$",
        "tool": "spotify_control",
        "args_extractor": lambda m, text: {"action": "play"},
        "description": "play music/spotify (generic)",
    },
    {
        "pattern": r"\bplay\s+(?!music|song|spotify|track|youtube)(.+?)(\s+on\s+spotify)?\s*$",
        "tool": "spotify_control",
        "args_extractor": lambda m, text: {"action": "play", "song_name": m.group(1).strip()},
        "description": "play [song name] on spotify",
    },
    {
        # FIXED: Require explicit music context to avoid matching "stop talking"
        "pattern": r"\b(pause|stop)\s+(the\s+)?(music|song|spotify|playback|track)\b",
        "tool": "spotify_control",
        "args_extractor": lambda m, text: {"action": "pause"},
        "description": "pause/stop music",
    },
    {
        "pattern": r"\b(next|skip)\s*(track|song)?\s*$",
        "tool": "spotify_control",
        "args_extractor": lambda m, text: {"action": "next"},
        "description": "next/skip track",
    },
    {
        "pattern": r"\b(previous|prev|back)\s*(track|song)?\s*$",
        "tool": "spotify_control",
        "args_extractor": lambda m, text: {"action": "previous"},
        "description": "previous track",
    },
    
    # ═══════════════════════════════════════════════════════════════════════
    # REMINDERS/TIMERS
    # ═══════════════════════════════════════════════════════════════════════
    {
        "pattern": r"\b(remind|reminder)\s+(me\s+)?(to|about)\s+(.+?)(\s+in\s+(\d+)\s*(min|minute|hour|hr|sec|second)s?)?\s*$",
        "tool": "set_reminder",
        "args_extractor": lambda m, text: _extract_reminder_args(m, text),
        "description": "remind me to X in Y mins",
    },
    {
        "pattern": r"\b(set|start)\s+(a\s+)?timer\s+(for\s+)?(\d+)\s*(min|minute|hour|hr|sec|second)s?\b",
        "tool": "set_timer",
        "args_extractor": lambda m, text: {"minutes": _parse_to_minutes(m.group(4), m.group(5))},
        "description": "set timer for X mins",
    },
    
    # ═══════════════════════════════════════════════════════════════════════
    # CALENDAR
    # ═══════════════════════════════════════════════════════════════════════
    {
        "pattern": r"\b(what('s|s| is)|show|check|get)\s+(on\s+)?(my\s+)?calendar\b",
        "tool": "calendar_get_events",
        "args_extractor": lambda m, text: {},
        "description": "show my calendar",
    },
    {
        "pattern": r"\b(schedule|create|add)\s+(a\s+)?(meeting|event|appointment)\b",
        "tool": "calendar_create_event",
        "args_extractor": lambda m, text: {"title": text, "start_time": "", "end_time": ""},
        "description": "schedule a meeting (needs LLM refinement)",
    },
    
    # ═══════════════════════════════════════════════════════════════════════
    # EMAIL (Fixed tool names to match tools.py)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "pattern": r"\b(check|read|show|get)\s+(my\s+)?(email|inbox|mail|gmail)s?\b",
        "tool": "gmail_read_email",  # FIXED: was "email_read"
        "args_extractor": lambda m, text: {},
        "description": "check my email",
    },
    {
        "pattern": r"\b(send|compose|write)\s+(an?\s+)?(email|mail)\b",
        "tool": "gmail_send_email",  # FIXED: was "email_send"
        "args_extractor": lambda m, text: {"to": "", "subject": "", "body": ""},
        "description": "send an email (needs LLM refinement)",
    },
    
    # ═══════════════════════════════════════════════════════════════════════
    # NOTES (Import from utils/note_tools.py)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "pattern": r"\b(make|create|add|write)\s+(a\s+)?note\s*[:\-]?\s*(.+)?$",
        "tool": "note_create",  # FIXED: was "note_new"
        "args_extractor": lambda m, text: _extract_note_args(m, text),
        "description": "make a note",
    },
    {
        "pattern": r"\b(show|list|read)\s+(my\s+)?notes\b",
        "tool": "note_list",
        "args_extractor": lambda m, text: {},
        "description": "show my notes",
    },
    
    # ═══════════════════════════════════════════════════════════════════════
    # SYSTEM
    # ═══════════════════════════════════════════════════════════════════════
    {
        "pattern": r"\b(open|launch|start)\s+(.+?)\s*(app|application|program)?\s*$",
        "tool": "open_app",
        "args_extractor": lambda m, text: {"app_name": m.group(2).strip()},
        "description": "open [app name]",
    },
    {
        "pattern": r"\b(take\s+a\s+)?screenshot\b",
        "tool": "read_screen",  # FIXED: was "take_screenshot"
        "args_extractor": lambda m, text: {"prompt": "Describe what is on the screen"},
        "description": "take a screenshot",
    },
    {
        "pattern": r"\b(read|analyze|look\s+at)\s+(the\s+|my\s+)?screen\b",
        "tool": "read_screen",
        "args_extractor": lambda m, text: {"prompt": text},
        "description": "read/analyze screen",
    },
    
    # ═══════════════════════════════════════════════════════════════════════
    # WEATHER
    # ═══════════════════════════════════════════════════════════════════════
    {
        "pattern": r"\b(what('s|s| is) the )?weather\s*(in\s+(.+?))?(\?)?$",
        "tool": "get_weather",
        "args_extractor": lambda m, text: {"city": m.group(4).strip() if m.group(4) else ""},
        "description": "what's the weather",
    },
    
    # ═══════════════════════════════════════════════════════════════════════
    # FORCE COMPLEX (Don't force specific tool, but ensure LLM planning runs)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "pattern": r"^(what|who|when|where|how|why|is|are|can|could|would|should)\b.+\?$",
        "tool": None,
        "args_extractor": None,
        "description": "Question detected",
        "force_complex": True,
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def _extract_search_query(text: str) -> str:
    """Extract search query from text, removing command prefixes."""
    patterns_to_remove = [
        r"^(can you |please |could you )?",
        r"(search|google|look up|find out|browse)\s+(the\s+)?(web|internet|online)?\s*(for|about)?\s*",
    ]
    query = text.lower()
    for p in patterns_to_remove:
        query = re.sub(p, "", query, flags=re.IGNORECASE)
    return query.strip() or text


def _extract_reminder_args(match, text: str) -> Dict[str, Any]:
    """Extract reminder message and delay."""
    message = match.group(4).strip() if match.group(4) else text
    delay = 5.0  # Default 5 minutes
    
    if match.group(6) and match.group(7):
        delay = _parse_to_minutes(match.group(6), match.group(7))
    
    return {"message": message, "delay_minutes": delay}


def _parse_to_minutes(value: str, unit: str) -> float:
    """Parse duration to minutes."""
    val = float(value)
    unit = unit.lower()
    if unit.startswith("sec"):
        return val / 60
    elif unit.startswith("min"):
        return val
    elif unit.startswith("hour") or unit.startswith("hr"):
        return val * 60
    return val  # Default to minutes


def _extract_note_args(match, text: str) -> Dict[str, Any]:
    """Extract note content from text."""
    # Try to get content after "note" keyword
    if match.group(3):
        return {"title": "Quick Note", "content": match.group(3).strip()}
    
    # Fallback: extract after common patterns
    for pattern in [r"note[:\-\s]+(.+)$", r"note\s+(.+)$"]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return {"title": "Quick Note", "content": m.group(1).strip()}
    
    return {"title": "Quick Note", "content": text}


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ROUTER FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def get_forced_tool(user_input: str) -> Optional[Dict[str, Any]]:
    """
    Check if input matches a forced pattern.
    
    Args:
        user_input: The user's message
        
    Returns:
        None if no match (let LLM decide)
        Dict with {"tool": str, "args": dict, "force_complex": bool} if matched
    """
    # EDGE CASE: Empty or whitespace-only input
    if not user_input or not user_input.strip():
        return None
    
    text = user_input.strip()
    
    for pattern_def in FORCED_PATTERNS:
        match = re.search(pattern_def["pattern"], text, re.IGNORECASE)
        if match:
            tool = pattern_def["tool"]
            
            # Some patterns just force COMPLEX routing without specific tool
            if pattern_def.get("force_complex") and not tool:
                print(f"🎯 [Tier-1] Force COMPLEX: {pattern_def['description']}")
                return {"tool": None, "args": {}, "force_complex": True}
            
            # Extract arguments safely
            args = {}
            if pattern_def["args_extractor"]:
                try:
                    args = pattern_def["args_extractor"](match, user_input)
                except Exception as e:
                    print(f"⚠️ [Tier-1] Arg extraction failed: {e}")
                    args = {}
            
            print(f"🎯 [Tier-1] Forced: {tool} ← '{pattern_def['description']}'")
            return {"tool": tool, "args": args, "force_complex": False}
    
    return None


def build_forced_plan(forced_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a plan dict from forced tool result."""
    if not forced_result or not forced_result.get("tool"):
        return None
    
    return {
        "plan": [{
            "id": 1,
            "tool": forced_result["tool"],
            "args": forced_result["args"],
            "forced": True  # Mark as forced for logging
        }],
        "forced": True
    }
