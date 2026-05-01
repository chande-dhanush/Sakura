"""
FIX-02 Tests: Router Safety Check Expansion
=============================================
Verifies that _apply_safety_checks() no longer demotes factual
PLAN queries to CHAT due to a too-narrow indicator list.
"""
import pytest
from sakura_assistant.core.routing.router import IntentRouter, RouteResult


class TestRouterSafetyChecks:
    """Test the expanded complex_indicators list in _apply_safety_checks."""

    def _make_router(self):
        """Create an IntentRouter with a dummy LLM (not used here)."""
        return IntentRouter(llm=None)

    #    Factual PLAN queries must STAY as PLAN                          
    @pytest.mark.parametrize("query", [
        "Who is Alan Turing?",
        "What is photosynthesis?",
        "When was the Eiffel Tower built?",
        "Where is the Great Wall of China?",
        "How does a nuclear reactor work?",
        "Why is the sky blue?",
        "Explain quantum entanglement",
        "Define epistemology",
        "Tell me about the history of Rome",
        "Describe the human circulatory system",
        "Compare Python and Rust",
        "Find me the best coffee shops",
        "Look up the capital of France",
        "Research recent advances in AI",
        "What's the weather like?",
        "Show me the latest news",
    ])
    def test_factual_plan_stays_plan(self, query):
        """PLAN without hint on factual/tool-requiring query must stay PLAN."""
        router = self._make_router()
        decision = RouteResult("PLAN", None)
        result = router._apply_safety_checks(query, decision)
        assert result.classification == "PLAN", (
            f"'{query}' was demoted from PLAN to {result.classification}"
        )

    #    Greetings must still be forced to CHAT                          
    @pytest.mark.parametrize("query", [
        "hi",
        "hello",
        "hey there",
        "good morning",
        "how are you",
    ])
    def test_greetings_still_forced_chat(self, query):
        """Greetings classified as PLAN/DIRECT must be forced to CHAT."""
        router = self._make_router()
        decision = RouteResult("PLAN", None)
        result = router._apply_safety_checks(query, decision)
        assert result.classification == "CHAT", (
            f"Greeting '{query}' should be CHAT, got {result.classification}"
        )

    #    Truly simple queries without any indicator stay CHAT            
    @pytest.mark.parametrize("query", [
        "thanks",
        "ok cool",
        "sure thing",
        "lol",
        "I see",
    ])
    def test_simple_no_indicator_stays_chat(self, query):
        """PLAN without hint AND no complex indicator should be demoted to CHAT."""
        router = self._make_router()
        decision = RouteResult("PLAN", None)
        result = router._apply_safety_checks(query, decision)
        assert result.classification == "CHAT", (
            f"Simple query '{query}' should be demoted to CHAT, got {result.classification}"
        )

    #    DIRECT with valid hint must not be touched                      
    def test_direct_with_hint_untouched(self):
        """DIRECT + tool_hint must pass through unchanged."""
        router = self._make_router()
        decision = RouteResult("DIRECT", "get_weather")
        result = router._apply_safety_checks("What's the weather?", decision)
        assert result.classification == "DIRECT"
        assert result.tool_hint == "get_weather"

    #    PLAN with hint must not be touched                              
    def test_plan_with_hint_untouched(self):
        """PLAN + tool_hint must pass through unchanged (Check 3 only fires
        when tool_hint is None)."""
        router = self._make_router()
        decision = RouteResult("PLAN", "web_search")
        result = router._apply_safety_checks("Research quantum computing", decision)
        assert result.classification == "PLAN"
        assert result.tool_hint == "web_search"

    #    Original V17.2 indicators still work                            
    @pytest.mark.parametrize("query", [
        "first check email and then play music",
        "search for AI news and also open VS Code",
        "calculate my monthly budget after that",
    ])
    def test_original_indicators_still_work(self, query):
        """V17.2 indicators (and then, after that, first, also, calculate, search)
        must still allow PLAN through without demotion."""
        router = self._make_router()
        decision = RouteResult("PLAN", None)
        result = router._apply_safety_checks(query, decision)
        assert result.classification == "PLAN"
