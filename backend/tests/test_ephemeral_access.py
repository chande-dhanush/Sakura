"""
FIX-05 Tests: query_ephemeral Availability
============================================
Verifies that query_ephemeral is universally available across all 
micro-toolsets so the Planner can retrieve Context Valve handles.
"""
import pytest
from sakura_assistant.core.routing.micro_toolsets import (
    UNIVERSAL_TOOLS,
    MICRO_TOOLSETS,
    get_micro_toolset
)


def _make_all_possible_tools():
    """Create mock tools for filtering."""
    class DummyTool:
        def __init__(self, name):
            self.name = name
            
    # Gather all potential tool names from the config
    all_names = set(UNIVERSAL_TOOLS)
    for category in MICRO_TOOLSETS.values():
        all_names.update(category["primary"])
        
    all_names.update(["web_search", "search_wikipedia", "search_arxiv", "get_news", "get_weather"])
    return [DummyTool(name) for name in all_names]


class TestEphemeralToolAvailability:
    
    def test_query_ephemeral_in_universal_tools(self):
        """1. query_ephemeral must be explicitly defined in UNIVERSAL_TOOLS."""
        assert "query_ephemeral" in UNIVERSAL_TOOLS, (
            "query_ephemeral must be in UNIVERSAL_TOOLS to guarantee it "
            "is never hidden from the Planner"
        )

    def test_ephemeral_tool_present_in_all_defined_intents(self):
        """2. For every known intent, the resolved toolset must include query_ephemeral."""
        all_tools = _make_all_possible_tools()
        
        for intent in MICRO_TOOLSETS.keys():
            micro_tools = get_micro_toolset(intent=intent, all_tools=all_tools)
            
            if micro_tools is not None:
                tool_names = [t.name for t in micro_tools]
                assert "query_ephemeral" in tool_names, (
                    f"query_ephemeral is missing from '{intent}' micro-toolset. "
                    f"Got tools: {tool_names}"
                )

    def test_ephemeral_tool_present_for_unknown_intents(self):
        """3. Even if intent is 'general' or unknown, query_ephemeral must be included."""
        all_tools = _make_all_possible_tools()
        
        micro_tools = get_micro_toolset(intent="general", all_tools=all_tools)
        if micro_tools is not None:
            tool_names = [t.name for t in micro_tools]
            assert "query_ephemeral" in tool_names, (
                f"query_ephemeral is missing from 'general' fallback toolset."
            )
            
        micro_tools_unknown = get_micro_toolset(intent="unknown_intent_xyz", all_tools=all_tools)
        if micro_tools_unknown is not None:
            tool_names = [t.name for t in micro_tools_unknown]
            assert "query_ephemeral" in tool_names, (
                f"query_ephemeral is missing from unknown intent toolset."
            )
