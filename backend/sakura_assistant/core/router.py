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
import re

from langchain_core.messages import SystemMessage, HumanMessage


# V13: Urgency detection pattern (compiled once at module load)
_URGENT_PATTERNS = re.compile(
    r'\b(urgent(ly)?|asap|emergency|hurry|quick(ly)?|immediately|right now|as soon as possible)\b',
    re.IGNORECASE
)


# Router prompt for V10 classification with Few-Shot Examples
ROUTER_SYSTEM_PROMPT = """You are a query classifier for a personal AI assistant.

Classify the user's query into ONE of these categories:

DIRECT - Single, obvious tool action that can be executed immediately.
PLAN - Requires multiple steps, research, reasoning chains, or complex comparison.
CHAT - Pure conversation, no tools needed.

=== FEW-SHOT EXAMPLES ===

User: "Play Numb by Linkin Park"
{"classification": "DIRECT", "tool_hint": "spotify_control", "reason": "Single media action"}

User: "What is the weather in Tokyo?"
{"classification": "DIRECT", "tool_hint": "get_weather", "reason": "Single lookup"}

User: "What time is it?"
{"classification": "DIRECT", "tool_hint": "get_time", "reason": "Single lookup"}

User: "Explain quantum physics"
{"classification": "CHAT", "tool_hint": null, "reason": "Knowledge explanation, no tool"}

User: "Who is the CEO of OpenAI?"
{"classification": "PLAN", "tool_hint": "web_search", "reason": "Fact lookup"}

User: "Find a recipe for lasagna and add the ingredients to my shopping list"
{"classification": "PLAN", "tool_hint": null, "reason": "Multi-step: Search -> Add to list"}

User: "Research quantum computing and summarize the key concepts"
{"classification": "PLAN", "tool_hint": null, "reason": "Multi-step: Research -> Summarize"}

User: "Compare Python and JavaScript for web development"
{"classification": "PLAN", "tool_hint": null, "reason": "Comparison requires research on both"}

User: "Who is the president of France and what are they known for?"
{"classification": "PLAN", "tool_hint": null, "reason": "Multi-part question requiring lookup + synthesis"}

User: "What happened in the news today?"
{"classification": "PLAN", "tool_hint": null, "reason": "Requires news search + summarization"}

User: "Look up the best restaurants nearby and check their reviews"
{"classification": "PLAN", "tool_hint": null, "reason": "Multi-step: Search -> Check reviews"}

=== END EXAMPLES ===

Return JSON only:
{"classification": "DIRECT|PLAN|CHAT", "tool_hint": "tool_name or null"}
"""


class RouteResult:
    """Result of intent routing."""
    
    def __init__(self, classification: str, tool_hint: Optional[str] = None, urgency: str = "NORMAL"):
        self.classification = classification  # DIRECT, PLAN, or CHAT
        self.tool_hint = tool_hint
        self.urgency = urgency  # V13: URGENT or NORMAL
    
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
    
    async def aroute(self, query: str, context: str = "", history: List[Dict] = None) -> RouteResult:
        """Async version of route using native ainvoke."""
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
            messages = [
                SystemMessage(content=ROUTER_SYSTEM_PROMPT),
                HumanMessage(content=f"Context: {context}\n\nQuery: {query}")
            ]
            
            # Use async invoke
            response = await self.llm.ainvoke(messages)
            classification, tool_hint = self._parse_response(response.content)
            return RouteResult(classification, tool_hint, urgency)
            
        except Exception as e:
            print(f"⚠️ [Router] Async Error: {e}, defaulting to CHAT")
            return RouteResult("CHAT", None, urgency)

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
            messages = [
                SystemMessage(content=ROUTER_SYSTEM_PROMPT),
                HumanMessage(content=f"Context: {context}\n\nQuery: {query}")
            ]
            
            response = self.llm.invoke(messages)
            classification, tool_hint = self._parse_response(response.content)
            
            return RouteResult(classification, tool_hint, urgency)
            
        except Exception as e:
            print(f"⚠️ [Router] Error: {e}, defaulting to CHAT")
            return RouteResult("CHAT", None, urgency)
    
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
