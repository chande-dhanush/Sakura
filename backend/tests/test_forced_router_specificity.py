"""
FIX-06 Tests: Forced Router Specificity
=========================================
Verifies the negative-lookahead on the generic "search for X" pattern
so it no longer swallows queries targeting specialized tools.
"""
import pytest
from sakura_assistant.core.routing.forced_router import get_forced_tool


class TestForcedRouterSpecificity:
    """The generic 'search for X' pattern must NOT match queries
    that explicitly target a specialized service."""

    # ── Queries that should NOT be captured by web_search ───────────────
    @pytest.mark.parametrize("query", [
        "search wikipedia for quantum computing",
        "search my calendar for meetings",
        "search my email for the invoice",
        "search my inbox for unread messages",
        "search arxiv for transformer papers",
        "search my notes for grocery list",
    ])
    def test_specialized_queries_not_forced_web_search(self, query):
        """Specialized-target queries must NOT be forced to web_search."""
        result = get_forced_tool(query)
        if result is not None:
            assert result["tool"] != "web_search", (
                f"'{query}' was incorrectly forced to web_search. "
                f"Got: {result}"
            )

    # ── Queries that SHOULD still be captured by web_search ────────────
    @pytest.mark.parametrize("query,expected_tool", [
        ("search for quantum computing", "web_search"),
        ("search for best restaurants near me", "web_search"),
        ("search for python tutorial", "web_search"),
        ("search latest AI news", "web_search"),
    ])
    def test_generic_searches_still_forced(self, query, expected_tool):
        """Generic search queries must still be forced to web_search."""
        result = get_forced_tool(query)
        assert result is not None, f"'{query}' should have matched a forced pattern"
        assert result["tool"] == expected_tool, (
            f"'{query}' should force {expected_tool}, got {result['tool']}"
        )

    # ── Explicit web search phrases still work ─────────────────────────
    @pytest.mark.parametrize("query", [
        "search the web for climate change",
        "google the web for quantum computing",
        "browse the internet for recipes",
    ])
    def test_explicit_web_search_still_works(self, query):
        """Queries that explicitly say 'web/internet/google' should still
        match the FIRST web_search pattern (not affected by our fix)."""
        result = get_forced_tool(query)
        assert result is not None
        assert result["tool"] == "web_search"

    def test_case_insensitive_lookahead(self):
        """The negative lookahead must be case-insensitive since patterns
        are compiled with re.IGNORECASE."""
        result = get_forced_tool("search Wikipedia for Einstein")
        if result is not None:
            assert result["tool"] != "web_search"

    def test_args_still_extracted_for_generic_search(self):
        """Ensure the capture group still extracts the query text correctly
        after inserting the lookahead."""
        result = get_forced_tool("search for healthy dinner ideas")
        assert result is not None
        assert result["tool"] == "web_search"
        assert "healthy dinner ideas" in result["args"].get("query", "")
