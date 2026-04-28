"""
Sakura V10 Intent Router
========================
Routes user queries to DIRECT/PLAN/CHAT paths.

Extracted from llm.py as part of SOLID refactoring.
- Single Responsibility: Only handles query classification
- Open/Closed: New routes can be added via classification logic
"""
import json
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
import re

from langchain_core.messages import SystemMessage, HumanMessage


# V13: Urgency detection pattern (compiled once at module load)
_URGENT_PATTERNS = re.compile(
    r'\b(urgent(ly)?|asap|emergency|hurry|quick(ly)?|immediately|right now|as soon as possible)\b',
    re.IGNORECASE
)


from ...config import ROUTER_SYSTEM_PROMPT



class RouteResult:
    """Result of intent routing."""
    __slots__ = ["classification", "tool_hint", "urgency"]
    
    def __init__(self, classification: str, tool_hint: Optional[str] = None, urgency: str = "NORMAL"):
        # Validate classification
        valid_modes = {"DIRECT", "PLAN", "CHAT", "RESEARCH"}
        if classification not in valid_modes:
            # V19 Contract Hardening: Default to PLAN if malformed string provided
            classification = "PLAN"
            
        self.classification = classification  # DIRECT, PLAN, CHAT, or RESEARCH
        self.tool_hint = tool_hint
        self.urgency = urgency if urgency in ("URGENT", "NORMAL") else "NORMAL"
    
    @property
    def needs_tools(self) -> bool:
        return self.classification in ("DIRECT", "PLAN")
    
    @property
    def needs_planning(self) -> bool:
        return self.classification == "PLAN"
    
    @property
    def is_urgent(self) -> bool:
        return self.urgency == "URGENT"


def get_urgency(query: str) -> str:
    """
    V13: Detect urgency level using pattern matching.
    
    Returns:
        "URGENT" or "NORMAL"
    """
    return "URGENT" if _URGENT_PATTERNS.search(query) else "NORMAL"


class IntentRouter:
    """
    Routes user queries to appropriate processing paths.
    
    V10 Architecture:
    - DIRECT: Single-tool fast lane (skip Planner)
    - PLAN: Multi-step ReAct loop
    - CHAT: Pure conversation responder
    """
    
    def __init__(self, llm):
        """
        Args:
            llm: ReliableLLM instance for routing decisions
        """
        self.llm = llm
    
    async def aroute(self, query: str, context: str = "", history: List[Dict] = None, llm_override: Any = None) -> RouteResult:
        """Async version of route using native ainvoke."""
        # Use provided override or default
        active_llm = llm_override or self.llm
        # V13: Detect urgency first (fast, no LLM)
        urgency = get_urgency(query)
        if urgency == "URGENT":
            print(f"⚡ [Router] URGENT query detected")
        
        # 1. Action command check (CPU bound, fast enough to keep sync logic)
        if self._is_action_command(query):
            print(f"⚡ [Router] Action command detected (Async), forcing DIRECT")
            tool_hint = self._guess_tool_hint(query)
            return RouteResult("DIRECT", tool_hint, urgency)
            
        # 2. LLM classification
        try:
            # V15.2: Inject current datetime for temporal grounding
            current_dt = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
            prompt = ROUTER_SYSTEM_PROMPT.format(current_datetime=current_dt)
            
            # V18.4 BUG-03: Slice history to last 3 turns
            recent_history = ""
            if history:
                sliced = history[-3:]
                recent_history = "\n".join([f"{m.get('role', 'user').upper()}: {m.get('content', '')[:100]}" for m in sliced])
                
            messages = [
                SystemMessage(content=prompt),
                HumanMessage(content=f"History:\n{recent_history}\n\nContext: {context}\n\nQuery: {query}")
            ]
            
            # Use async invoke
            response = await active_llm.ainvoke(messages)
            classification, tool_hint = self._parse_response(response.content)
            
            # VERIFICATION-05: Music Force PLAN for references
            music_tools = ["spotify_control", "play_youtube", "youtube_control"]
            if classification == "DIRECT" and tool_hint in music_tools:
                triggers = ["my ", "it", "that", "the one", "favourite", "fav ", "last ", "same "]
                if any(t in query.lower() for t in triggers):
                    print(f"🔄 [Router] Reference detected in music query, forcing PLAN")
                    classification = "PLAN"

            # V17.2: Apply safety checks to prevent Tavily Trap
            route_result = RouteResult(classification, tool_hint, urgency)
            return self._apply_safety_checks(query, route_result)
            
        except Exception as e:
            # V18 FIX-01: Default to PLAN (not CHAT) so tools are still available
            print(f"⚠️ [Router] Async Error: {e}, defaulting to PLAN (safer than CHAT)")
            return RouteResult("PLAN", "web_search", urgency)

    def route(self, query: str, context: str = "", history: List[Dict] = None) -> RouteResult:
        """
        Classify query and determine processing path.
        
        Args:
            query: User's input text
            context: Optional memory/graph context
            history: Optional conversation history
            
        Returns:
            RouteResult with classification and optional tool hint
        """
        # V13: Detect urgency first (fast, no LLM)
        urgency = get_urgency(query)
        
        # 1. Check for forced action commands (bypass LLM)
        if self._is_action_command(query):
            print(f"⚡ [Router] Action command detected, forcing DIRECT")
            tool_hint = self._guess_tool_hint(query)
            return RouteResult("DIRECT", tool_hint, urgency)
        
        # 2. LLM-based classification
        try:
            # V15.2: Inject current datetime for temporal grounding
            current_dt = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
            prompt = ROUTER_SYSTEM_PROMPT.format(current_datetime=current_dt)
            
            # V18.4 BUG-03: Slice history to last 3 turns
            recent_history = ""
            if history:
                sliced = history[-3:]
                recent_history = "\n".join([f"{m.get('role', 'user').upper()}: {m.get('content', '')[:100]}" for m in sliced])

            messages = [
                SystemMessage(content=prompt),
                HumanMessage(content=f"History:\n{recent_history}\n\nContext: {context}\n\nQuery: {query}")
            ]
            
            # LLM classification
            response = self.llm.invoke(messages)
            classification, tool_hint = self._parse_response(response.content)
            
            # VERIFICATION-05: Music Force PLAN for references
            music_tools = ["spotify_control", "play_youtube", "youtube_control"]
            if classification == "DIRECT" and tool_hint in music_tools:
                triggers = ["my ", "it", "that", "the one", "favourite", "fav ", "last ", "same "]
                if any(t in query.lower() for t in triggers):
                    classification = "PLAN"
                    
            route_result = RouteResult(classification, tool_hint, urgency)
            return self._apply_safety_checks(query, route_result)
            
        except Exception as e:
            # V18 FIX-01: Default to PLAN (not CHAT) so tools are still available
            print(f"⚠️ [Router] Error: {e}, defaulting to PLAN (safer than CHAT)")
            return RouteResult("PLAN", "web_search", urgency)
    
    def _is_action_command(self, user_input: str) -> bool:
        """
        Hard heuristic to detect action commands that MUST go to planner.
        
        Prevents LLM from misclassifying obvious tool commands
        like "play it" or "search that" as CHAT.
        """
        text = user_input.lower().strip()
        
        # V17 Fix: Don't shortcut complex chains - let Planner handle them
        # V17.1 Fix: Relax comma check to catch "cmd1, cmd2" (count=1)
        is_complex = " and " in text or " then " in text or "," in text
        if is_complex:
            return False
            
        # V18.4 Fix: Don't shortcut queries with reference pronouns/possessives
        # These MUST go to LLM -> PLAN for memory resolution
        triggers = [" it", " that", " the one", "favourite", "fav ", "last ", "my "]
        if any(t in text for t in triggers) or text.endswith(" it") or text.endswith(" that"):
            return False
        
        # Action verbs that ALWAYS need tools
        action_verbs = [
            "play", "queue", "pause", "stop", "skip", "resume",  # Music
            "open", "launch", "start", "run",                    # Apps
            "search", "find", "look up", "google",               # Search
            "send", "message", "email", "text", "call",          # Communication
            "remind", "reminder", "set alarm", "timer",          # Reminders
            "create", "add", "make", "delete", "remove",         # CRUD
            "download", "upload", "save", "export",              # Files
            "turn on", "turn off", "enable", "disable",          # System
        ]
        
        words = text.split()
        if not words:
            return False
        
        first_word = words[0]
        
        # Direct match on first word
        for verb in action_verbs:
            if first_word == verb or first_word == verb.split()[0]:
                return True
        
        # Check multi-word verbs at start
        for verb in action_verbs:
            if text.startswith(verb):
                return True
        
        return False
    
    def _guess_tool_hint(self, query: str) -> Optional[str]:
        """Guess which tool an action command needs."""
        text = query.lower()
        
        # V17.4: Priority-based platform detection (check BEFORE generic mappings)
        # YouTube takes precedence over Spotify when explicitly mentioned
        if "youtube" in text:
            if any(verb in text for verb in ["play", "watch", "open", "search"]):
                return "play_youtube"
        
        # Spotify detection (explicit mention OR generic play without platform)
        if "spotify" in text:
            return "spotify_control"
        
        # Tool mapping heuristics (fallback for commands without explicit platform)
        mappings = {
            "play": "spotify_control",  # Default media player
            "queue": "spotify_control",
            "pause": "spotify_control",
            "email": "gmail_read_email",
            "weather": "get_weather",
            "timer": "set_timer",
            "remind": "set_reminder",
            "search": "web_search",
            "open": "open_app",
            "screenshot": "read_screen",
            "clipboard": "clipboard_read",
            "calendar": "calendar_get_events",
            # V17.1: Note mapping removed - handled by verb analysis below
        }
        
        for keyword, tool in mappings.items():
            if keyword in text:
                return tool
        
        # V17.1: Note verb analysis (priority: destructive -> additive -> read)
        if "note" in text:
            if any(v in text for v in ["edit", "update", "modify", "overwrite", "change", "fix", "rewrite"]):
                return "note_overwrite"
            elif any(v in text for v in ["add to", "append", "insert", "put in", "include"]):
                return "note_append"
            elif any(v in text for v in ["create", "make", "new", "write"]):
                return "note_create"
            return "note_read"
        
        return None
    
    def _parse_response(self, response_text: str) -> Tuple[str, Optional[str]]:
        """
        Parse Router LLM response.
        
        Returns:
            Tuple of (classification, tool_hint)
        """
        try:
            # Clean potential markdown wrapping
            clean = response_text.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].split("```")[0].strip()
            
            data = json.loads(clean)
            classification = data.get("classification", "CHAT").upper()
            tool_hint = data.get("tool_hint")
            
            # Validate classification
            if classification not in ("DIRECT", "PLAN", "CHAT"):
                classification = "CHAT"
            
            print(f" [Router] {classification} (hint: {tool_hint or 'none'})")
            return classification, tool_hint
            
        except json.JSONDecodeError:
            # Fallback: Try to detect old SIMPLE/COMPLEX format
            lower = response_text.lower()
            if "complex" in lower:
                return "PLAN", None
            elif "simple" in lower:
                return "CHAT", None
            else:
                # V18 FIX-01: Default to PLAN (not CHAT) — a redundant tool call
                # is always less harmful than a hallucinated text answer
                print(f"⚠️ [Router] Parse failed, defaulting to PLAN (safer than CHAT)")
                return "PLAN", None

    def _apply_safety_checks(self, query: str, decision: RouteResult) -> RouteResult:
        """
        V17.2: Safety checks to prevent misclassification.
        
        Rules:
        1. Greetings MUST be CHAT, never DIRECT/PLAN
        2. DIRECT without hint is suspicious → force CHAT
        3. PLAN without hint defaults to CHAT (prevents Tavily Trap)
        """
        query_lower = query.lower().strip()
        
        # Check 1: Explicit greeting patterns
        GREETING_PATTERNS = [
            "hi", "hello", "hey", "good morning", "good evening",
            "what's up", "how are you", "how are you doing",
            "yo", "sup", "greetings", "hi there", "hey there"
        ]
        
        # If query starts with greeting or is just a greeting
        is_greeting = any(
            query_lower.startswith(g) or query_lower == g 
            for g in GREETING_PATTERNS
        )
        
        if is_greeting:
            if decision.classification != "CHAT":
                print(f"⚠️ [Router Safety] Greeting misclassified as {decision.classification} → forcing CHAT: {query}")
                decision.classification = "CHAT"
                decision.tool_hint = None
            return decision
        
        # Check 2: DIRECT without hint is suspicious
        if decision.classification == "DIRECT" and not decision.tool_hint:
            print(f"⚠️ [Router Safety] DIRECT without hint → forcing CHAT: {query}")
            decision.classification = "CHAT"
            return decision
        
        # Check 3: PLAN without hint might trigger Tavily Trap
        if decision.classification == "PLAN" and not decision.tool_hint:
            # Allow PLAN if query is clearly complex or a factual/tool-requiring query
            # V18: Expanded from 6 to 26 indicators to prevent over-demotion
            complex_indicators = [
                # Original V17.2 indicators
                "and then", "after that", "first", "also", "calculate", "search",
                # Question words (factual queries NEED tools)
                "who", "what", "when", "where", "how", "why",
                # Research/lookup verbs
                "tell me", "explain", "define", "describe", "compare",
                "find", "look up", "research",
                # Common tool triggers
                "weather", "news", "email", "calendar", "play", "open", "remind",
            ]
            if not any(ind in query_lower for ind in complex_indicators):
                print(f"⚠️ [Router Safety] PLAN without hint on simple query → forcing CHAT: {query}")
                decision.classification = "CHAT"
        
        return decision
