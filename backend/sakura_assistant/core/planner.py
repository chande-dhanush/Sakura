import json
from typing import Dict, Any, Optional, Set
from langchain_core.messages import SystemMessage, HumanMessage
from ..config import (
    GROQ_API_KEY,
    PLANNER_SYSTEM_PROMPT,
    PLANNER_RETRY_PROMPT,
)
from .tools import get_all_tools

# V5.1: Prompts and tool schemas now imported from config.py for centralized management

# Use imported prompt
PLANNER_STATIC_PROMPT = PLANNER_SYSTEM_PROMPT

# (Legacy helper functions removed in V7 refactor)

# V4.2: Planner cache for idempotent commands (saves API calls)
# ONLY cache commands that are: deterministic, no arguments, no time-sensitivity
_CACHEABLE_PATTERNS = {
    "play spotify": {"plan": [{"id": 1, "tool": "spotify_control", "args": {"action": "play"}}]},
    "pause spotify": {"plan": [{"id": 1, "tool": "spotify_control", "args": {"action": "pause"}}]},
    "pause music": {"plan": [{"id": 1, "tool": "spotify_control", "args": {"action": "pause"}}]},
    "stop music": {"plan": [{"id": 1, "tool": "spotify_control", "args": {"action": "pause"}}]},
    "next track": {"plan": [{"id": 1, "tool": "spotify_control", "args": {"action": "next"}}]},
    "next song": {"plan": [{"id": 1, "tool": "spotify_control", "args": {"action": "next"}}]},
    "previous track": {"plan": [{"id": 1, "tool": "spotify_control", "args": {"action": "previous"}}]},
    "previous song": {"plan": [{"id": 1, "tool": "spotify_control", "args": {"action": "previous"}}]},
    "show calendar": {"plan": [{"id": 1, "tool": "calendar_get_events", "args": {}}]},
    "open calendar": {"plan": [{"id": 1, "tool": "calendar_get_events", "args": {}}]},
    "list tasks": {"plan": [{"id": 1, "tool": "tasks_list", "args": {}}]},
    "show tasks": {"plan": [{"id": 1, "tool": "tasks_list", "args": {}}]},
    "list notes": {"plan": [{"id": 1, "tool": "note_list", "args": {}}]},
    "show notes": {"plan": [{"id": 1, "tool": "note_list", "args": {}}]},
}


def _normalize_for_cache(text: str) -> str:
    """Normalize input for cache lookup."""
    return text.lower().strip()


def _log_planner_usage(est_tokens: int, num_steps: int, is_retry: bool = False):
    """
    V5.1 Test-Phase: Log planner token usage to daily file.
    No behavior changes - purely observational.
    """
    import os
    from datetime import datetime
    
    try:
        log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(log_dir, f"planner_usage_{today}.log")
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        mode = "retry" if is_retry else "first"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{timestamp}|{mode}|{est_tokens}|{num_steps}\n")
    except Exception:
        pass  # Silent fail - logging should never break planner


class Planner:
    def __init__(self, llm):
        """
        V9.2: Initialize Planner with a fast, obedient LLM (llama-3.1-8b-instant).
        Tier-1 patterns handle common cases deterministically.
        """
        self.llm = llm

    def _filter_tools(self, all_tools: list, intent: str, user_input: str = "") -> list:
        """
        V9.1: Token Diet - ALWAYS filter tools to stay under 8K TPM limit.
        Never returns all 48 tools - always filters down to ~10-15 max.
        """
        from ..config import TOOL_GROUPS, TOOL_GROUPS_UNIVERSAL
        
        # --- Step 1: Extract keywords from user input ---
        user_lower = user_input.lower()
        
        # Keyword to tool group mapping (expanded)
        KEYWORD_TO_GROUP = {
            # Music
            "play": "music", "music": "music", "spotify": "music", "song": "music",
            "pause": "music", "skip": "music", "volume": "music", "youtube": "music",
            # Search (including ephemeral RAG and document queries)
            "search": "search", "google": "search", "find": "search", "look up": "search",
            "news": "search", "wikipedia": "search", "arxiv": "search", "scrape": "search",
            "document": "search", "refer": "search", "content": "search", "context": "search",
            "attached": "search", "uploaded": "search", "ingested": "search", "docs": "search",
            "pdf": "search", "file i": "search", "from the": "search",
            # Email
            "email": "email", "gmail": "email", "mail": "email", "inbox": "email",
            # Calendar
            "calendar": "calendar", "event": "calendar", "schedule": "calendar",
            "reminder": "calendar", "remind": "calendar", "timer": "calendar",
            # System
            "file": "system", "open": "system", "screen": "system", "note": "system",
            "clipboard": "system", "copy": "system", "paste": "system", "task": "system",
            "bookmark": "system", "site": "system", "shortcut": "system", "url": "system",
            # Utility
            "weather": "utility", "convert": "utility", "math": "utility",
            "calculate": "utility", "define": "utility", "location": "utility",
        }
        
        # --- Step 2: Detect which groups are needed ---
        detected_groups = set()
        for keyword, group in KEYWORD_TO_GROUP.items():
            if keyword in user_lower:
                detected_groups.add(group)
        
        # --- Step 3: If intent is specific, add that group too ---
        if intent in TOOL_GROUPS:
            detected_groups.add(intent)
        
        # --- Step 4: Default to system+utility if nothing detected ---
        if not detected_groups:
            detected_groups = {"system", "utility"}
        
        # --- Step 5: Build filtered tool list ---
        filtered = []
        all_target_keywords = []
        for group in detected_groups:
            all_target_keywords.extend(TOOL_GROUPS.get(group, []))
        
        for tool in all_tools:
            t_name = tool.name.lower()
            # Match against group keywords OR universal tools
            if any(k in t_name for k in all_target_keywords) or t_name in TOOL_GROUPS_UNIVERSAL:
                filtered.append(tool)
        
        # --- Step 6: Enforce minimum (prevent too aggressive filtering) ---
        if len(filtered) < 5:
            # Add universal tools
            for tool in all_tools:
                if tool.name.lower() in TOOL_GROUPS_UNIVERSAL and tool not in filtered:
                    filtered.append(tool)
        
        # --- Step 7: Enforce MAXIMUM (token budget) ---
        MAX_TOOLS = 15  # Hard cap to stay under 8K TPM
        if len(filtered) > MAX_TOOLS:
            filtered = filtered[:MAX_TOOLS]
        
        
        # V9.1: Validate tools before returning
        valid_tools = []
        for tool in filtered:
            if hasattr(tool, 'name') and tool.name:
                valid_tools.append(tool)
            else:
                print(f"⚠️ Planner: Skipping invalid tool (no name): {tool}")
        
        if not valid_tools:
            print(f"❌ Planner: No valid tools after filtering - falling back to all tools")
            valid_tools = all_tools
        
        print(f"🔧 Planner: {len(all_tools)} → {len(valid_tools)} tools (Groups: {detected_groups})")
        return valid_tools

    def plan(self, user_input: str, context: str = "", hindsight: str = None,
             intent_mode: str = "action", resolution=None, tool_history: list = None) -> Dict[str, Any]:
        """
        Generates a tool execution plan using Native Function Calling (Tool Use).
        V7 Refactor: Replaces JSON prompting with bind_tools().
        V8: Supports 'tool_history' for ReAct iterative loops.
        V9.2: Tier-1 forced routing for deterministic actions.
        """
        # V5.1: REASONING_ONLY mode - no tools needed
        if intent_mode == "reasoning":
            print(f"🧠 Planner: REASONING mode - skipping tools")
            return {"plan": [], "mode": "reasoning"}
        
        # V9.2: TIER-1 FORCED ROUTING (Deterministic - bypasses LLM)
        # Only check on first call (not during ReAct loop retries)
        if not hindsight and not tool_history:
            from .forced_router import get_forced_tool, build_forced_plan
            forced = get_forced_tool(user_input)
            if forced and forced.get("tool"):
                plan = build_forced_plan(forced)
                if plan:
                    print(f"⚡ [Tier-1] Forced plan: {forced['tool']}")
                    return plan
        
        # V4.2: Check cache for idempotent commands (skip if retrying or data_then_reason)
        # V8: SKIP CACHE if input has tool_history (dynamic loop)
        from ..config import ENABLE_PLANNER_CACHE
        if ENABLE_PLANNER_CACHE and not hindsight and not tool_history and intent_mode == "action":
            normalized = _normalize_for_cache(user_input)
            if normalized in _CACHEABLE_PATTERNS:
                print(f"⚡ Planner: Cache hit for '{normalized}'")
                return _CACHEABLE_PATTERNS[normalized]
        
        # V7: Build reference context from World Graph resolution
        reference_block = ""
        if resolution and resolution.resolved:
            resolved = resolution.resolved
            if hasattr(resolved, 'name'):  # EntityNode
                reference_block = f"\n[RESOLVED REFERENCE]\nUser is referring to: {resolved.name} ({resolved.type.value if hasattr(resolved, 'type') else 'entity'})\n"
            elif hasattr(resolved, 'tool'):  # ActionNode
                reference_block = f"\n[RESOLVED REFERENCE]\nUser is referring to last action: {resolved.tool} with args {resolved.args}\n"
            
            if resolution.action == "repeat":
                reference_block += "ACTION: User wants to REPEAT this action.\n"
            elif resolution.action == "modify_tool":
                reference_block += "ACTION: User wants to do the SAME THING with a DIFFERENT tool.\n"
            
            print(f"📊 [V7] Planner: Injecting resolved reference (conf={resolution.confidence:.2f})")
        
        # Include graph context if provided
        context_block = ""
        if context and len(context) > 10:
            context_block = f"\n[GRAPH CONTEXT]\n{context}\n"
        
        # V5: Hindsight injection
        hindsight_block = ""
        if hindsight:
            # RETRY PATH
            system_prompt = PLANNER_RETRY_PROMPT.format(
                user_input=user_input,
                context=context_block + reference_block,
                hindsight=hindsight
            )
            user_content = f"Original request: {user_input}"
            print(f"🔄 Planner: Retry mode - {hindsight[:40]}...")
        else:
            # FIRST CALL
            system_prompt = PLANNER_STATIC_PROMPT.format(
                context=context_block + reference_block
            )
            user_content = f"Request: {user_input}"
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content)
        ]
        
        # V8: Append tool history for ReAct loop (previous tool calls + results)
        if tool_history:
            # V9.1 Optimization: Truncate history to avoid token explosion
            # Keep last 5 items (enough for immediate context)
            if len(tool_history) > 5:
                tool_history = tool_history[-5:]
                print(f"✂️ Planner: Truncated history to last 5 items")
                
            messages.extend(tool_history)
            # V9: Add Goal Reminder to prevent "Planner Blindness"
            messages.append(HumanMessage(content=f"[GOAL REMINDER]\nOriginal User Request: \"{user_input}\"\nBased on the tool results above, what is your next step to complete this goal? If the goal is complete, do NOT call any tools."))
            print(f"📜 [V8] Planner: Injected {len(tool_history)} history items + Goal Reminder")
        
        # V5.1: Log token estimate
        est_tokens = (len(system_prompt) + len(user_content)) // 4
        print(f"🧠 Planner: ~{est_tokens} tokens ({'retry' if hindsight else 'first'})")

        try:
            print("🧠 Planner: Thinking (Native Tool Use)...")
            
            # V9: Dynamic Tool Filtering (reduces token usage)
            all_tools = get_all_tools()
            tools = self._filter_tools(all_tools, intent_mode, user_input)
            llm_with_tools = self.llm.bind_tools(tools)
            
            # V9.1: Governor enforcement
            from .context_governor import get_context_governor, ContextBudgetExceeded
            governor = get_context_governor()
            messages, _, tool_history = governor.enforce(
                messages, 
                "PLANNER",
                tool_history=tool_history
            )
            
            response = llm_with_tools.invoke(messages)
            
            # PARSE NATIVE TOOL CALLS
            if response.tool_calls:
                # V10: Deduplicate and limit terminal actions
                TERMINAL_TOOLS = {
                    "play_youtube", "spotify_control", "open_app",
                    "file_open", "gmail_send_email", "calendar_create_event",
                    "tasks_create", "note_create", "set_timer", "set_reminder"
                }
                
                plan = []
                seen_terminal = set()  # Track terminal tools already added
                
                for i, call in enumerate(response.tool_calls):
                    tool_name = call["name"]
                    
                    # Skip duplicate terminal actions
                    if tool_name in TERMINAL_TOOLS:
                        if tool_name in seen_terminal:
                            print(f"⚠️ Planner: Skipping duplicate terminal action: {tool_name}")
                            continue
                        seen_terminal.add(tool_name)
                    
                    plan.append({
                        "id": len(plan) + 1,
                        "tool": tool_name,
                        "args": call["args"],
                        "tool_call_id": call["id"]
                    })
                    
                    # V10: Stop after first terminal action (one action = one tab)
                    if tool_name in TERMINAL_TOOLS:
                        print(f"🛑 Planner: Stopping plan after terminal action: {tool_name}")
                        break
                
                # Safety cap
                if len(plan) > 3:
                    print(f"⚠️ Planner: Capping plan from {len(plan)} to 3 steps")
                    plan = plan[:3]
                
                # Log usage
                _log_planner_usage(est_tokens, len(plan), is_retry=bool(hindsight))
                print(f"📋 Planner Output: {len(plan)} steps via Native API.")
                return {"plan": plan, "message": response}
            else:
                print("🧠 Planner: No tools called (Chat mode)")
                return {"plan": [], "message": response}

        except Exception as e:
            import traceback
            print(f"❌ PLANNER ERROR ❌")
            print(f"   Message: {e}")
            print(f"   Traceback:")
            traceback.print_exc()
            return {"plan": [], "error": str(e)}
