"""
FIX-01 Tests: Router Parse Failure & Exception Fallback
========================================================
Verifies that parse failures and exceptions now default to PLAN
(with web_search hint for exceptions) instead of silently
routing to CHAT, which would suppress all tool invocation.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sakura_assistant.core.routing.router import IntentRouter, RouteResult


class TestParseResponseFallback:
    """Tests for _parse_response() defaulting to PLAN on JSON failure."""

    def _make_router(self):
        return IntentRouter(llm=None)

    def test_valid_json_direct(self):
        """Valid JSON with DIRECT classification should work normally."""
        router = self._make_router()
        classification, hint = router._parse_response(
            '{"classification": "DIRECT", "tool_hint": "get_weather"}'
        )
        assert classification == "DIRECT"
        assert hint == "get_weather"

    def test_valid_json_plan(self):
        """Valid JSON with PLAN classification should work normally."""
        router = self._make_router()
        classification, hint = router._parse_response(
            '{"classification": "PLAN", "tool_hint": "web_search"}'
        )
        assert classification == "PLAN"
        assert hint == "web_search"

    def test_valid_json_chat(self):
        """Valid JSON with CHAT classification should work normally."""
        router = self._make_router()
        classification, hint = router._parse_response(
            '{"classification": "CHAT", "tool_hint": null}'
        )
        assert classification == "CHAT"

    def test_garbage_response_defaults_plan(self):
        """Totally unparseable response must default to PLAN (not CHAT)."""
        router = self._make_router()
        classification, hint = router._parse_response("I think this is a search query...")
        # V18 FIX-01: default changed from CHAT to PLAN
        assert classification == "PLAN", (
            f"Garbage response should default to PLAN, got {classification}"
        )

    def test_malformed_json_defaults_plan(self):
        """Broken JSON should default to PLAN (not CHAT)."""
        router = self._make_router()
        classification, hint = router._parse_response('{"classification": "DIRECT", "tool_')
        assert classification == "PLAN"

    def test_empty_response_defaults_plan(self):
        """Empty response should default to PLAN (not CHAT)."""
        router = self._make_router()
        classification, hint = router._parse_response("")
        assert classification == "PLAN"

    def test_complex_in_response_still_returns_plan(self):
        """Legacy 'complex' keyword still maps to PLAN."""
        router = self._make_router()
        classification, hint = router._parse_response("This is a complex task")
        assert classification == "PLAN"

    def test_simple_in_response_still_returns_chat(self):
        """Legacy 'simple' keyword still maps to CHAT."""
        router = self._make_router()
        classification, hint = router._parse_response("This is a simple greeting")
        assert classification == "CHAT"

    def test_markdown_wrapped_json_parses(self):
        """JSON wrapped in ```json ... ``` should parse correctly."""
        router = self._make_router()
        response = '```json\n{"classification": "DIRECT", "tool_hint": "get_weather"}\n```'
        classification, hint = router._parse_response(response)
        assert classification == "DIRECT"
        assert hint == "get_weather"


class TestRouteExceptionFallback:
    """Tests for aroute()/route() exception handling defaulting to PLAN."""

    def _make_router_with_failing_llm(self):
        """Create a router whose LLM raises an exception."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API connection error")
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("API connection error"))
        return IntentRouter(llm=mock_llm)

    def test_sync_route_exception_returns_plan(self):
        """Sync route() exception must return PLAN with web_search hint."""
        router = self._make_router_with_failing_llm()
        # Use a query that isn't an action command (so it reaches LLM path)
        result = router.route("What is quantum computing?")
        assert result.classification == "PLAN", (
            f"Exception should default to PLAN, got {result.classification}"
        )
        assert result.tool_hint == "web_search", (
            f"Exception should provide web_search hint, got {result.tool_hint}"
        )

    def test_async_route_exception_returns_plan(self):
        """Async aroute() exception must return PLAN with web_search hint."""
        router = self._make_router_with_failing_llm()
        result = asyncio.run(
            router.aroute("What is quantum computing?")
        )
        assert result.classification == "PLAN"
        assert result.tool_hint == "web_search"

    def test_exception_preserves_urgency(self):
        """Urgency detection should still work even when LLM fails."""
        router = self._make_router_with_failing_llm()
        result = router.route("Urgently find the nearest hospital")
        # "urgently" triggers URGENT detection + "find" triggers action command
        # so this may take the action command path.
        # Use a query without action verbs:
        result = router.route("I need urgent help with something strange")
        assert result.urgency == "URGENT"
        # Should still be PLAN (exception path)
        assert result.classification == "PLAN"

    def test_action_command_bypasses_llm_failure(self):
        """Action commands go through heuristic path, not LLM, so they
        should still work even when LLM is broken."""
        router = self._make_router_with_failing_llm()
        result = router.route("play Bohemian Rhapsody")
        assert result.classification == "DIRECT"
        assert result.tool_hint == "spotify_control"
