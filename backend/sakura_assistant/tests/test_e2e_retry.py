"""
Sakura V5.1: End-to-End Integration Test
Tests the complete retry flow: tool fail → Verifier FAIL → retry → local formatter.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, Mock, patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sakura_assistant.core.agent_state import AgentState, RateLimitExceeded
from sakura_assistant.core.verifier import Verifier, VerifierVerdict
from sakura_assistant.core.retry_formatter import format_retry_response


class MockLLMResponse:
    """Mock LLM response object."""
    def __init__(self, content):
        self.content = content


class TestE2ERetryFlow:
    """
    End-to-end test: simulates tool failure → Verifier FAIL → retry → local formatter.
    
    This test verifies wiring between:
    - AgentState tracking (4 call limit)
    - Verifier heuristics (pre-LLM catch)
    - Retry formatter (honest language)
    """
    
    def test_full_retry_flow_with_heuristic_fail(self):
        """
        Scenario: Tool fails with error → heuristic catches → no LLM wasted.
        """
        state = AgentState()
        
        # Mock LLM (should NOT be called due to heuristic)
        mock_llm = MagicMock()
        verifier = Verifier(mock_llm)
        
        # Tool output with error (heuristic should catch)
        tool_output = "Step 1 (web_search): Error: API timeout"
        plan = {"plan": [{"tool": "web_search", "args": {"query": "test"}}]}
        
        # Run verifier
        verdict = verifier.evaluate("search for test", plan, tool_output, state)
        
        # Assertions
        assert verdict.is_fail == True
        assert "error" in verdict.reason.lower() or "timeout" in verdict.reason.lower()
        assert state.llm_call_count == 0  # No LLM call spent!
        mock_llm.invoke.assert_not_called()  # LLM never touched
    
    def test_full_retry_flow_with_llm_pass(self):
        """
        Scenario: Tool succeeds → no heuristic trigger → LLM verifies PASS.
        """
        state = AgentState()
        
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse('{"verdict": "PASS", "reason": "Task completed successfully"}')
        verifier = Verifier(mock_llm)
        
        # Successful tool output (no error patterns)
        tool_output = "Step 1 (spotify_control): Playing 'Test Song' by Test Artist"
        plan = {"plan": [{"tool": "spotify_control", "args": {"action": "play", "song_name": "Test Song"}}]}
        
        # Run verifier
        verdict = verifier.evaluate("play test song", plan, tool_output, state)
        
        # Assertions
        assert verdict.is_pass == True
        assert state.llm_call_count == 1  # LLM was called
        mock_llm.invoke.assert_called_once()
    
    def test_full_retry_flow_with_llm_fail_then_retry(self):
        """
        Scenario: Tool works but wrong content → LLM FAIL → retry with hindsight.
        
        This is the canonical V5 flow.
        """
        # === PHASE 1: First attempt fails verification ===
        # V5.1: Use explicit hard_limit=4 for rate limit testing
        state = AgentState(hard_limit=4)
        state.record_llm_call("routing")   # LLM #1
        state.record_llm_call("planning")  # LLM #2
        
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse('{"verdict": "FAIL", "reason": "Wrong song returned"}')
        verifier = Verifier(mock_llm)
        
        tool_output = "Step 1 (spotify_control): Playing 'Wrong Song' by Different Artist"
        plan = {"plan": [{"tool": "spotify_control", "args": {"action": "play", "song_name": "Test Song"}}]}
        
        verdict = verifier.evaluate("play Test Song", plan, tool_output, state)
        
        assert verdict.is_fail == True
        assert state.llm_call_count == 3  # LLM #3 (verifier)
        
        # === PHASE 2: Retry with hindsight ===
        state.set_hindsight(verdict.reason)
        assert state.retry_count == 1
        assert state.hindsight == "Wrong song returned"
        
        # Retry planner would be called here (LLM #4)
        state.record_llm_call("retrying")
        
        # Rate limit now exhausted
        assert state.llm_call_count == 4
        assert state.can_call_llm() == False
        
        # === PHASE 3: Local formatter (no LLM) ===
        retry_output = format_retry_response(
            tool_name="spotify_control",
            tool_args={"action": "play", "song_name": "Test Song"},
            tool_output="Playing 'Test Song' by Correct Artist",
            success=True,
            is_retry=True
        )
        
        # Should NOT have honest prefix for spotify (action doesn't need it)
        assert "Playing" in retry_output
        
        # Verify no 5th LLM call possible
        with pytest.raises(RateLimitExceeded):
            state.record_llm_call("responding")
    
    def test_retry_formatter_honest_language_for_search(self):
        """Test that search retries get honest prefix."""
        response = format_retry_response(
            tool_name="web_search",
            tool_args={"query": "python tutorials"},
            tool_output="10 results found for 'python tutorials'",
            success=True,
            is_retry=True
        )
        
        assert "After refining my search" in response
        assert "results" in response.lower()
    
    def test_retry_formatter_honest_failure(self):
        """Test that retry failures are honest."""
        response = format_retry_response(
            tool_name="web_search",
            tool_args={"query": "impossible query"},
            tool_output="",
            success=False,
            failure_reason="No results found",
            is_retry=True
        )
        
        assert "tried a different approach" in response
        assert "couldn't complete" in response
    
    def test_heuristic_catches_empty_search_results(self):
        """Heuristic should fail on empty search results."""
        state = AgentState()
        mock_llm = MagicMock()
        verifier = Verifier(mock_llm)
        
        plan = {"plan": [{"tool": "web_search", "args": {"query": "test"}}]}
        tool_output = ""  # Empty
        
        verdict = verifier.evaluate("search test", plan, tool_output, state)
        
        assert verdict.is_fail == True
        assert "empty" in verdict.reason.lower()
        assert state.llm_call_count == 0  # Heuristic saved LLM call
    
    def test_heuristic_catches_partial_success(self):
        """Heuristic should fail on partial success language."""
        state = AgentState()
        mock_llm = MagicMock()
        verifier = Verifier(mock_llm)
        
        plan = {"plan": [{"tool": "web_search", "args": {"query": "test"}}]}
        tool_output = "Found some results, but couldn't fully complete the search"
        
        verdict = verifier.evaluate("search test", plan, tool_output, state)
        
        assert verdict.is_fail == True
        assert "partial" in verdict.reason.lower() or "couldn't fully" in verdict.reason.lower()
        assert state.llm_call_count == 0  # Heuristic saved LLM call


class TestStateTransitions:
    """Test that state transitions correctly through retry flow."""
    
    def test_state_phases_through_retry(self):
        """Verify phase transitions during retry."""
        state = AgentState()
        
        state.record_llm_call("routing")
        assert state.phase == "routing"
        
        state.record_llm_call("planning")
        assert state.phase == "planning"
        
        state.record_llm_call("verifying")
        assert state.phase == "verifying"
        
        state.set_hindsight("Failed")
        assert state.hindsight == "Failed"
        assert state.retry_count == 1
        
        state.record_llm_call("retrying")
        assert state.phase == "retrying"
        assert state.llm_call_count == 4
    
    def test_tool_status_tracking(self):
        """Verify tool execution status is tracked."""
        state = AgentState()
        
        state.record_tool_result(success=False)
        assert state.tool_execution_status == "failed"
        
        state.record_tool_result(success=True)
        assert state.tool_execution_status == "success"
        
        state.record_tool_result(success=True, partial=True)
        assert state.tool_execution_status == "partial"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
