"""
Sakura V10 Response Generator
=============================
Generates final text responses with EQ layer and guardrails.

Extracted from llm.py as part of SOLID refactoring.
- Single Responsibility: Response generation only
- Handles context building, mood adaptation, and validation
"""
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from langchain_core.messages import SystemMessage, HumanMessage


# Responder guardrail: Text-only output rule
RESPONDER_NO_TOOLS_RULE = """CRITICAL RULE: You are a TEXT-ONLY responder. You CANNOT call tools.
You must ONLY return plain text responses. Never output JSON, tool schemas, or {"name": ...} patterns.
If you need a tool, respond with: "I need to use a tool for that. Let me help you differently."
IMPORTANT: If tool outputs are provided below, the action was ALREADY completed. Acknowledge it naturally (e.g., "Playing now" or "Done") - do NOT tell the user to manually do it."""


# V13: Pre-compiled validation patterns (avoid recompiling on every response)
_TOOL_LEAK_PATTERNS = [
    re.compile(r'\{\s*"name"\s*:', re.IGNORECASE),
    re.compile(r'\{\s*"tool"\s*:', re.IGNORECASE),
    re.compile(r'\{\s*"function"\s*:', re.IGNORECASE),
    re.compile(r'\{\s*"action"\s*:\s*"', re.IGNORECASE),
]

_TOOL_SPLIT_PATTERN = re.compile(r'\{\s*"(name|tool|function|action)"\s*:')

_ACTION_CLAIM_PATTERNS = [
    re.compile(r"\bi (have |just )?(sent|scheduled|created|added|updated|played|opened|deleted|saved)", re.IGNORECASE),
    re.compile(r"\b(email|event|task|note|file) (has been|was) (sent|created|scheduled|added)", re.IGNORECASE),
    re.compile(r"\bdone[.!]?\s*$", re.IGNORECASE),
    re.compile(r"\bplaying now", re.IGNORECASE),
    re.compile(r"\bsuccessfully (sent|created|scheduled|added|saved)", re.IGNORECASE),
]


@dataclass
class ResponseContext:
    """Context for generating a response."""
    user_input: str
    tool_outputs: str = ""
    history: List[Dict] = None
    graph_context: str = ""
    intent_adjustment: str = ""  # EQ layer mood adaptation
    current_mood: str = "Neutral"
    study_mode: bool = False
    data_reasoning: bool = False
    session_summary: str = ""  # V10.5 Session Memory Injection
    
    def __post_init__(self):
        if self.history is None:
            self.history = []


class ResponseGenerator:
    """
    Generates final text responses with emotional intelligence.
    
    Features:
    - EQ Layer: Adapts tone based on user mood
    - Guardrails: Prevents tool-call leakage
    - Action-claim detection: Catches false claims
    - Context building: Compact V4 format
    """
    
    def __init__(self, llm, personality: str = ""):
        """
        Args:
            llm: ReliableLLM for response generation
            personality: System personality prompt
        """
        self.llm = llm
        self.personality = personality
    
    async def agenerate(self, context: ResponseContext) -> str:
        """Async version of generate."""
        messages = self._build_messages(context)
        
        try:
            print(f"🤖 Synthesizing (Async)... ({len(messages)} messages)")
            
            # Invoke with tool_choice=none if supported
            try:
                response = await self.llm.ainvoke(messages, tool_choice="none")
            except TypeError:
                response = await self.llm.ainvoke(messages)
            
            raw_response = response.content
            
            # Validate and clean response
            final_response, had_violation = self.validate_output(raw_response)
            if had_violation:
                print("⚠️ Responder tool-call violation detected and stripped")
            
            # Check for false action claims (if no tools were used)
            if not context.tool_outputs:
                final_response = self._check_action_claim(final_response)
            
            return final_response
            
        except Exception as e:
            print(f"❌ Async Response generation error: {e}")
            return "I apologize, but I encountered an issue. Could you please try again?"

    def generate(self, context: ResponseContext) -> str:
        """
        Generate a natural response based on context.
        
        Args:
            context: ResponseContext with all necessary information
            
        Returns:
            Final response text (validated and cleaned)
        """
        messages = self._build_messages(context)
        
        try:
            print(f"🤖 Synthesizing... ({len(messages)} messages)")
            
            # Invoke with tool_choice=none if supported
            try:
                response = self.llm.invoke(messages, tool_choice="none")
            except TypeError:
                response = self.llm.invoke(messages)
            
            raw_response = response.content
            
            # Validate and clean response
            final_response, had_violation = self.validate_output(raw_response)
            if had_violation:
                print("⚠️ Responder tool-call violation detected and stripped")
            
            # Check for false action claims (if no tools were used)
            if not context.tool_outputs:
                final_response = self._check_action_claim(final_response)
            
            return final_response
            
        except Exception as e:
            print(f"❌ Response generation error: {e}")
            return "I apologize, but I encountered an issue. Could you please try again?"
    
    def generate_chat(self, user_input: str, history: List[Dict]) -> str:
        """Shorthand for simple chat responses."""
        context = ResponseContext(
            user_input=user_input,
            history=history
        )
        return self.generate(context)
    
    def _build_messages(self, context: ResponseContext) -> List:
        """Build message list for LLM invocation."""
        messages = []
        
        # 1. Build system prompt with all context blocks
        system_parts = [self.personality, RESPONDER_NO_TOOLS_RULE]
        
        # V10.5: inject Session Summary (Short-term memory)
        if context.session_summary:
            system_parts.append(f"""
[CURRENT SESSION CONTEXT]
The following is a summary of the conversation so far. USE THIS to recall recent events even if they are not in the chat history:
{context.session_summary}
""")
        
        # Data reasoning mode instruction
        if context.data_reasoning:
            system_parts.append("""
CRITICAL: The user wants your ANALYSIS/OPINION, not a summary.
- Provide your honest critique, evaluation, or perspective
- Use judgment language: "I think", "this suggests", "the issue is"
- Do NOT just repeat or summarize what the data says
""")
        
        # World Graph context
        if context.graph_context:
            system_parts.append(f"\n{context.graph_context}\n")
        
        # EQ Layer - Intent-aware response adjustment
        if context.intent_adjustment:
            system_parts.append(f"\n[USER MOOD ADAPTATION]\n{context.intent_adjustment}\n")
        
        # Study mode instructions
        if context.study_mode:
            system_parts.append("""
STUDY MODE ACTIVE:
- Focus on educational content
- Use clear explanations
- Cite sources when available
""")
        
        # Current mood and tool outputs
        system_parts.append(f"CURRENT MOOD: {context.current_mood}")
        if context.tool_outputs:
            system_parts.append(f"""
╔══════════════════════════════════════════════════════════════════╗
║  ⚡ TOOL ALREADY EXECUTED - RESULTS BELOW - YOU MUST USE THESE  ║
╚══════════════════════════════════════════════════════════════════╝
{context.tool_outputs}
╔══════════════════════════════════════════════════════════════════╗
║  END OF TOOL RESULTS - Respond using this data, don't say       ║
║  "I need a tool" - the tool already ran successfully!           ║
╚══════════════════════════════════════════════════════════════════╝
""")
        system_parts.append("Task: Respond naturally based on context.")
        
        messages.append(SystemMessage(content="\n".join(system_parts)))
        
        # 2. Compact context (last 3 messages)
        compact_context = self._build_compact_context(context.history, context.user_input)
        if compact_context:
            messages.append(SystemMessage(content=compact_context))
        
        # 3. Current user input
        messages.append(HumanMessage(content=context.user_input))
        
        return messages
    
    def _build_compact_context(self, history: List[Dict], current_input: str) -> str:
        """Build V4 compact context from history."""
        if not history:
            return ""
        
        # Take last 3 messages
        recent = history[-3:] if len(history) > 3 else history
        
        lines = ["<CONTEXT>"]
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:200]  # Truncate
            lines.append(f"{role}: {content}")
        lines.append("</CONTEXT>")
        
        return "\n".join(lines)
    
    def validate_output(self, text: str) -> Tuple[str, bool]:
        """
        Validate and clean responder output.
        
        Strips any tool-call patterns that may have leaked through.
        V13: Uses pre-compiled patterns for performance.
        
        Returns:
            Tuple of (cleaned_text, had_violation)
        """
        had_violation = False
        for pattern in _TOOL_LEAK_PATTERNS:
            if pattern.search(text):
                had_violation = True
                break
        
        if had_violation:
            print("⚠️ [GUARDRAIL] Responder attempted tool call - stripping JSON")
            # Extract text before the JSON
            clean = _TOOL_SPLIT_PATTERN.split(text)[0].strip()
            if not clean or len(clean) < 10:
                clean = "I apologize, but I encountered an issue processing that request. Could you please rephrase?"
            return clean, True
        
        return text, False
    
    def _check_action_claim(self, response: str) -> str:
        """
        Detect false action claims when no tools were executed.
        
        Uses regex heuristics to catch confident lies like
        "I sent the email" when no email was actually sent.
        V13: Uses pre-compiled patterns for performance.
        """
        response_lower = response.lower()
        
        for pattern in _ACTION_CLAIM_PATTERNS:
            if pattern.search(response_lower):
                print("⚠️ [GUARDRAIL] False action claim detected")
                return "I understand you want me to do something, but I wasn't able to take any action. Could you clarify what you'd like me to do?"
        
        return response
