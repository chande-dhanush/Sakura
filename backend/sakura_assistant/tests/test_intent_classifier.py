"""
Sakura V5.1: Intent Classifier Tests
Tests rule-based intent classification for three modes.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sakura_assistant.core.intent_classifier import (
    classify_intent, IntentMode, has_judgment_signals,
    REASONING_KEYWORDS, FETCH_KEYWORDS, ACTION_KEYWORDS
)


class TestIntentClassification:
    """Test intent classification into 3 modes."""
    
    def test_reasoning_only_opinion(self):
        """Pure opinion request → REASONING_ONLY."""
        mode, reason = classify_intent("What's your honest opinion about AI?")
        assert mode == IntentMode.REASONING_ONLY
        assert "reasoning" in reason
    
    def test_reasoning_only_thoughts(self):
        """Thoughts request → REASONING_ONLY."""
        mode, _ = classify_intent("What do you think about this idea?")
        assert mode == IntentMode.REASONING_ONLY
    
    def test_data_reasoning_website(self):
        """Check website + opinion → DATA_REASONING."""
        mode, reason = classify_intent("Check my website and give me your honest opinion")
        assert mode == IntentMode.DATA_REASONING
        assert "reasoning + fetch" in reason
    
    def test_data_reasoning_news(self):
        """Look up news + analyze → DATA_REASONING."""
        mode, _ = classify_intent("Look up the news and analyze it for me")
        assert mode == IntentMode.DATA_REASONING
    
    def test_data_reasoning_search_think(self):
        """Search + thoughts → DATA_REASONING."""
        mode, _ = classify_intent("Search for Python tutorials and tell me what you think")
        assert mode == IntentMode.DATA_REASONING
    
    def test_data_reasoning_search_docs_tell_how(self):
        """Search docs + tell me how → DATA_REASONING (the n8n docs bug)."""
        mode, reason = classify_intent("can u search up the n8n docs and tell me how to update my n8n instance hosted on docker")
        assert mode == IntentMode.DATA_REASONING
        assert "reasoning + fetch" in reason
    
    def test_data_reasoning_explain_how(self):
        """Search + explain how → DATA_REASONING."""
        mode, _ = classify_intent("look up the docs and explain how to configure it")
        assert mode == IntentMode.DATA_REASONING
    
    def test_action_play(self):
        """Play command → ACTION."""
        mode, reason = classify_intent("Play training AMV on YouTube")
        assert mode == IntentMode.ACTION
        assert "action" in reason.lower()
    
    def test_action_send(self):
        """Send command → ACTION."""
        mode, _ = classify_intent("Send an email to John")
        assert mode == IntentMode.ACTION
    
    def test_action_create(self):
        """Create command → ACTION."""
        mode, _ = classify_intent("Create a note about the meeting")
        assert mode == IntentMode.ACTION
    
    def test_action_priority_first_verb(self):
        """First verb is action → ACTION overrides."""
        mode, reason = classify_intent("Play that song... what do you think?")
        assert mode == IntentMode.ACTION
        assert "imperative" in reason or "play" in reason
    
    def test_reasoning_with_action_verb_not_first(self):
        """Action verb not first = reasoning + action = still routed based on keywords."""
        mode, _ = classify_intent("What do you think I should play?")
        # "play" is an action keyword, but not imperative (first verb)
        # Since it has reasoning AND action, but no fetch → default to ACTION for ambiguous
        assert mode == IntentMode.ACTION


class TestJudgmentSignals:
    """Test judgment signal detection."""
    
    def test_comparative_language(self):
        """Comparative words indicate judgment."""
        assert has_judgment_signals("This is clearly better than the alternative")
        assert has_judgment_signals("Option A is better")
    
    def test_evaluative_language(self):
        """Pros/cons indicate judgment."""
        assert has_judgment_signals("The pros outweigh the cons")
    
    def test_critique_language(self):
        """Critique words indicate judgment."""
        assert has_judgment_signals("The main issue is performance")
        assert has_judgment_signals("This needs improvement")
    
    def test_analytical_language(self):
        """Analytical markers indicate judgment."""
        assert has_judgment_signals("This suggests that the design is flawed")
        assert has_judgment_signals("The data indicates a problem")
    
    def test_multi_sentence_counts(self):
        """3+ substantive sentence responses count as having judgment."""
        response = "The website looks clean. The navigation is intuitive. Performance could be improved. Overall a solid effort."
        assert has_judgment_signals(response)
    
    def test_content_dump_fails(self):
        """Raw content without judgment fails."""
        assert not has_judgment_signals("Here is the data")
        assert not has_judgment_signals("The search returned 5 results")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
