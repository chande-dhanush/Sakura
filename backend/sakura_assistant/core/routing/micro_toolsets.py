"""
Sakura V16: Micro-Toolsets for Token Optimization
==================================================
Pre-defined minimal toolsets for common intents.

V16 Features:
- Always includes UNIVERSAL_TOOLS to prevent "Capability Blindness"
- Semantic Tool Gating to break "Tavily Trap" 
- Tool Hierarchy: Specialized APIs > General Search
"""
from typing import List, Set, Optional, Tuple


# =============================================================================
# UNIVERSAL TOOLS - Always included in every toolset
# =============================================================================

UNIVERSAL_TOOLS: Set[str] = {
    "web_search",       # Fallback for any search need
    "get_system_info",  # Time/date queries
    "quick_math",       # Calculations
}


# =============================================================================
# TOOL HIERARCHY - Specialized APIs before general search
# =============================================================================

# V16: Break the "Tavily Trap" - prefer specialized APIs for specific query types
TOOL_HIERARCHY = {
    # Intent -> (Primary tools, Fallback tools)
    # Primary tools are tried first; fallback only if primary doesn't apply
    "encyclopedia": {
        "primary": ["search_wikipedia"],  # Structured, verified data
        "fallback": ["web_search"],
        "triggers": ["who is", "what is", "define", "explain", "meaning of", "history of", "biography"],
    },
    "scientific": {
        "primary": ["search_arxiv", "search_wikipedia"],
        "fallback": ["web_search"],
        "triggers": ["research", "paper", "study", "scientific", "arxiv", "journal"],
    },
    "news": {
        "primary": ["get_news", "web_search"],  # News-specific or fresh search
        "fallback": [],
        "triggers": ["news", "latest", "recent", "today", "happening", "current events"],
    },
    "weather": {
        "primary": ["get_weather"],
        "fallback": [],
        "triggers": ["weather", "temperature", "forecast", "rain", "sunny"],
    },
}


# =============================================================================
# MICRO-TOOLSETS - Intent-specific minimal sets
# =============================================================================

MICRO_TOOLSETS = {
    "music": {
        "primary": ["spotify_control", "play_youtube", "volume_control"],
        "description": "Music playback and control",
    },
    "email": {
        "primary": ["gmail_read_email", "gmail_send_email"],
        "description": "Email operations",
    },
    "calendar": {
        "primary": ["calendar_get_events", "calendar_create_event", "set_reminder", "set_timer"],
        "description": "Calendar and reminders",
    },
    "notes": {
        "primary": ["note_create", "note_read", "note_append", "note_list", "note_search"],
        "description": "Note-taking operations",
    },
    "search": {
        "primary": ["web_search", "search_wikipedia", "search_arxiv", "web_scrape", "get_news"],
        "description": "Web search and research",
    },
    "file": {
        "primary": ["file_read", "file_write", "file_open", "clipboard_read", "clipboard_write"],
        "description": "File and clipboard operations",
    },
    "system": {
        "primary": ["open_app", "read_screen", "get_location", "get_system_info"],
        "description": "System control and info",
    },
}


def detect_semantic_intent(user_input: str) -> Tuple[str, Optional[str]]:
    """
    V16: Detect semantic intent and preferred tool category.
    
    Returns:
        (basic_intent, tool_hint) - e.g., ("search", "encyclopedia")
    """
    text = user_input.lower()
    
    # Check tool hierarchy triggers first (semantic gating)
    for category, config in TOOL_HIERARCHY.items():
        for trigger in config["triggers"]:
            if trigger in text:
                return ("search", category)
    
    # Basic intent detection
    if any(kw in text for kw in ["play", "pause", "skip", "music", "song", "spotify", "youtube"]):
        return ("music", None)
    
    if any(kw in text for kw in ["email", "mail", "inbox", "gmail", "send email"]):
        return ("email", None)
    
    if any(kw in text for kw in ["calendar", "schedule", "event", "meeting", "appointment"]):
        return ("calendar", None)
    
    if any(kw in text for kw in ["note", "notes", "write down", "jot"]):
        return ("notes", None)
    
    if any(kw in text for kw in ["search", "find", "look up", "research"]):
        return ("search", None)
    
    if any(kw in text for kw in ["file", "open file", "read file", "clipboard"]):
        return ("file", None)
    
    if any(kw in text for kw in ["open app", "screenshot", "screen", "system"]):
        return ("system", None)
    
    return ("general", None)


def get_micro_toolset(intent: str, all_tools: list, tool_hint: str = None, fallback_mode: bool = False) -> list:
    """
    Get minimal toolset for intent with semantic gating.
    
    Args:
        intent: The detected intent
        all_tools: Full list of tools
        tool_hint: Semantic hint (encyclopedia, etc.)
        fallback_mode: If True, include fallback tools (unlock cascading)
        
    V16: Uses TOOL_HIERARCHY. V16.1: Supports fallback cascade.
    """
    # V17.2: If fallback mode is active (Complex Request or Retry), 
    # ABORT semantic gating and return None. This forces the caller to use ALL tools.
    if fallback_mode:
        print(f" [Cascade] Fallback active: Disabling Semantic Gating for {intent}")
        return None

    target_names: Set[str] = set()
    
    # V16: Apply semantic tool gating if hint provided
    if tool_hint and tool_hint in TOOL_HIERARCHY:
        hierarchy = TOOL_HIERARCHY[tool_hint]
        target_names.update(hierarchy["primary"])
        
        # V16.1: Cascade Trigger
        # Unlock fallback tools if explicitly requested (e.g., primary failed)
        if fallback_mode:
            target_names.update(hierarchy["fallback"])
            print(f" [Cascade] Unlocking fallback tools for {tool_hint}: {hierarchy['fallback']}")
        else:
            print(f" [Semantic Gating] {tool_hint}: Using {hierarchy['primary']}, hiding general search")
            
        # V16.1: Add universal tools EXCEPT web_search (keep Tavily hidden)
        target_names.update(t for t in UNIVERSAL_TOOLS if t != "web_search")
    else:
        # Add universal tools only when not in semantic gating mode
        target_names.update(UNIVERSAL_TOOLS)
        
        # Add intent-specific tools
        if intent in MICRO_TOOLSETS:
            target_names.update(MICRO_TOOLSETS[intent]["primary"])
    
    # Filter tools
    micro_tools = [t for t in all_tools if t.name in target_names]
    
    # Validate we have enough tools
    # V16.1: Allow smaller toolsets (e.g. just Wikipedia) if semantic gating is active
    min_tools = 1 if tool_hint else 2
    
    if len(micro_tools) >= min_tools:
        print(f"⚡ [Micro-Toolset] {intent}: {len(micro_tools)} tools")
        return micro_tools
    
    # Fallback: return None to signal caller should use full filtering
    return None


def detect_intent_from_input(user_input: str) -> str:
    """
    Lightweight intent detection (backward compatible wrapper).
    
    Returns:
        Intent string or "general" if no specific match.
    """
    intent, _ = detect_semantic_intent(user_input)
    return intent
