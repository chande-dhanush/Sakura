"""
Sakura V5.1: Intent Classifier

Rule-based intent classification with three execution modes:
- REASONING_ONLY: Opinion/analysis without data fetch
- DATA_REASONING: Fetch data → Apply reasoning
- ACTION: Execute tools (current V5 behavior)

Priority Order:
1. If reasoning + fetch keywords → DATA_REASONING
2. If reasoning keywords only → REASONING_ONLY  
3. If ACTION keyword is first verb → ACTION
4. Default → ACTION (preserve current behavior)

This is pure heuristic (0 LLM calls), runs before routing.
"""
from enum import Enum
from typing import Tuple, Dict
import re

# V5.1: Cache compiled regex patterns for performance
_KEYWORD_PATTERNS: Dict[str, re.Pattern] = {}


class IntentMode(Enum):
    """Three execution modes for the pipeline."""
    REASONING_ONLY = "reasoning"        # Opinion without data fetch
    DATA_REASONING = "data_then_reason" # Fetch → Think → Opinion
    ACTION = "action"                   # Execute tools directly


# Keywords indicating user wants reasoning/opinion/judgment
REASONING_KEYWORDS = {
    # Explicit opinion requests
    "opinion", "opinions", "thoughts", "think", "honest", "honestly",
    # Critique/evaluation
    "critique", "review", "evaluate", "evaluation", "analyze", "analysis",
    # Perspective/judgment
    "perspective", "judgment", "assess", "assessment", "feedback",
    # Implicit reasoning
    "what do you", "how do you feel", "your take", "your view",
    "do you think", "would you say", "tell me what you",
    # Instruction/explanation requests (user wants synthesized answer, not raw data)
    "tell me how", "explain how", "show me how", "how do i", "how to",
    # Summarization/synthesis (user wants condensed understanding, not dump)
    "summarize", "summary", "summarise", "break down", "explain", "in simple terms",
}

# Keywords indicating data should be fetched first
FETCH_KEYWORDS = {
    # Search/lookup
    "search", "look up", "lookup", "look for", "find",
    # Check/read
    "check", "scrape", "fetch", "read", "get",
    # Website/document specific
    "look at", "see", "scan", "browse", "visit",
    # Implicit fetch
    "my website", "my site", "my portfolio", "the news", "this article",
    # URL patterns (link analysis = implicit fetch)
    "http://", "https://", "www.", ".com/", ".org/", ".io/", ".dev/",
    "this link", "this url", "this page",
}

# Keywords indicating direct action (imperative verbs)
ACTION_KEYWORDS = {
    # Media control
    "play", "pause", "stop", "resume", "skip", "next", "previous",
    # Communication
    "send", "email", "forward", "reply",
    # System actions
    "open", "launch", "start", "close",
    # Data actions
    "create", "save", "delete", "remove", "add", "update", "set",
    # Schedule
    "schedule", "reschedule", "cancel", "remind",
    # PA Tools
    "weather", "timer", "alarm", "volume", "mute", "unmute",
    "convert", "calculate", "define", "news", "location", "battery",
}


def _get_first_verb(text: str) -> str:
    """Extract the first potential verb from the input."""
    # Remove common prefixes
    text = re.sub(r'^(can you|could you|please|would you|will you)\s+', '', text.lower())
    
    # Get first word that could be a verb
    words = text.split()
    if words:
        return words[0]
    return ""


def _has_keywords(text: str, keywords: set) -> bool:
    """Check if text contains any keywords from the set (word-boundary safe, cached)."""
    text_lower = text.lower()
    for keyword in keywords:
        # Use word boundaries to avoid false positives like "thinking" matching "think"
        # For multi-word phrases, just check substring (they're specific enough)
        if ' ' in keyword or '/' in keyword or '.' in keyword:
            # Multi-word or URL pattern: simple substring match
            if keyword in text_lower:
                return True
        else:
            # Single word: require word boundary with cached pattern
            if keyword not in _KEYWORD_PATTERNS:
                _KEYWORD_PATTERNS[keyword] = re.compile(r'\b' + re.escape(keyword) + r'\b')
            if _KEYWORD_PATTERNS[keyword].search(text_lower):
                return True
    return False


def classify_intent(user_input: str) -> Tuple[IntentMode, str]:
    """
    Classify user intent into one of three execution modes.
    
    Returns:
        Tuple of (IntentMode, reason string for logging)
    
    Priority Order:
    1. reasoning + fetch → DATA_REASONING (user wants opinion on external data)
    2. reasoning only → REASONING_ONLY (pure opinion request)
    3. action as first verb → ACTION (imperative command)
    4. default → ACTION (preserve existing behavior)
    """
    has_reasoning = _has_keywords(user_input, REASONING_KEYWORDS)
    has_fetch = _has_keywords(user_input, FETCH_KEYWORDS)
    has_action = _has_keywords(user_input, ACTION_KEYWORDS)
    first_verb = _get_first_verb(user_input)
    
    # V9: Multi-clause detection (Router Bias towards COMPLEX)
    # Only trigger if we have action + conjunction + action pattern
    # "Check weather AND email boss" -> COMPLEX
    # "Tell me about Tom and Jerry" -> NOT triggered (no second action)
    def has_multi_action(text: str) -> bool:
        lower = text.lower()
        conjunctions = [" and ", " then ", ", then ", " after that "]
        for conj in conjunctions:
            if conj in lower:
                parts = lower.split(conj, 1)
                # Check if both parts have action keywords
                left_action = any(kw in parts[0] for kw in ACTION_KEYWORDS)
                right_action = any(kw in parts[1] for kw in ACTION_KEYWORDS) if len(parts) > 1 else False
                if left_action and right_action:
                    return True
        return False
    
    if has_multi_action(user_input):
        return IntentMode.ACTION, "multi-action clause (bias to COMPLEX)"
    
    # Priority 1: Reasoning + Fetch = DATA_REASONING
    # "Check my website and give me your honest opinion"
    if has_reasoning and has_fetch:
        return IntentMode.DATA_REASONING, "reasoning + fetch detected"
    
    # Priority 2: Pure Reasoning = REASONING_ONLY
    # "What's your honest opinion about AI?"
    if has_reasoning and not has_action:
        return IntentMode.REASONING_ONLY, "pure reasoning request"
    
    # Priority 3: Action as first verb = ACTION
    # "Play training AMV on YouTube"
    if first_verb in ACTION_KEYWORDS:
        return IntentMode.ACTION, f"imperative action: {first_verb}"
    
    # Priority 4: Has action keyword anywhere = ACTION
    if has_action:
        return IntentMode.ACTION, "action keyword detected"
    
    # Default: ACTION (preserve V5 behavior for ambiguous queries)
    return IntentMode.ACTION, "default (no clear intent)"


# Judgment signal patterns for verifier (not explicit phrases)
JUDGMENT_SIGNALS = {
    # Comparative language
    "better", "worse", "prefer", "vs", "versus", "compared to", "rather than",
    # Evaluative language
    "pros", "cons", "advantage", "disadvantage", "strength", "weakness",
    # Decision language
    "recommend", "suggest", "would choose", "should", "shouldn't",
    # Critique language  
    "issue", "problem", "concern", "impressive", "lacking", "needs",
    # Confidence markers
    "clearly", "obviously", "definitely", "essentially", "fundamentally",
    # Analytical markers
    "because", "since", "therefore", "indicates", "suggests", "shows that",
}


def has_judgment_signals(text: str) -> bool:
    """
    Check if response contains judgment/reasoning signals.
    
    Used by Verifier for DATA_REASONING mode.
    Returns True if response shows actual reasoning was applied.
    """
    text_lower = text.lower()
    
    # Check for any judgment signal
    for signal in JUDGMENT_SIGNALS:
        if signal in text_lower:
            return True
    
    # Also check for multi-sentence responses (indicates analysis)
    # Require 3+ substantive sentences to avoid false positives on summaries
    sentence_count = len([s for s in text.split('.') if len(s.strip()) > 20])
    if sentence_count >= 3:
        return True
    
    return False
