"""
FIX-03 Tests: Planner Anti-Hallucination Enforcement Gate
==========================================================
Verifies that the Planner retries once with enforcement when the LLM
answers from training data instead of calling tools. Also verifies
the gate does NOT fire when no tools are bound (CHAT path).
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool as langchain_tool

from sakura_assistant.core.execution.planner import Planner


#    Helpers                                                             

def _make_dummy_tools():
    """Create minimal LangChain tools for testing."""
    @langchain_tool
    def web_search(query: str) -> str:
        """Search the web for information."""
        return f"Results for: {query}"

    @langchain_tool
    def search_wikipedia(query: str) -> str:
        """Search Wikipedia for factual information."""
        return f"Wikipedia: {query}"

    return [web_search, search_wikipedia]


def _make_text_only_response(text: str = "Photosynthesis is the process..."):
    """Create an AIMessage that has NO tool_calls (hallucination)."""
    return AIMessage(content=text, tool_calls=[])


def _make_tool_call_response(tool_name: str = "web_search", args: dict = None):
    """Create an AIMessage WITH tool_calls (correct behavior)."""
    return AIMessage(
        content="",
        tool_calls=[{
            "name": tool_name,
            "args": args or {"query": "photosynthesis"},
            "id": "call_test123"
        }]
    )


def _make_mock_llm(responses):
    """Create a mock LLM that returns sequential responses.
    Supports both .invoke() and .ainvoke()."""
    call_count = {"n": 0}
    
    def _invoke(messages, **kwargs):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]
    
    async def _ainvoke(messages, **kwargs):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]
    
    mock = MagicMock()
    mock.invoke = MagicMock(side_effect=_invoke)
    mock.ainvoke = AsyncMock(side_effect=_ainvoke)
    mock.bind_tools = MagicMock(return_value=mock)
    mock._call_count = call_count
    return mock


#    Sync Tests                                                          

class TestPlannerEnforcementSync:
    """Sync plan() enforcement gate tests."""

    def test_enforcement_fires_when_tools_bound_but_no_calls(self):
        """When tools are bound but LLM returns text-only,
        enforcement retry must fire."""
        # First call: text-only (hallucination)
        # Second call (enforcement): tool call (correct)
        mock_llm = _make_mock_llm([
            _make_text_only_response(),
            _make_tool_call_response("web_search", {"query": "photosynthesis"})
        ])
        
        planner = Planner(llm=mock_llm)
        tools = _make_dummy_tools()
        result = planner.plan(
            user_input="What is photosynthesis?",
            available_tools=tools
        )
        
        # Should have produced tool call steps from the retry
        assert len(result["steps"]) > 0, "Enforcement should produce tool call steps"
        assert result["steps"][0]["tool"] == "web_search"
        assert result["complete"] is False
        
        # Verify LLM was called twice (original + enforcement retry)
        assert mock_llm._call_count["n"] == 2

    def test_enforcement_does_not_fire_without_tools(self):
        """When no tools are bound (CHAT path), enforcement must NOT fire."""
        mock_llm = _make_mock_llm([
            _make_text_only_response("I'm doing great, thanks!")
        ])
        
        planner = Planner(llm=mock_llm)
        result = planner.plan(
            user_input="How are you?",
            available_tools=None  # No tools = CHAT path
        )
        
        # Should complete normally without retry
        assert result["steps"] == []
        assert result["complete"] is True
        # LLM called only once (no enforcement)
        assert mock_llm._call_count["n"] == 1

    def test_enforcement_fails_gracefully_on_double_refusal(self):
        """If LLM refuses tools even after enforcement, fall through
        to complete=True (no infinite loop)."""
        mock_llm = _make_mock_llm([
            _make_text_only_response("First refusal"),
            _make_text_only_response("Second refusal")
        ])
        
        planner = Planner(llm=mock_llm)
        tools = _make_dummy_tools()
        result = planner.plan(
            user_input="What is quantum computing?",
            available_tools=tools
        )
        
        # Should fall through to complete=True after double refusal
        assert result["steps"] == []
        assert result["complete"] is True
        # LLM called exactly twice (original + enforcement, then stop)
        assert mock_llm._call_count["n"] == 2

    def test_tool_calls_on_first_try_skip_enforcement(self):
        """If LLM correctly calls tools on the first try,
        enforcement must NOT fire."""
        mock_llm = _make_mock_llm([
            _make_tool_call_response("search_wikipedia", {"query": "Einstein"})
        ])
        
        planner = Planner(llm=mock_llm)
        tools = _make_dummy_tools()
        result = planner.plan(
            user_input="Who is Einstein?",
            available_tools=tools
        )
        
        assert len(result["steps"]) == 1
        assert result["steps"][0]["tool"] == "search_wikipedia"
        assert result["complete"] is False
        # LLM called only once
        assert mock_llm._call_count["n"] == 1

    def test_enforcement_message_contains_tool_names(self):
        """Enforcement retry message must contain available tool names
        so the LLM knows what to call."""
        captured_messages = []
        
        def _invoke(messages, **kwargs):
            captured_messages.append(messages)
            if len(captured_messages) == 1:
                return _make_text_only_response()
            return _make_tool_call_response()
        
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(side_effect=_invoke)
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        
        planner = Planner(llm=mock_llm)
        tools = _make_dummy_tools()
        planner.plan(user_input="Define gravity", available_tools=tools)
        
        # Second call should have enforcement message
        assert len(captured_messages) == 2
        retry_msgs = captured_messages[1]
        enforcement_content = retry_msgs[-1].content
        assert "SYSTEM OVERRIDE" in enforcement_content
        assert "MUST call a tool" in enforcement_content
        assert "web_search" in enforcement_content
        assert "search_wikipedia" in enforcement_content


#    Async Tests                                                         

class TestPlannerEnforcementAsync:
    """Async aplan() enforcement gate tests."""

    def test_async_enforcement_fires_when_tools_bound(self):
        """Async path: enforcement retry must fire on hallucination."""
        mock_llm = _make_mock_llm([
            _make_text_only_response(),
            _make_tool_call_response("web_search", {"query": "AI"})
        ])
        
        planner = Planner(llm=mock_llm)
        tools = _make_dummy_tools()
        
        result = asyncio.run(
            planner.aplan(user_input="What is artificial intelligence?", available_tools=tools)
        )
        
        assert len(result["steps"]) > 0
        assert result["steps"][0]["tool"] == "web_search"
        assert mock_llm._call_count["n"] == 2

    def test_async_enforcement_does_not_fire_without_tools(self):
        """Async path: no enforcement when tools aren't bound."""
        mock_llm = _make_mock_llm([
            _make_text_only_response("Hello there!")
        ])
        
        planner = Planner(llm=mock_llm)
        
        result = asyncio.run(
            planner.aplan(user_input="Hi", available_tools=None)
        )
        
        assert result["steps"] == []
        assert result["complete"] is True
        assert mock_llm._call_count["n"] == 1

    def test_async_double_refusal_falls_through(self):
        """Async path: double refusal falls through to complete=True."""
        mock_llm = _make_mock_llm([
            _make_text_only_response("Training data answer 1"),
            _make_text_only_response("Training data answer 2")
        ])
        
        planner = Planner(llm=mock_llm)
        tools = _make_dummy_tools()
        
        result = asyncio.run(
            planner.aplan(user_input="Define entropy", available_tools=tools)
        )
        
        assert result["steps"] == []
        assert result["complete"] is True
        assert mock_llm._call_count["n"] == 2

    def test_async_empty_tools_list_does_not_fire(self):
        """Passing an empty tools list should NOT trigger enforcement
        (edge case: available_tools=[] is falsy)."""
        mock_llm = _make_mock_llm([
            _make_text_only_response("No tools needed here")
        ])
        
        planner = Planner(llm=mock_llm)
        
        result = asyncio.run(
            planner.aplan(user_input="Tell me a joke", available_tools=[])
        )
        
        assert result["steps"] == []
        assert result["complete"] is True
        # Empty list is falsy   no enforcement
        assert mock_llm._call_count["n"] == 1
