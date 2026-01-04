"""
Sakura V5: Retry Formatter - Local Response Generation (No LLM)

Purpose: Format retry path outputs without using LLM call budget.
Design: Rule-based, deterministic, personality-aware phrasing.
"""
from typing import Optional


# Tool-specific success templates (personality: calm, efficient)
TOOL_SUCCESS_TEMPLATES = {
    # Music/Media
    "spotify_control": "Done. {action_desc}",
    "play_youtube": "Playing on YouTube now.",
    
    # Communication
    "gmail_send_email": "Email sent to {to}.",
    "gmail_read_email": "Here's what I found in your inbox:\n{result_preview}",
    
    # Calendar/Tasks
    "calendar_get_events": "Your schedule:\n{result_preview}",
    "calendar_create_event": "Added to calendar: {title}",
    "tasks_list": "Your tasks:\n{result_preview}",
    "tasks_create": "Task created: {title}",
    
    # Notes
    "note_create": "Note created: {title}",
    "note_append": "Updated note: {title}",
    "note_read": "{result_preview}",
    "note_list": "Notes found:\n{result_preview}",
    
    # Search/RAG
    "web_search": "Here's what I found after refining the search:\n{result_preview}",
    "fetch_document_context": "From your documents:\n{result_preview}",
    "web_scrape": "From that page:\n{result_preview}",
    
    # Files
    "file_read": "{result_preview}",
    "file_write": "File saved.",
    "list_files": "{result_preview}",
    
    # System
    "open_app": "Opening {app_name}.",
    "read_screen": "{result_preview}",
}

# Default fallback
DEFAULT_SUCCESS_TEMPLATE = "Done."
DEFAULT_FAILURE_TEMPLATE = "I tried again but still couldn't complete that. {reason}"


def format_retry_response(
    tool_name: str,
    tool_args: dict,
    tool_output: str,
    success: bool,
    failure_reason: Optional[str] = None,
    is_retry: bool = True  # V5.1: Explicit retry flag for honest language
) -> str:
    """
    Format a response for the retry path (no LLM call).
    
    V5.1 Hardening: Responses are explicitly honest about retry attempts.
    V7: Respects HIDE_RETRY_PREFIX config for smoother UX.
    
    Args:
        tool_name: Name of the executed tool
        tool_args: Arguments passed to the tool
        tool_output: Raw output from tool
        success: Whether tool execution succeeded
        failure_reason: Verifier's failure reason (if retrying again)
        is_retry: Whether this is a retry attempt (adds honesty prefix)
    
    Returns:
        Formatted response string
    """
    # V7: Check if we should hide retry prefix
    from ..config import HIDE_RETRY_PREFIX
    if HIDE_RETRY_PREFIX:
        is_retry = False  # Suppress retry language
    if not success:
        # V5.1: Honest failure after retry
        if is_retry:
            return f"I tried a different approach, but still couldn't complete that. {failure_reason or 'Please try rephrasing your request.'}"
        return DEFAULT_FAILURE_TEMPLATE.format(
            reason=failure_reason or "Please try rephrasing your request."
        )
    
    template = TOOL_SUCCESS_TEMPLATES.get(tool_name, DEFAULT_SUCCESS_TEMPLATE)
    
    # Build context for template substitution
    context = {
        "result_preview": _truncate_preview(tool_output),
        "action_desc": _describe_spotify_action(tool_args) if tool_name == "spotify_control" else "",
        **tool_args  # Include all tool args for template access
    }
    
    try:
        base_response = template.format(**context)
    except KeyError:
        # Template has placeholders we don't have - use simplified version
        base_response = _simple_format(tool_name, tool_output, success)
    
    # V5.1: Prepend honest retry acknowledgment
    if is_retry:
        retry_prefixes = {
            "web_search": "After refining my search, ",
            "fetch_document_context": "After adjusting my approach, ",
            "spotify_control": "",  # Spotify doesn't need prefix
            "play_youtube": "",
            "gmail_send_email": "",
            "calendar_create_event": "",
            "tasks_create": "",
            "note_create": "",
        }
        prefix = retry_prefixes.get(tool_name, "After a second attempt, ")
        
        # Only add prefix for non-empty prefixes
        if prefix:
            # Lowercase first char of base_response if prefix is added
            if base_response and base_response[0].isupper():
                base_response = base_response[0].lower() + base_response[1:]
            return prefix + base_response
    
    return base_response


def format_multi_tool_response(
    tool_results: list,  # List of (tool_name, tool_args, tool_output, success)
    overall_success: bool
) -> str:
    """
    Format response when multiple tools were executed in retry.
    
    Args:
        tool_results: List of (tool_name, args, output, success) tuples
        overall_success: Whether the overall operation succeeded
    
    Returns:
        Formatted response string
    """
    if not tool_results:
        return "I processed your request." if overall_success else "I couldn't complete that request."
    
    if len(tool_results) == 1:
        name, args, output, success = tool_results[0]
        return format_retry_response(name, args, output, success)
    
    # Multiple tools - summarize
    parts = []
    for name, args, output, success in tool_results:
        if success:
            short = _get_tool_verb(name)
            parts.append(f"✓ {short}")
    
    if parts:
        return "Done: " + ", ".join(parts)
    else:
        return "I ran into some issues completing that request."


def _truncate_preview(text: str, max_len: int = 300) -> str:
    """Truncate output for preview, preserving useful content."""
    if not text:
        return "(no content)"
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _describe_spotify_action(args: dict) -> str:
    """Human-readable Spotify action description."""
    action = args.get("action", "").lower()
    song = args.get("song_name", "")
    
    if action == "play" and song:
        return f"Playing {song}"
    elif action == "play":
        return "Resumed playback"
    elif action == "pause":
        return "Paused"
    elif action == "next":
        return "Skipped to next track"
    elif action == "previous":
        return "Playing previous track"
    return action.capitalize()


def _get_tool_verb(tool_name: str) -> str:
    """Short verb form of tool action for summaries."""
    verbs = {
        "spotify_control": "Music",
        "play_youtube": "YouTube",
        "gmail_send_email": "Email sent",
        "gmail_read_email": "Email checked",
        "calendar_get_events": "Calendar",
        "calendar_create_event": "Event added",
        "tasks_list": "Tasks",
        "tasks_create": "Task added",
        "note_create": "Note created",
        "note_append": "Note updated",
        "note_read": "Note read",
        "web_search": "Web search",
        "fetch_document_context": "Documents",
        "web_scrape": "Page scraped",
        "file_read": "File read",
        "file_write": "File saved",
        "open_app": "App opened",
    }
    return verbs.get(tool_name, tool_name)


def _simple_format(tool_name: str, output: str, success: bool) -> str:
    """Fallback simple formatting."""
    if not success:
        return "I couldn't complete that action."
    
    verb = _get_tool_verb(tool_name)
    if output and len(output) < 200:
        return f"{verb}: {output}"
    return f"{verb} completed."
