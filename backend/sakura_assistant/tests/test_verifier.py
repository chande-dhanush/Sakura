"""
Sakura V5: Verifier Unit Tests
Tests verdict parsing and handling of various LLM responses.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, Mock

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sakura_assistant.core.verifier import Verifier, VerifierVerdict, VERIFIER_SYSTEM_PROMPT
from sakura_assistant.core.agent_state import AgentState


class MockLLMResponse:
    """Mock LLM response object."""
    def __init__(self, content):
        self.content = content


class TestVerifierVerdictParsing:
    """Test parsing of various LLM response formats."""
    
    def test_parse_clean_pass_json(self):
        """Should parse clean PASS JSON correctly."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse('{"verdict": "PASS", "reason": "Task completed"}')
        
        verifier = Verifier(mock_llm)
        state = AgentState()
        
        verdict = verifier.evaluate("play music", {"plan": []}, "Playing now", state)
        
        assert verdict.passed == True
        assert verdict.is_pass == True
        assert verdict.is_fail == False
        assert "completed" in verdict.reason.lower()
    
    def test_parse_clean_fail_json(self):
        """Should parse clean FAIL JSON correctly."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse('{"verdict": "FAIL", "reason": "Song not found"}')
        
        verifier = Verifier(mock_llm)
        state = AgentState()
        
        verdict = verifier.evaluate("play unknown", {"plan": []}, "Error: not found", state)
        
        assert verdict.passed == False
        assert verdict.is_pass == False
        assert verdict.is_fail == True
        assert "not found" in verdict.reason.lower()
    
    def test_parse_markdown_wrapped_json(self):
        """Should parse JSON wrapped in markdown code blocks."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse('```json\n{"verdict": "PASS", "reason": "Done"}\n```')
        
        verifier = Verifier(mock_llm)
        state = AgentState()
        
        verdict = verifier.evaluate("test", {"plan": []}, "output", state)
        
        assert verdict.passed == True
    
    def test_parse_malformed_response_with_fail_keyword(self):
        """Should detect FAIL even in malformed response."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse('FAIL - the search returned wrong results')
        
        verifier = Verifier(mock_llm)
        state = AgentState()
        
        verdict = verifier.evaluate("test", {"plan": []}, "output", state)
        
        assert verdict.passed == False
    
    def test_parse_malformed_response_defaults_to_pass(self):
        """Should default to PASS on completely malformed response."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse('This is not JSON at all')
        
        verifier = Verifier(mock_llm)
        state = AgentState()
        
        verdict = verifier.evaluate("test", {"plan": []}, "output", state)
        
        assert verdict.passed == True  # Default safe behavior


class TestVerifierLLMCallTracking:
    """Test that Verifier properly tracks LLM calls via AgentState."""
    
    def test_evaluate_increments_llm_count(self):
        """evaluate() should record an LLM call."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse('{"verdict": "PASS", "reason": "OK"}')
        
        verifier = Verifier(mock_llm)
        state = AgentState()
        
        assert state.llm_call_count == 0
        
        verifier.evaluate("test", {"plan": []}, "output", state)
        
        assert state.llm_call_count == 1
        assert state.phase == "verifying"
    
    def test_evaluate_respects_rate_limit(self):
        """evaluate() should fail if rate limit exhausted."""
        from sakura_assistant.core.agent_state import RateLimitExceeded
        
        mock_llm = MagicMock()
        verifier = Verifier(mock_llm)
        
        # Exhaust the rate limit with explicit hard_limit=4 for testing
        state = AgentState(hard_limit=4)
        for i in range(4):
            state.record_llm_call(f"phase_{i}")
        
        with pytest.raises(RateLimitExceeded):
            verifier.evaluate("test", {"plan": []}, "output", state)


class TestVerifierErrorHandling:
    """Test error handling in Verifier."""
    
    def test_llm_error_returns_pass_verdict(self):
        """LLM errors should not block - default to PASS."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API Error")
        
        verifier = Verifier(mock_llm)
        state = AgentState()
        
        verdict = verifier.evaluate("test", {"plan": []}, "output", state)
        
        # Should not raise, should return PASS
        assert verdict.passed == True
        assert "unavailable" in verdict.reason.lower()
    
    def test_truncates_long_tool_output(self):
        """Should truncate very long tool output to prevent token overflow."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MockLLMResponse('{"verdict": "PASS", "reason": "OK"}')
        
        verifier = Verifier(mock_llm)
        state = AgentState()
        
        # Create a very long output
        long_output = "x" * 10000
        
        verifier.evaluate("test", {"plan": []}, long_output, state)
        
        # Check that invoke was called with truncated output
        call_args = mock_llm.invoke.call_args[0][0]  # First positional arg is messages
        human_msg = call_args[1].content  # Second message is HumanMessage
        
        # Should be truncated to ~1000 chars
        assert len(human_msg) < 1500


class TestVerifierVerdictDataclass:
    """Test VerifierVerdict dataclass properties."""
    
    def test_is_pass_property(self):
        verdict = VerifierVerdict(passed=True, reason="OK")
        assert verdict.is_pass == True
        assert verdict.is_fail == False
    
    def test_is_fail_property(self):
        verdict = VerifierVerdict(passed=False, reason="Failed")
        assert verdict.is_pass == False
        assert verdict.is_fail == True
    
    def test_raw_response_optional(self):
        verdict = VerifierVerdict(passed=True, reason="OK")
        assert verdict.raw_response is None
        
        verdict2 = VerifierVerdict(passed=True, reason="OK", raw_response="raw")
        assert verdict2.raw_response == "raw"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
