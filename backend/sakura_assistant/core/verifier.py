"""
Sakura V5: Verifier - Binary Plan Outcome Evaluation

Purpose: Quick truth-check of tool execution results.
Model: Uses intent_llm (Llama 3.3 70B via ReliableLLM with Gemini failover)
Output: PASS/FAIL with ≤12 word reason

V5.1: Also provides judgment signal verification for DATA_REASONING mode.
"""
import json
import re
from dataclasses import dataclass
from typing import Optional
from langchain_core.messages import SystemMessage, HumanMessage


@dataclass
class VerifierVerdict:
    """Structured result from Verifier evaluation."""
    passed: bool
    reason: str  # ≤12 words
    raw_response: Optional[str] = None
    
    @property
    def is_pass(self) -> bool:
        return self.passed
    
    @property
    def is_fail(self) -> bool:
        return not self.passed


# V5.1: Import prompt from centralized config
from ..config import VERIFIER_SYSTEM_PROMPT


class Verifier:
    """
    V5 Verifier: Binary outcome evaluation.
    
    - Uses intent_llm (70B with ReliableLLM wrapper)
    - Checks semantic correctness, not just execution success
    - Returns structured VerifierVerdict
    """
    
    def __init__(self, llm):
        """
        Initialize with a ReliableLLM instance.
        
        Args:
            llm: ReliableLLM wrapping intent_llm (Llama 3.3 70B)
        """
        self.llm = llm
    
    def evaluate(self, user_input: str, plan: dict, tool_outputs: str, state) -> VerifierVerdict:
        """
        Evaluate plan execution outcome.
        
        V5.1 Hardening: Runs cheap heuristics FIRST to catch obvious failures
        without burning an LLM call.
        
        Args:
            user_input: Original user request
            plan: Executed plan dict
            tool_outputs: String of tool execution results
            state: AgentState (will record LLM call)
        
        Returns:
            VerifierVerdict with passed/reason
        """
        # V5.1: Pre-LLM heuristic checks (no LLM call spent)
        # These are DEFENSIVE ONLY: errors, empty output, weak language
        heuristic_verdict = self._pre_llm_heuristics(tool_outputs, plan)
        if heuristic_verdict is not None:
            print(f"⚡ [V5.1] Heuristic FAIL: {heuristic_verdict.reason}")
            return heuristic_verdict
        
        # V5.1 Test-Phase: Entity scan DISABLED (semantic, not defensive)
        # Uncomment only if false positives are rare in production
        # entity_verdict = self._key_fact_scan(user_input, tool_outputs)
        # if entity_verdict is not None:
        #     print(f"⚡ [V5.1] Entity FAIL: {entity_verdict.reason}")
        #     return entity_verdict
        
        # Record this as an LLM call (raises RateLimitExceeded if budget exhausted)
        state.record_llm_call("verifying")
        
        # Build minimal context for evaluation
        plan_summary = self._summarize_plan(plan)
        
        messages = [
            SystemMessage(content=VERIFIER_SYSTEM_PROMPT),
            HumanMessage(content=f"User: {user_input}\nPlan: {plan_summary}\nResult:\n{tool_outputs[:1000]}")  # Cap result length
        ]
        
        # V9.1: Governor enforcement
        from .context_governor import get_context_governor, ContextBudgetExceeded
        governor = get_context_governor()
        try:
            messages, _, _ = governor.enforce(messages, "VERIFIER")
        except ContextBudgetExceeded:
            # Verifier over budget - default to PASS (never block critical path)
            print(f"⚠️ [Governor] Verifier context over budget - defaulting to PASS")
            return VerifierVerdict(passed=True, reason="Context too large for verification")
        
        try:
            response = self.llm.invoke(messages, timeout=15)  # Timeout for verifier call
            return self._parse_verdict(response.content)
        except Exception as e:
            # On verifier failure, default to PASS (don't block on verifier errors)
            print(f"⚠️ Verifier error: {e} - defaulting to PASS")
            return VerifierVerdict(passed=True, reason="Verifier unavailable", raw_response=str(e))
    
    def _pre_llm_heuristics(self, tool_outputs: str, plan: dict) -> Optional[VerifierVerdict]:
        """
        V9.2 Hardening: Cheap heuristic checks before LLM call.
        
        Returns VerifierVerdict(passed=False) on obvious failures.
        Returns None if LLM evaluation is needed.
        
        V9.2 FIX: "no results" and "not found" are VALID for list operations.
        """
        # Skip if no plan steps (nothing to verify)
        steps = plan.get("plan", [])
        if not steps:
            return None
        
        output_lower = tool_outputs.lower() if tool_outputs else ""
        executed_tools = {s.get("tool") for s in steps}
        
        # ═══ Classify tool types ═══
        content_tools = {"web_search", "fetch_document_context", "file_read", 
                         "web_scrape", "read_screen", "define_word", "get_news"}
        
        # V9.2 FIX: These tools can return "no results" and that's VALID
        list_tools = {"gmail_read_email", "calendar_get_events", "tasks_list", 
                      "note_list", "list_uploaded_documents"}
        
        expects_content = bool(executed_tools & content_tools)
        is_list_operation = bool(executed_tools & list_tools)
        
        # 1. Empty or near-empty output when content expected (NOT list ops)
        if expects_content and not is_list_operation and len(tool_outputs.strip()) < 20:
            return VerifierVerdict(passed=False, reason="Empty result when content expected")
        
        # 2. V9.2: Valid empty results for list operations - these are NOT failures
        valid_empty_patterns = [
            "no unread emails", "no emails found", "no new emails",
            "no events", "no calendar events", "nothing scheduled",
            "no tasks", "no pending tasks",
            "no notes", "no matching",
        ]
        
        if is_list_operation:
            for pattern in valid_empty_patterns:
                if pattern in output_lower:
                    # This is a VALID result - let it pass through to LLM
                    return None
        
        # 3. Explicit ERROR indicators (these are always failures)
        error_patterns = [
            "error:", "failed:", "exception:", "traceback", 
            "unable to", "access denied", "unauthorized", "timeout", 
            "timed out", "connection refused", "api key", "rate limit"
        ]
        
        for pattern in error_patterns:
            if pattern in output_lower:
                return VerifierVerdict(passed=False, reason=f"Tool error: {pattern}")
        
        # 4. Weak/apologetic language (high skepticism trigger)
        weak_patterns = [
            "i'm sorry", "i couldn't", "unfortunately", "i was unable",
            "i don't have access", "permission denied", "403", "401", 
            "invalid credentials", "not authorized"
        ]
        
        for pattern in weak_patterns:
            if pattern in output_lower:
                return VerifierVerdict(passed=False, reason=f"Weak response: {pattern}")
        
        # No obvious failure detected - needs LLM evaluation
        return None
    
    def _extract_key_entities(self, user_input: str) -> list:
        """
        V5.1: Extract key entities (dates, emails, names) from user request.
        Used for Key-Fact Scan heuristic.
        """
        entities = []
        
        # Email pattern
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        entities.extend(re.findall(email_pattern, user_input))
        
        # Date patterns (various formats)
        date_patterns = [
            r'\d{1,2}/\d{1,2}/\d{2,4}',  # MM/DD/YYYY
            r'\d{4}-\d{2}-\d{2}',         # YYYY-MM-DD
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{1,2}',  # Month Day
            r'\d{1,2}(?:st|nd|rd|th)? (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',  # Day Month
        ]
        for pattern in date_patterns:
            matches = re.findall(pattern, user_input.lower())
            entities.extend(matches)
        
        # Quoted strings (likely specific names/titles)
        quoted = re.findall(r'"([^"]+)"', user_input)
        entities.extend(quoted)
        quoted_single = re.findall(r"'([^']+)'", user_input)
        entities.extend(quoted_single)
        
        return entities
    
    def _key_fact_scan(self, user_input: str, tool_outputs: str) -> Optional[VerifierVerdict]:
        """
        V5.1: Check if key entities from user request appear in tool output.
        Returns FAIL verdict if critical entity is missing.
        """
        entities = self._extract_key_entities(user_input)
        if not entities:
            return None  # No key entities to check
        
        output_lower = tool_outputs.lower()
        
        missing = []
        for entity in entities[:3]:  # Check max 3 entities
            entity_lower = str(entity).lower()
            if len(entity_lower) > 3 and entity_lower not in output_lower:
                missing.append(entity)
        
        if missing:
            return VerifierVerdict(
                passed=False, 
                reason=f"Key entity missing: {missing[0][:20]}"
            )
        
        return None
    
    def _summarize_plan(self, plan: dict) -> str:
        """Extract tool names from plan for verifier context."""
        steps = plan.get("plan", [])
        if not steps:
            return "(no tools)"
        tools = [s.get("tool", "?") for s in steps[:3]]  # Max 3 tools
        return ", ".join(tools)
    
    def _parse_verdict(self, content: str) -> VerifierVerdict:
        """Parse JSON verdict from LLM response."""
        try:
            # Clean potential markdown wrapping
            clean = content.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].split("```")[0].strip()
            
            data = json.loads(clean)
            
            verdict_str = str(data.get("verdict", "")).upper()
            passed = verdict_str == "PASS"
            reason = str(data.get("reason", "No reason provided"))[:60]  # Cap reason length
            
            return VerifierVerdict(passed=passed, reason=reason, raw_response=content)
            
        except (json.JSONDecodeError, KeyError) as e:
            # Fallback: look for PASS/FAIL in raw text
            upper = content.upper()
            if "FAIL" in upper:
                # Extract reason heuristically
                reason = self._extract_reason(content)
                return VerifierVerdict(passed=False, reason=reason or "Parse failed", raw_response=content)
            else:
                # Default to PASS if unclear
                return VerifierVerdict(passed=True, reason="Assumed pass", raw_response=content)
    
    def _extract_reason(self, text: str) -> str:
        """Heuristic extraction of reason from malformed response."""
        # Look for common patterns
        patterns = [
            r'"reason"\s*:\s*"([^"]+)"',
            r'reason:\s*(.+?)(?:\.|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)[:60]
        return "Unknown reason"
    
    def verify_response_has_judgment(self, response: str, intent_mode: str) -> VerifierVerdict:
        """
        V5.1: Verify that a DATA_REASONING response actually contains reasoning.
        
        Called AFTER responder generates output, only for data_then_reason mode.
        Returns FAIL if response is just content-dumping without analysis.
        
        Args:
            response: The final response text from responder
            intent_mode: The intent mode (only checks for "data_then_reason")
        """
        # Only applies to DATA_REASONING mode
        if intent_mode != "data_then_reason":
            return VerifierVerdict(passed=True, reason="Not data_then_reason mode")
        
        # Import judgment check from intent_classifier
        from .intent_classifier import has_judgment_signals
        
        if has_judgment_signals(response):
            return VerifierVerdict(passed=True, reason="Response contains reasoning/judgment")
        else:
            return VerifierVerdict(
                passed=False, 
                reason="User requested analysis. Tools are inputs, not output.",
                raw_response=response[:200]
            )
