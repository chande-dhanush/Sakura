"""
Sakura V10 Intent Router
========================
Routes user queries to DIRECT/PLAN/CHAT paths.

Extracted from llm.py as part of SOLID refactoring.
- Single Responsibility: Only handles query classification
- Open/Closed: New routes can be added via classification logic
"""
import json
from typing import Optional, Tuple, List, Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage


# Router prompt for V10 classification
ROUTER_SYSTEM_PROMPT = """You are a query classifier for a personal AI assistant.

Classify the user's query into ONE of these categories:

DIRECT - Single, obvious tool action that can be executed immediately.
Examples: "check email", "what's the weather", "play music", "set timer 5 min"

PLAN - Requires multiple steps, research, or complex reasoning.
Examples: "who is X and what are they known for", "compare A and B", "research topic"

CHAT - Pure conversation, no tools needed.
Examples: "hi", "thanks", "tell me a joke", "explain quantum physics"

Return JSON only:
{"classification": "DIRECT|PLAN|CHAT", "tool_hint": "tool_name or null"}
"""


class RouteResult:
    """Result of intent routing."""
    
    def __init__(self, classification: str, tool_hint: Optional[str] = None):
        self.classification = classification  # DIRECT, PLAN, or CHAT
        self.tool_hint = tool_hint
    
    @property
    def needs_tools(self) -> bool:
        return self.classification in ("DIRECT", "PLAN")
    
    @property
    def needs_planning(self) -> bool:
        return self.classification == "PLAN"


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
        # 1. Check for forced action commands (bypass LLM)
        if self._is_action_command(query):
            print(f"⚡ [Router] Action command detected, forcing DIRECT")
            tool_hint = self._guess_tool_hint(query)
            return RouteResult("DIRECT", tool_hint)
        
        # 2. LLM-based classification
        try:
            messages = [
                SystemMessage(content=ROUTER_SYSTEM_PROMPT),
                HumanMessage(content=f"Context: {context}\n\nQuery: {query}")
            ]
            
            response = self.llm.invoke(messages)
            classification, tool_hint = self._parse_response(response.content)
            
            return RouteResult(classification, tool_hint)
            
        except Exception as e:
            print(f"⚠️ [Router] Error: {e}, defaulting to CHAT")
            return RouteResult("CHAT")
    
    def _is_action_command(self, user_input: str) -> bool:
        """
        Hard heuristic to detect action commands that MUST go to planner.
        
        Prevents LLM from misclassifying obvious tool commands
        like "play it" or "search that" as CHAT.
        """
        text = user_input.lower().strip()
        
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
        
        # Tool mapping heuristics
        mappings = {
            "play": "spotify_control",
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
            "note": "note_read",
        }
        
        for keyword, tool in mappings.items():
            if keyword in text:
                return tool
        
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
            
            print(f"🧠 [Router] {classification} (hint: {tool_hint or 'none'})")
            return classification, tool_hint
            
        except json.JSONDecodeError:
            # Fallback: Try to detect old SIMPLE/COMPLEX format
            lower = response_text.lower()
            if "complex" in lower:
                return "PLAN", None
            elif "simple" in lower:
                return "CHAT", None
            else:
                print(f"⚠️ [Router] Parse failed, defaulting to CHAT")
                return "CHAT", None
