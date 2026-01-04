"""
Sakura V5.1: Full Loop Integration Test
"The Ghost in the Machine" - Tests complete failure→retry→success flow.

Test Scenario:
1. User asks for a calendar event
2. Tool returns 403 Permission Error
3. Verifier detects FAIL (via heuristics)
4. Retry Planner receives Hindsight
5. Second tool succeeds
6. Local formatter returns final text
7. Assert: Total LLM calls = 4, Status sequence correct (uses hard_limit=4 for testing)
"""
import pytest
import sys
import os
from enum import Enum
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sakura_assistant.core.agent_state import AgentState, RateLimitExceeded
from sakura_assistant.core.verifier import Verifier, VerifierVerdict
from sakura_assistant.core.retry_formatter import format_retry_response


# Mirror of ProcessingStatus from viewmodel (avoid Qt import in tests)
class ProcessingStatus(Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"


class MockLLMResponse:
    def __init__(self, content):
        self.content = content


class TestV5FullLoop:
    """
    The canonical V5 integration test - simulates the complete failure→retry→success path.
    """
    
    def test_calendar_403_to_success_full_flow(self):
        """
        Scenario:
        1. User: "Check my calendar for tomorrow"
        2. calendar_get_events returns 403
        3. Heuristic catches 403 → FAIL (no LLM wasted)
        4. Retry with hindsight
        5. Second attempt succeeds → local formatter
        6. Assert: Total LLM = 4, correct status sequence
        """
        # === SETUP ===
        # V5.1: Use explicit hard_limit=4 to test rate limit behavior
        state = AgentState(hard_limit=4)
        status_sequence = []
        
        # Track status transitions
        def record_status(phase):
            status_sequence.append(phase)
            state.phase = phase
        
        mock_llm = MagicMock()
        verifier = Verifier(mock_llm)
        
        # === PHASE 1: ROUTING ===
        record_status("routing")
        state.record_llm_call("routing")  # LLM #1
        assert state.llm_call_count == 1
        
        # === PHASE 2: PLANNING ===
        record_status("planning")
        state.record_llm_call("planning")  # LLM #2
        assert state.llm_call_count == 2
        
        # === PHASE 3: EXECUTION (first attempt) ===
        record_status("executing")
        first_tool_output = "Step 1 (calendar_get_events): Error 403: Permission denied"
        plan = {"plan": [{"tool": "calendar_get_events", "args": {"date": "tomorrow"}}]}
        
        # === PHASE 4: VERIFICATION ===
        record_status("verifying")
        verdict = verifier.evaluate("Check my calendar for tomorrow", plan, first_tool_output, state)
        
        # Heuristic should catch 403 - NO LLM CALL SPENT
        assert verdict.is_fail == True
        assert "403" in verdict.reason or "permission" in verdict.reason.lower()
        assert state.llm_call_count == 2  # Still 2! Heuristic saved a call
        
        # === PHASE 5: RETRYING ===
        record_status("retrying")
        state.set_hindsight(verdict.reason)
        assert state.retry_count == 1
        assert state.hindsight is not None
        
        state.record_llm_call("retrying")  # LLM #3 (retry planner)
        assert state.llm_call_count == 3
        
        # === PHASE 6: SECOND EXECUTION ===
        record_status("executing")
        retry_output = "Step 1 (gmail_read_email): Found email: 'Meeting tomorrow at 3pm'"
        retry_plan = {"plan": [{"tool": "gmail_read_email", "args": {"query": "meeting tomorrow"}}]}
        
        # Verify retry - should pass (no error patterns)
        mock_llm.invoke.return_value = MockLLMResponse('{"verdict": "PASS", "reason": "Found meeting info"}')
        retry_verdict = verifier.evaluate("Check my calendar for tomorrow", retry_plan, retry_output, state)
        
        # This time LLM was called (no heuristic trigger)
        assert retry_verdict.is_pass == True
        assert state.llm_call_count == 4  # LLM #4 (verifier on retry)
        
        # === PHASE 7: LOCAL FORMATTER (no LLM) ===
        record_status("formatting")
        final_response = format_retry_response(
            tool_name="gmail_read_email",
            tool_args={"query": "meeting tomorrow"},
            tool_output="Found email: 'Meeting tomorrow at 3pm'",
            success=True,
            is_retry=True
        )
        
        # Should have honest retry language
        assert "after" in final_response.lower() or "second" in final_response.lower() or "refin" in final_response.lower()
        
        # === PHASE 8: VERIFY FINAL STATE ===
        record_status("completed")
        
        # CRITICAL ASSERTIONS
        assert state.llm_call_count == 4  # Hard limit respected
        assert state.retry_count == 1
        assert state.can_call_llm() == False  # Budget exhausted
        
        # Status sequence verification
        expected_phases = ["routing", "planning", "executing", "verifying", 
                          "retrying", "executing", "formatting", "completed"]
        assert status_sequence == expected_phases
        
        # No 5th LLM call possible
        with pytest.raises(RateLimitExceeded):
            state.record_llm_call("responding")
    
    def test_entity_extraction_emails(self):
        """
        V5.1 Test-Phase: Entity extraction works correctly (scan disabled in prod).
        Test the extraction function directly.
        """
        verifier = Verifier(None)
        
        entities = verifier._extract_key_entities("Send email to john@example.com")
        assert "john@example.com" in entities
    
    def test_weak_language_triggers_fail(self):
        """
        Scenario: Tool returns "I'm sorry, I couldn't find..." → Weak language trigger.
        """
        state = AgentState()
        mock_llm = MagicMock()
        verifier = Verifier(mock_llm)
        
        tool_output = "I'm sorry, I couldn't access your calendar due to authentication issues."
        plan = {"plan": [{"tool": "calendar_get_events", "args": {}}]}
        
        verdict = verifier.evaluate("Show my calendar", plan, tool_output, state)
        
        assert verdict.is_fail == True
        assert "weak" in verdict.reason.lower() or "sorry" in verdict.reason.lower() or "couldn't" in verdict.reason.lower()
        assert state.llm_call_count == 0  # Heuristic saved LLM call
    
    def test_entity_extraction_quoted(self):
        """
        V5.1 Test-Phase: Quoted string extraction works.
        """
        verifier = Verifier(None)
        
        entities = verifier._extract_key_entities('Play "Bohemian Rhapsody" on Spotify')
        assert "Bohemian Rhapsody" in entities
    
    def test_date_entity_detection(self):
        """
        V5.1 Test-Phase: Date/email extraction test.
        """
        verifier = Verifier(None)
        
        # Test email extraction
        entities = verifier._extract_key_entities("Send to test@email.com")
        assert "test@email.com" in entities
        
        # Test quoted string extraction
        entities = verifier._extract_key_entities('Play "Bohemian Rhapsody"')
        assert "Bohemian Rhapsody" in entities


class TestProcessingStatusContract:
    """Test that ProcessingStatus enum is properly defined for UI contract."""
    
    def test_processing_status_values(self):
        """Verify all required status values exist."""
        assert ProcessingStatus.IDLE.value == "idle"
        assert ProcessingStatus.PROCESSING.value == "processing"
        assert ProcessingStatus.RETRYING.value == "retrying"
        assert ProcessingStatus.COMPLETED.value == "completed"
        assert ProcessingStatus.FAILED.value == "failed"
    
    def test_status_enum_is_string_based(self):
        """Status values should be strings for UI signaling."""
        for status in ProcessingStatus:
            assert isinstance(status.value, str)


class TestHeuristicsSaveLLMCalls:
    """Verify heuristics save LLM calls across various failure modes."""
    
    @pytest.mark.parametrize("error_pattern", [
        "Error: connection timeout",
        "Failed: invalid API key", 
        "Access denied: missing permissions",
        "Not found: no matching results",
        "Unable to complete the request",
        "403 Forbidden",
        "I'm sorry, I couldn't find that",
    ])
    def test_error_patterns_save_llm(self, error_pattern):
        """Various error patterns should trigger heuristic FAIL without LLM."""
        state = AgentState()
        mock_llm = MagicMock()
        verifier = Verifier(mock_llm)
        
        plan = {"plan": [{"tool": "web_search", "args": {}}]}
        
        verdict = verifier.evaluate("search test", plan, error_pattern, state)
        
        # Core assertion: heuristic caught it (FAIL + no LLM call)
        assert verdict.is_fail == True, f"Expected FAIL for pattern: {error_pattern}"
        assert state.llm_call_count == 0, "Heuristic should have caught this"
        mock_llm.invoke.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
