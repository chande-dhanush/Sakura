"""
Sakura V5: AgentState Unit Tests
Tests rate limit enforcement, state tracking, and reset behavior.
"""
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sakura_assistant.core.agent_state import AgentState, RateLimitExceeded


class TestAgentStateRateLimit:
    """Test rate limit enforcement."""
    
    def test_initial_state(self):
        """State should start with zero counts."""
        state = AgentState()
        assert state.llm_call_count == 0
        assert state.retry_count == 0
        assert state.can_call_llm() == True
        assert state.remaining_calls() == 8  # V5.1: hard_limit is 8
    
    def test_record_llm_call_increments_count(self):
        """Each record_llm_call should increment the counter."""
        state = AgentState()
        state.record_llm_call("routing")
        assert state.llm_call_count == 1
        assert state.phase == "routing"
        
        state.record_llm_call("planning")
        assert state.llm_call_count == 2
        assert state.phase == "planning"
    
    def test_rate_limit_at_hard_limit(self):
        """Should raise RateLimitExceeded after hard_limit (8) calls."""
        state = AgentState()
        # Make 8 calls - up to hard limit
        for i in range(8):
            state.record_llm_call(f"phase_{i}")
        
        assert state.can_call_llm() == False
        assert state.remaining_calls() == 0
        
        with pytest.raises(RateLimitExceeded):
            state.record_llm_call("extra")  # 9 - BLOCKED
    
    def test_can_call_llm_boundary(self):
        """can_call_llm should return False at exactly hard_limit."""
        state = AgentState(hard_limit=2)  # V5.1: use hard_limit
        assert state.can_call_llm() == True
        
        state.record_llm_call("routing")
        assert state.can_call_llm() == True
        
        state.record_llm_call("responding")
        assert state.can_call_llm() == False


class TestAgentStateReset:
    """Test state reset between turns."""
    
    def test_reset_clears_all_state(self):
        """reset() should clear all mutable state."""
        state = AgentState()
        state.record_llm_call("routing")
        state.record_llm_call("planning")
        state.set_hindsight("Test failure reason")
        state.current_intent = "COMPLEX"
        state.verifier_verdicts.append("FAIL")
        
        state.reset()
        
        assert state.llm_call_count == 0
        assert state.retry_count == 0
        assert state.hindsight is None
        assert state.current_intent == "unknown"
        assert state.phase == "idle"
        assert len(state.verifier_verdicts) == 0
    
    def test_reset_allows_new_calls(self):
        """After reset, should be able to make calls again."""
        state = AgentState(hard_limit=4)  # Use smaller limit for test
        # Exhaust the limit
        for i in range(4):
            state.record_llm_call(f"phase_{i}")
        
        assert state.can_call_llm() == False
        
        # Reset and verify
        state.reset()
        assert state.can_call_llm() == True
        state.record_llm_call("routing")  # Should not raise


class TestAgentStateHindsight:
    """Test hindsight tracking for retries."""
    
    def test_set_hindsight_increments_retry(self):
        """set_hindsight should increment retry_count."""
        state = AgentState()
        assert state.retry_count == 0
        
        state.set_hindsight("First failure")
        assert state.retry_count == 1
        assert state.hindsight == "First failure"
    
    def test_to_metadata_includes_state(self):
        """to_metadata should return all relevant state."""
        state = AgentState()
        state.record_llm_call("routing")
        state.record_llm_call("planning")
        state.set_hindsight("Tool error")
        state.record_tool_result(success=True)
        
        meta = state.to_metadata()
        
        assert meta["llm_calls"] == 2
        assert meta["retries"] == 1
        assert meta["phase"] == "planning"
        assert meta["tool_status"] == "success"


class TestAgentStateToolTracking:
    """Test tool execution status tracking."""
    
    def test_record_tool_result_success(self):
        """Should track successful tool execution."""
        state = AgentState()
        state.record_tool_result(success=True)
        assert state.tool_execution_status == "success"
    
    def test_record_tool_result_failure(self):
        """Should track failed tool execution."""
        state = AgentState()
        state.record_tool_result(success=False)
        assert state.tool_execution_status == "failed"
    
    def test_record_tool_result_partial(self):
        """Should track partial success."""
        state = AgentState()
        state.record_tool_result(success=True, partial=True)
        assert state.tool_execution_status == "partial"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
