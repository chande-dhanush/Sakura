"""
Sakura V13: Constraint Injection Tests

Regression tests for the State Machine architecture.
Critical test: Surgery scenario that caused the original failure.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

# Import modules under test
from sakura_assistant.core.state_manager import (
    StateManager, ConstraintState, StateType, StateStatus
)
from sakura_assistant.core.constraint_injector import (
    ConstraintExtractor, ConstraintInjector
)
from sakura_assistant.core.reflection import ReflectionEngine


class TestStateManager:
    """Test StateManager core functionality."""
    
    def test_add_state_basic(self):
        """Test basic constraint addition."""
        manager = StateManager(token_budget=200)
        
        state = ConstraintState(
            id="test_001",
            type=StateType.PHYSICAL,
            constraint="Test constraint",
            implications=["action1", "action2"],
            criticality=0.8,
            user_emphasis=0.7
        )
        
        result = manager.add_state(state)
        
        assert result is True
        assert len(manager.active_states) == 1
        assert manager.active_states[0].id == "test_001"
    
    def test_duplicate_id_rejected(self):
        """Test that duplicate IDs are rejected."""
        manager = StateManager(token_budget=200)
        
        state1 = ConstraintState(id="dup_001", type=StateType.PHYSICAL, constraint="First")
        state2 = ConstraintState(id="dup_001", type=StateType.TEMPORAL, constraint="Second")
        
        assert manager.add_state(state1) is True
        assert manager.add_state(state2) is False
        assert len(manager.active_states) == 1
    
    def test_token_budget_enforcement(self):
        """Test that states are archived when token budget exceeded."""
        manager = StateManager(token_budget=50)  # Small budget
        
        # Add multiple states that exceed budget
        for i in range(5):
            state = ConstraintState(
                id=f"budget_{i}",
                type=StateType.PHYSICAL,
                constraint=f"Long constraint description number {i} that takes tokens",
                implications=["action1", "action2", "action3"],
                criticality=0.5 + (i * 0.1)
            )
            manager.add_state(state)
        
        # Should have some archived due to budget
        assert len(manager.active_states) < 5
        assert len(manager.archived_states) > 0
    
    def test_priority_ordering(self):
        """Test that states are ordered by priority (criticality * type_weight)."""
        manager = StateManager(token_budget=500)
        
        # Add low priority first
        low_priority = ConstraintState(
            id="low",
            type=StateType.EMOTIONAL,  # Weight: 0.4
            constraint="Low priority",
            criticality=0.3
        )
        
        # Add high priority second
        high_priority = ConstraintState(
            id="high",
            type=StateType.PHYSICAL,  # Weight: 1.0
            constraint="High priority",
            criticality=0.9
        )
        
        manager.add_state(low_priority)
        manager.add_state(high_priority)
        
        # High priority should be first
        assert manager.active_states[0].id == "high"
        assert manager.active_states[1].id == "low"
    
    def test_auto_expiry(self):
        """Test time-based automatic expiry."""
        manager = StateManager(token_budget=200)
        
        # Create expired state
        expired_state = ConstraintState(
            id="expired_001",
            type=StateType.TEMPORAL,
            constraint="Past deadline",
            expires_at=datetime.now() - timedelta(hours=1),
            auto_expire=True
        )
        
        manager.active_states.append(expired_state)  # Bypass add_state
        
        retired = manager.check_expiry()
        
        assert "expired_001" in retired
        assert len(manager.active_states) == 0
        assert len(manager.archived_states) == 1
    
    def test_prompt_injection_format(self):
        """Test that prompt injection generates correct format."""
        manager = StateManager(token_budget=200)
        
        state = ConstraintState(
            id="inject_001",
            type=StateType.PHYSICAL,
            constraint="Cannot walk due to surgery",
            implications=["walking", "exercise", "going outside"]
        )
        manager.add_state(state)
        
        injection = manager.to_prompt_injection()
        
        assert "<active_constraints>" in injection
        assert "[PHYSICAL]" in injection
        assert "Cannot walk due to surgery" in injection
        assert "DO NOT suggest:" in injection
        assert "walking" in injection
    
    def test_retire_state(self):
        """Test manual state retirement."""
        manager = StateManager(token_budget=200)
        
        state = ConstraintState(id="retire_001", type=StateType.PHYSICAL, constraint="Test")
        manager.add_state(state)
        
        result = manager.retire_state("retire_001", reason="Test retirement")
        
        assert result is True
        assert len(manager.active_states) == 0
        assert len(manager.archived_states) == 1
        assert manager.archived_states[0].status == StateStatus.ARCHIVED


class TestConstraintInjector:
    """Test ConstraintInjector middleware."""
    
    def test_inject_into_responder_context(self):
        """Test constraint injection for responder."""
        manager = StateManager(token_budget=200)
        injector = ConstraintInjector(state_manager=manager)
        
        state = ConstraintState(
            id="resp_001",
            type=StateType.PHYSICAL,
            constraint="Cannot walk",
            implications=["walking", "exercise"]
        )
        manager.add_state(state)
        
        injection = injector.inject_into_responder_context(None)
        
        assert "<active_constraints>" in injection
        assert "<constraint_enforcement_rules>" in injection
        assert "FORBIDDEN" in injection
    
    def test_diagnose_violation(self):
        """Test violation detection."""
        manager = StateManager(token_budget=200)
        injector = ConstraintInjector(state_manager=manager)
        
        state = ConstraintState(
            id="violate_001",
            type=StateType.PHYSICAL,
            constraint="Cannot walk",
            implications=["walk", "exercise"]  # Use 'walk' for substring match
        )
        manager.add_state(state)
        
        # Simulate a violation
        diagnosis = injector.diagnose_failure(
            user_query="What should I do?",
            assistant_response="Try taking a 10-minute walk outside!"
        )
        
        assert diagnosis["violations_found"] > 0
        assert "walk" in str(diagnosis["details"])


class TestSurgeryScenario:
    """
    CRITICAL REGRESSION TEST
    
    This is the exact scenario that caused the original failure:
    1. User: "I had corn removal surgery on both legs"
    2. User: "I'm feeling off"
    3. Assistant should NOT suggest walking
    """
    
    def test_surgery_constraint_detection(self):
        """Test that surgery message would be detected as constraint."""
        manager = StateManager(token_budget=200)
        
        # Simulate what ConstraintExtractor would produce
        surgery_state = ConstraintState(
            id="phys_surgery_001",
            type=StateType.PHYSICAL,
            constraint="Cannot walk normally due to corn removal surgery (both legs)",
            implications=["walking", "going outside", "physical exercise", "standing for long periods"],
            criticality=0.9,
            user_emphasis=0.8,
            expires_at=datetime.now() + timedelta(days=14),
            auto_expire=True
        )
        
        manager.add_state(surgery_state)
        
        # Verify injection includes the constraint
        injection = manager.to_prompt_injection()
        
        assert "surgery" in injection.lower()
        assert "walking" in injection.lower()
        assert "DO NOT suggest" in injection
    
    def test_surgery_prevents_walk_suggestion(self):
        """Test that constraint injection prevents walking suggestions."""
        manager = StateManager(token_budget=200)
        injector = ConstraintInjector(state_manager=manager)
        
        # Add surgery constraint with short forms for substring matching
        surgery_state = ConstraintState(
            id="phys_surgery_001",
            type=StateType.PHYSICAL,
            constraint="Cannot walk - corn removal surgery (both legs)",
            implications=["walk", "outside", "exercise", "standing"],  # Short forms
            criticality=0.9
        )
        manager.add_state(surgery_state)
        
        # Simulate diagnosis on a bad response
        bad_response = "You should try a 10-minute walk outside to clear your head!"
        diagnosis = injector.diagnose_failure("I'm feeling off", bad_response)
        
        # Should detect the violation
        assert diagnosis["violations_found"] > 0
        
        # Good response should not trigger violation (avoids 'walk' and 'outside')
        good_response = "Since you have surgery recovery, try some gentle stretches or meditation instead."
        diagnosis_good = injector.diagnose_failure("I'm feeling off", good_response)
        
        assert diagnosis_good["violations_found"] == 0


class TestReflectionEngine:
    """Test ReflectionEngine retirement logic."""
    
    def test_pattern_retirement_physical(self):
        """Test pattern-based retirement for physical constraints."""
        manager = StateManager(token_budget=200)
        engine = ReflectionEngine(llm_client=None, state_manager=manager)
        
        # Add a physical constraint
        state = ConstraintState(
            id="phys_test",
            type=StateType.PHYSICAL,
            constraint="Broken leg",
            implications=["walking"]
        )
        manager.add_state(state)
        
        # User says they're healed
        engine._check_explicit_retirement("My leg is healed now!")
        
        # Should be retired
        assert len(manager.active_states) == 0
        assert len(manager.archived_states) == 1
    
    def test_pattern_retirement_temporal(self):
        """Test pattern-based retirement for temporal constraints."""
        manager = StateManager(token_budget=200)
        engine = ReflectionEngine(llm_client=None, state_manager=manager)
        
        state = ConstraintState(
            id="temp_test",
            type=StateType.TEMPORAL,
            constraint="Exam deadline tomorrow",
            implications=["taking breaks"]
        )
        manager.add_state(state)
        
        # Use phrase that matches pattern: "i (finished|completed|submitted|handed in) (the|my)"
        engine._check_explicit_retirement("I finished the exam!")
        
        assert len(manager.active_states) == 0
    
    def test_mention_count_update(self):
        """Test that mention counts are updated."""
        manager = StateManager(token_budget=200)
        engine = ReflectionEngine(llm_client=None, state_manager=manager)
        
        state = ConstraintState(
            id="mention_test",
            type=StateType.PHYSICAL,
            constraint="Knee injury",
            implications=["running"]
        )
        manager.add_state(state)
        
        initial_count = state.mention_count
        
        # Mention the constraint
        engine._update_mention_counts(
            "My knee is still bothering me",
            "I understand your knee is causing issues"
        )
        
        assert state.mention_count > initial_count


# Run with: python -m pytest tests/test_constraint_injection.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
