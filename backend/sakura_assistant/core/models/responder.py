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


# RESPONDER_NO_TOOLS_RULE is now imported from config.py to maintain centralization



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
    requires_facts: bool = False  # V19.6: If True and no tools, soften tone
    response_posture: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.history is None:
            self.history = []
        
        # Type validation
        if not isinstance(self.user_input, str):
            raise ValueError(f"ResponseContext.user_input must be str, got {type(self.user_input)}")
        if not isinstance(self.history, list):
            raise ValueError(f"ResponseContext.history must be list, got {type(self.history)}")
        if not isinstance(self.tool_outputs, str):
            # Coerce if possible, or fail fast
            self.tool_outputs = str(self.tool_outputs) if self.tool_outputs is not None else ""


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
    
    async def agenerate(self, context: ResponseContext, llm_override: Any = None) -> str:
        """Async version of generate."""
        self._prepare_response_posture(context)
        messages = self._build_messages(context)
        
        # Use provided override or default
        active_llm = llm_override or self.llm
        
        try:
            print(f" Synthesizing (Async)... ({len(messages)} messages)")
            
            # Invoke with tool_choice=none if supported
            try:
                response = await active_llm.ainvoke(messages, tool_choice="none")
            except TypeError:
                response = await active_llm.ainvoke(messages)
            
            raw_response = response.content
            
            # V19.6: Conditional Confidence Gating
            is_low_confidence = "[LOW_CONFIDENCE]" in context.tool_outputs
            if (context.requires_facts and not context.tool_outputs) or is_low_confidence:
                # Soften response if facts needed but missing, or if tool output was nonsense
                softener = "I'm not fully sure, but " if is_low_confidence else "I might be wrong, but "
                if not raw_response.lower().startswith(("i'm", "i might", "i am", "possibly", "maybe")):
                    raw_response = softener + raw_response[0].lower() + raw_response[1:]
            
            # Validate and clean response
            final_response, had_violation = self.validate_output(raw_response)
            if had_violation:
                print("   Responder tool-call violation detected and stripped")
            
            # V15.2: DEV ASSERTION - Catch tool_success + fallback bug
            # This should NEVER happen: tool ran successfully but responder says it can't
            if context.tool_outputs:
                fallback_phrases = [
                    "i need to use a tool",
                    "let me help you differently",
                    "i can't do that",
                    "i'm not able to",
                    "i cannot perform",
                    "i can't touch",        # V17.1
                    "i don't have access",  # V17.1
                    "i'm unable to"         # V17.1
                ]
                response_lower = final_response.lower()
                for phrase in fallback_phrases:
                    if phrase in response_lower:
                        print(f"   [DEV ASSERTION FAILED] Tool succeeded but responder used fallback!")
                        print(f"   Tool output present: {bool(context.tool_outputs)}")
                        print(f"   Fallback phrase found: '{phrase}'")
                        print(f"   Response: {final_response[:200]}")
                        # In dev mode, override with success acknowledgment
                        final_response = "Done! The action was completed successfully."
                        break
            
            # Check for false action claims (if no tools were used)
            if not context.tool_outputs:
                final_response = self._check_action_claim(final_response)
            
            # V16: Deterministic identity self-check (regex/graph, NOT LLM)
            final_response = self._identity_self_check(final_response)
            
            # V18 FIX-07: Tool result fidelity check
            if context.tool_outputs and len(context.tool_outputs) > 50:
                import re
                # Extract candidate data points: numbers with units, capitalized phrases
                data_points = re.findall(
                    r'\b\d+[ %kmKM]?\b|\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b',
                    context.tool_outputs[:500]
                )
                key_points = data_points[:5]
                
                if key_points:
                    response_lower = final_response.lower()
                    matches = sum(1 for p in key_points if str(p).lower() in response_lower)
                    
                    if matches == 0:
                        print(f"   [Fidelity] Response references none of {key_points}. Regenerating.")
                        retry_messages = self._build_messages(context, fidelity_override=True)
                        try:
                            retry_resp = await active_llm.ainvoke(retry_messages, tool_choice="none")
                        except TypeError:
                            retry_resp = await active_llm.ainvoke(retry_messages)
                        final_response, _ = self.validate_output(retry_resp.content)
                        final_response = self._identity_self_check(final_response)
            
            # V17.1: Record response in WorldGraph for reference resolution
            try:
                from ..graph.world_graph import get_world_graph
                wg = get_world_graph()
                mode = "after_tool" if context.tool_outputs else "chat"
                wg.record_response(
                    content=final_response,
                    mode=mode,
                    tool_context=context.tool_outputs[:200] if context.tool_outputs else None
                )
            except Exception as rec_err:
                print(f"   [Responder] Failed to record response (async): {rec_err}")
            
            return final_response
            
        except Exception as e:
            print(f"  Async Response generation error: {e}")
            return "I apologize, but I encountered an issue. Could you please try again?"

    def generate(self, context: ResponseContext) -> str:
        """
        Generate a natural response based on context.
        
        Args:
            context: ResponseContext with all necessary information
            
        Returns:
            Final response text (validated and cleaned)
        """
        self._prepare_response_posture(context)
        messages = self._build_messages(context)
        
        try:
            print(f" Synthesizing... ({len(messages)} messages)")
            
            # Invoke with tool_choice=none if supported
            try:
                response = self.llm.invoke(messages, tool_choice="none")
            except TypeError:
                response = self.llm.invoke(messages)
            
            raw_response = response.content

            # V19.6: Conditional Confidence Gating (Sync)
            is_low_confidence = "[LOW_CONFIDENCE]" in context.tool_outputs
            if (context.requires_facts and not context.tool_outputs) or is_low_confidence:
                softener = "I'm not fully sure, but " if is_low_confidence else "I might be wrong, but "
                if not raw_response.lower().startswith(("i'm", "i might", "i am", "possibly", "maybe")):
                    raw_response = softener + raw_response[0].lower() + raw_response[1:]
            
            # Validate and clean response
            final_response, had_violation = self.validate_output(raw_response)
            if had_violation:
                print("   Responder tool-call violation detected and stripped")
            
            # V17.1: DEV ASSERTION - Catch tool_success + fallback bug (sync path)
            if context.tool_outputs:
                fallback_phrases = [
                    "i need to use a tool",
                    "let me help you differently",
                    "i can't do that",
                    "i'm not able to",
                    "i cannot perform",
                    "i can't touch",
                    "i don't have access",
                    "i'm unable to"
                ]
                response_lower = final_response.lower()
                for phrase in fallback_phrases:
                    if phrase in response_lower:
                        print(f"   [DEV ASSERTION FAILED] Tool succeeded but responder used fallback!")
                        print(f"   Tool output present: {bool(context.tool_outputs)}")
                        print(f"   Fallback phrase found: '{phrase}'")
                        print(f"   Response: {final_response[:200]}")
                        final_response = "Done! The action was completed successfully."
                        break
            
            # Check for false action claims (if no tools were used)
            if not context.tool_outputs:
                final_response = self._check_action_claim(final_response)
            
            # V16: Deterministic identity self-check (regex/graph, NOT LLM)
            final_response = self._identity_self_check(final_response)
            
            # V18 FIX-07: Tool result fidelity check
            if context.tool_outputs and len(context.tool_outputs) > 50:
                import re
                # Extract candidate data points: numbers with units, capitalized phrases
                data_points = re.findall(
                    r'\b\d+[ %kmKM]?\b|\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b',
                    context.tool_outputs[:500]
                )
                key_points = data_points[:5]
                
                if key_points:
                    response_lower = final_response.lower()
                    matches = sum(1 for p in key_points if str(p).lower() in response_lower)
                    
                    if matches == 0:
                        print(f"   [Fidelity] Response references none of {key_points}. Regenerating.")
                        retry_messages = self._build_messages(context, fidelity_override=True)
                        try:
                            retry_resp = self.llm.invoke(retry_messages, tool_choice="none")
                        except TypeError:
                            retry_resp = self.llm.invoke(retry_messages)
                        final_response, _ = self.validate_output(retry_resp.content)
                        final_response = self._identity_self_check(final_response)
            
            # V17.1: Record response in WorldGraph for reference resolution
            try:
                from ..graph.world_graph import get_world_graph
                wg = get_world_graph()
                mode = "after_tool" if context.tool_outputs else "chat"
                wg.record_response(
                    content=final_response,
                    mode=mode,
                    tool_context=context.tool_outputs[:200] if context.tool_outputs else None
                )
            except Exception as rec_err:
                print(f"   [Responder] Failed to record response: {rec_err}")
            
            return final_response
            
        except Exception as e:
            print(f"  Response generation error: {e}")
            return "I apologize, but I encountered an issue. Could you please try again?"
    
    def generate_chat(self, user_input: str, history: List[Dict]) -> str:
        """Shorthand for simple chat responses."""
        context = ResponseContext(
            user_input=user_input,
            history=history
        )
        return self.generate(context)
    
    def _build_messages(self, context: ResponseContext, fidelity_override: bool = False) -> List:
        """Build message list for LLM invocation."""
        messages = []
        
        # V18.2: Import missing guardrails from config
        from ...config import RESPONDER_GUARDRAIL_PROMPT, TOOL_BEHAVIOR_RULES, RESPONDER_NO_TOOLS_RULE
        
        # 1. Build system prompt with all context blocks
        system_parts = [
            self.personality, 
            TOOL_BEHAVIOR_RULES,
            RESPONDER_NO_TOOLS_RULE,
            RESPONDER_GUARDRAIL_PROMPT
        ]
        
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

        # Behavioral restraint: this affects pacing, not facts or tool fidelity.
        posture = context.response_posture or self._infer_response_posture(context)
        system_parts.append(f"""
[CONVERSATIONAL RESTRAINT]
Posture: {posture["mode"]}
Budget: {posture["max_sentences"]} sentence(s) unless the user explicitly asks for more.
Reason: {posture["reason"]}
Warmth: {posture.get("warmth", "normal")}
Rules:
- Answer the actual ask first.
- Do not over-explain, recap the system, or over-reference memory.
- Leave breathing room; one useful sentence is allowed.
- Brief does not mean cold; preserve warmth when the turn is emotionally meaningful.
- Ask at most one clarification question, and only when it changes the answer.
""")
        
        # Current mood and tool outputs
        system_parts.append(f"CURRENT MOOD: {context.current_mood}")
        if context.tool_outputs:
            if fidelity_override:
                system_parts.append("CRITICAL: Your previous response IGNORED the tool data below. You MUST reference these specific results in your answer:\n")
            
            system_parts.append(f"""
                                                                    
     TOOL ALREADY EXECUTED - RESULTS BELOW - YOU MUST USE THESE   
                                                                    
{context.tool_outputs}
                                                                    
   END OF TOOL RESULTS - Respond using this data, don't say        
   "I need a tool" - the tool already ran successfully!            
                                                                    
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

    def _prepare_response_posture(self, context: ResponseContext) -> Dict[str, Any]:
        """Infer and trace the conversational posture once per response."""
        if context.response_posture:
            return context.response_posture

        posture = self._infer_response_posture(context)
        context.response_posture = posture

        try:
            from ..infrastructure.behavioral_trace import get_behavioral_trace, InfluenceType
            follow_up_allowed = posture["mode"] in {"expanded", "balanced"}
            get_behavioral_trace().record(
                InfluenceType.RESTRAINT,
                "ResponseGenerator",
                f"Selected {posture['mode']} posture with {posture['max_sentences']} sentence budget",
                {
                    "reason": posture["reason"],
                    "has_tool_outputs": bool(context.tool_outputs),
                    "study_mode": context.study_mode,
                    "data_reasoning": context.data_reasoning,
                    "follow_up_allowed": follow_up_allowed,
                    "warmth": posture.get("warmth", "normal"),
                    "voice": posture.get("voice", "normal"),
                    "cadence": posture.get("cadence", {}),
                }
            )
            if not follow_up_allowed:
                get_behavioral_trace().record(
                    InfluenceType.RESTRAINT,
                    "ResponseGenerator",
                    "Skipped follow-up pressure to preserve breathing room",
                    {"posture": posture["mode"]},
                )
        except Exception:
            pass

        return posture

    def _infer_response_posture(self, context: ResponseContext) -> Dict[str, Any]:
        """Small deterministic policy for conversational pacing and restraint."""
        text = context.user_input.strip()
        lowered = text.lower()
        words = re.findall(r"\w+", lowered)
        word_count = len(words)

        asks_for_depth = any(
            phrase in lowered
            for phrase in (
                "explain",
                "walk me through",
                "deep dive",
                "in detail",
                "thorough",
                "why",
                "how does",
                "compare",
                "analyze",
                "analyse",
            )
        )
        simple_ack = lowered in {"ok", "okay", "k", "cool", "nice", "got it", "lol", "haha"}
        gratitude_ack = lowered in {"thanks", "thank you", "ty"} or lowered.startswith(("thanks ", "thank you "))
        emotional_signal = any(
            phrase in lowered
            for phrase in (
                "stuck",
                "frustrated",
                "annoyed",
                "tired",
                "overwhelmed",
                "panic",
                "broken",
                "not working",
                "why won't",
                "i hate",
                "rough day",
                "bad day",
                "sad",
                "lonely",
                "scared",
                "anxious",
                "needed that",
            )
        )
        last_assistant_long = any(
            msg.get("role") in {"assistant", "ai"} and len(msg.get("content", "")) > 600
            for msg in context.history[-2:]
        )

        if emotional_signal:
            return {
                "mode": "grounded",
                "max_sentences": 2,
                "reason": "User shows friction or fatigue; be steady and brief before adding more.",
                "warmth": "steady",
                "voice": "soft",
                "cadence": {"pace": "slower", "pause_ms": 180},
            }

        if gratitude_ack:
            return {
                "mode": "warm_quiet",
                "max_sentences": 1,
                "reason": "User gave a small warm acknowledgement; answer lightly without withdrawing.",
                "warmth": "warm",
                "voice": "micro",
                "cadence": {"pace": "soft", "pause_ms": 120},
            }

        if simple_ack:
            return {
                "mode": "quiet",
                "max_sentences": 1,
                "reason": "User gave a small acknowledgement; leave space instead of filling it.",
                "warmth": "light",
                "voice": "micro_optional",
                "cadence": {"pace": "light", "pause_ms": 80},
            }

        if context.study_mode or context.data_reasoning or asks_for_depth:
            return {
                "mode": "expanded",
                "max_sentences": 5,
                "reason": "User is asking for explanation, analysis, or learning support.",
                "warmth": "engaged",
                "voice": "normal",
                "cadence": {"pace": "normal", "pause_ms": 80},
            }

        if context.tool_outputs:
            return {
                "mode": "delivery",
                "max_sentences": 2,
                "reason": "Tool results are present; deliver the outcome without procedural chatter.",
                "warmth": "clear",
                "voice": "normal",
                "cadence": {"pace": "brisk", "pause_ms": 40},
            }

        if last_assistant_long:
            return {
                "mode": "compressed",
                "max_sentences": 2,
                "reason": "Recent assistant turn was long; tighten cadence for conversational balance.",
                "warmth": "steady",
                "voice": "normal",
                "cadence": {"pace": "measured", "pause_ms": 100},
            }

        if word_count <= 12:
            return {
                "mode": "light",
                "max_sentences": 2,
                "reason": "User gave a short turn; respond at matching weight.",
                "warmth": "present",
                "voice": "normal",
                "cadence": {"pace": "light", "pause_ms": 80},
            }

        return {
            "mode": "balanced",
            "max_sentences": 3,
            "reason": "Default conversational rhythm.",
            "warmth": "normal",
            "voice": "normal",
            "cadence": {"pace": "normal", "pause_ms": 80},
        }
    
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
            print("   [GUARDRAIL] Responder attempted tool call - stripping JSON")
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
                print("   [GUARDRAIL] False action claim detected")
                return "I understand you want me to do something, but I wasn't able to take any action. Could you clarify what you'd like me to do?"
        
        return response
    
    def _identity_self_check(self, response: str) -> str:
        """
        V16: Deterministic identity validation (NO LLM, pure regex/lookup).
        
        Catches hallucinated identity claims by checking against IdentityManager.
        This is FAST (< 1ms) because it uses regex, not LLM.
        
        Returns:
            Original response if valid, or corrected response if violation found.
        """
        try:
            from ..graph.identity import get_identity_manager
            im = get_identity_manager()
            
            is_valid, violation = im.check_claim(response)
            
            if not is_valid:
                print(f"  [V16 Self-Check] Identity violation: {violation}")
                # V16.1: Seamless Correction (User Feedback)
                # Instead of appending a "Note:", return a clean, truthful response.
                # We use the IdentityManager's safe summary.
                
                safe_identity = im.get_summary()
                correction = f"Actually, just to be clear: {safe_identity} I might have gotten confused for a second there!"
                
                # If the response was very short, just replace it.
                if len(response) < 50:
                    return correction
                    
                # Otherwise, append it more naturally.
                return f"{response}\n\n(Correction: {safe_identity})"
            
            return response
            
        except Exception as e:
            # Self-check should never crash the response
            print(f"   [V16 Self-Check] Error (non-fatal): {e}")
            return response
