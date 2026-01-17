"""
Test Suite: Deterministic Context Router (V15.4)
==============================================
Tests for V15.4 mode-based context pruning and code hygiene.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from sakura_assistant.core.context_manager import ContextManager, get_smart_context, ContextSignals


class TestDeterministicRouting(unittest.TestCase):
    """Test ContextManager deterministic routing and mode-based pruning."""
    
    @classmethod
    def setUpClass(cls):
        """Create ContextManager instance."""
        cls.cm = ContextManager()
    
    def test_detect_signals_identity(self):
        """Test that identity keywords trigger 'facts' signals."""
        signals = self.cm._detect_signals("Who am I?")
        self.assertTrue(signals.facts, "Should detect 'facts' signal for 'Who am I?'")
        
        signals = self.cm._detect_signals("Tell me about myself")
        self.assertTrue(signals.facts, "Should detect 'facts' signal for 'about myself'")
    
    def test_detect_signals_temporal(self):
        """Test that temporal keywords trigger 'temporal' and 'episodes' signals."""
        signals = self.cm._detect_signals("What did we talk about yesterday?")
        self.assertTrue(signals.temporal, "Should detect 'temporal' for 'yesterday'")
        self.assertTrue(signals.episodes, "Temporal queries should infer 'episodes' signal")
    
    def test_detect_signals_location(self):
        """Test that location keywords trigger 'location' signal."""
        signals = self.cm._detect_signals("Where am I?")
        self.assertTrue(signals.location, "Should detect 'location' signal")
    
    def test_direct_mode_pruning(self):
        """Test that DIRECT mode produces compact planner context."""
        ctx_data = self.cm.get_context_for_llm("Play Numb by Linkin Park", mode="DIRECT")
        ctx = ctx_data["planner_context"]
        
        # Should be compact
        self.assertLess(len(ctx), 300, f"DIRECT mode context too long: {len(ctx)} chars")
        
        # Should NOT contain full identity block
        self.assertNotIn("=== USER IDENTITY ===", ctx, "DIRECT mode should not have full identity")
        
        # Should contain minimal user info
        self.assertIn("[USER]", ctx, "DIRECT mode should have minimal user tag")
    
    def test_direct_mode_identity_inclusion(self):
        """Test that DIRECT mode INCLUDES identity for identity queries."""
        ctx_data = self.cm.get_context_for_llm("Who am I?", mode="DIRECT")
        ctx = ctx_data["planner_context"]
        
        # Even in DIRECT mode, identity query should get full identity
        self.assertIn("=== USER IDENTITY ===", ctx, "Identity query should get full identity even in DIRECT")
    
    def test_plan_mode_full_context(self):
        """Test that PLAN mode includes full context."""
        ctx_data = self.cm.get_context_for_llm("Research quantum computing", mode="PLAN")
        ctx = ctx_data["planner_context"]
        
        # Should contain full identity block
        self.assertIn("=== USER IDENTITY ===", ctx, "PLAN mode should have full identity")
        
        # Should contain preferences
        self.assertIn("Preferences:", ctx, "PLAN mode should have preferences")
        
        # Should contain actions (if any exist)
        # Note: In fresh test state there might be no actions, so we check for block header if force was used 
        # but PLAN mode only adds if act exists.
    
    def test_chat_mode_episodic_priority(self):
        """Test that CHAT mode attempts episodic memory."""
        ctx_data = self.cm.get_context_for_llm("Tell me a joke", mode="CHAT")
        ctx = ctx_data["planner_context"]
        
        # Should contain full identity block
        self.assertIn("=== USER IDENTITY ===", ctx, "CHAT mode should have full identity")
    
    def test_unified_v15_4_api(self):
        """Test get_context_for_llm returns proper V15.4 structure."""
        result = self.cm.get_context_for_llm("Hello", mode="CHAT", history=[])
        
        self.assertIn("planner_context", result)
        self.assertIn("responder_context", result)
        self.assertIn("summary_context", result)
    
    def test_no_hallucination_identity(self):
        """Test that identity returns only WorldGraph data."""
        ctx_data = self.cm.get_context_for_llm("Who am I?", mode="CHAT")
        ctx = ctx_data["planner_context"]
        
        # Get expected identity from WorldGraph
        expected_name = self.cm.wg.get_user_identity().name
        
        # Context should contain the real name from WorldGraph
        self.assertIn(f"User: {expected_name}", ctx, 
                      f"Context should contain WorldGraph name '{expected_name}'")


class TestGetSmartContextShim(unittest.TestCase):
    """Test the module-level get_smart_context shim."""
    
    def test_get_smart_context_compatibility(self):
        """Test shim maintains old key names for backward compatibility."""
        result = get_smart_context("Play music", [], mode="DIRECT")
        
        self.assertIsInstance(result, dict)
        self.assertIn("dynamic_user_context", result)
        self.assertIn("graph_context", result)
        self.assertIn("short_memory_summary", result)


if __name__ == "__main__":
    print("=== V15.4 Deterministic Context Router Tests ===\n")
    unittest.main(verbosity=2)

