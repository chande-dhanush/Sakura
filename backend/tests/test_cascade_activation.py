"""
FIX-04 Tests: Search Cascade Activation
=========================================
Verifies that Tier-1 search failures trigger the unlocking of Tier-2 tools.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from sakura_assistant.core.execution.executor import ReActLoop, _is_empty_or_failed
from sakura_assistant.core.execution.context import ExecutionResult, ExecutionStatus

class TestSearchCascadeUnit:
    def test_is_empty_or_failed_empty_strings(self):
        """1. _is_empty_or_failed('') -> True"""
        assert _is_empty_or_failed("") is True
        assert _is_empty_or_failed("   ") is True

    def test_is_empty_or_failed_no_results(self):
        """2. _is_empty_or_failed('No results found for your query') -> True"""
        assert _is_empty_or_failed("No results found for your query") is True
        assert _is_empty_or_failed("0 results") is True

    def test_is_empty_or_failed_disambiguation(self):
        """3. _is_empty_or_failed('may refer to several topics') -> True"""
        assert _is_empty_or_failed("Target may refer to several topics") is True

    def test_is_empty_or_failed_valid_article(self):
        """4. _is_empty_or_failed('Photosynthesis is the process by which...') -> False"""
        assert _is_empty_or_failed("Photosynthesis is the process by which plants make food.") is False

    def test_is_empty_or_failed_normal_output(self):
        """5. _is_empty_or_failed('Here are the results: ...') -> False"""
        assert _is_empty_or_failed("Here are the results: 1. A, 2. B") is False


class MockTool:
    def __init__(self, name):
        self.name = name

class TestCascadeIntegration:
    def _make_loop(self, execute_steps_responses):
        # We need tool_map so we can unlock everything if cascade triggers
        mock_runner = MagicMock()
        mock_runner.tool_map = {
            "search_wikipedia": MockTool("search_wikipedia"),
            "search_arxiv": MockTool("search_arxiv"),
            "web_search": MockTool("web_search")
        }
        
        planner = MagicMock()
        planner.captured_tools = []
        async def mock_aplan(*args, **kwargs):
            # Capture available_tools
            planner.captured_tools.append(kwargs.get("available_tools"))
            
            # Stop loop if we exhausted responses
            if len(planner.captured_tools) > len(execute_steps_responses):
                return {"steps": [], "complete": True}
            return {"steps": [{"tool": "dummy"}], "complete": False}
            
        planner.aplan = mock_aplan
        
        policy_mock = MagicMock()
        policy_mock.is_terminal.return_value = False
        
        loop = ReActLoop(
            planner=planner,
            tool_runner=mock_runner,
            output_handler=MagicMock(),
            policy=policy_mock
        )
        
        loop._aexecute_steps = AsyncMock(side_effect=execute_steps_responses)
        return loop, planner

    def test_wikipedia_failure_unlocks_web_search(self):
        """6. Mock search_wikipedia to return 'No article found' -> assert web_search becomes available."""
        exec_res = ExecutionResult(
            outputs="No article found", 
            tool_messages=[MagicMock()], 
            tool_used="search_wikipedia",
            last_result={},
            status=ExecutionStatus.SUCCESS
        )
        loop, planner = self._make_loop([exec_res])
        initial_tools = [MockTool("search_wikipedia")]
        
        asyncio.run(loop.arun(user_input="explain quantum chaos", available_tools=initial_tools))
        
        assert len(planner.captured_tools) == 2
        iter1_tool_names = [t.name for t in planner.captured_tools[0]]
        iter2_tool_names = [t.name for t in planner.captured_tools[1]]
        
        assert "web_search" not in iter1_tool_names
        assert "web_search" in iter2_tool_names

    def test_wikipedia_success_no_cascade(self):
        """7. string: Mock search_wikipedia to return a valid article -> assert cascade does NOT activate."""
        exec_res = ExecutionResult(
            outputs="Photosynthesis is the process... [article content]", 
            tool_messages=[MagicMock()], 
            tool_used="search_wikipedia",
            last_result={},
            status=ExecutionStatus.SUCCESS
        )
        loop, planner = self._make_loop([exec_res])
        initial_tools = [MockTool("search_wikipedia")]
        
        asyncio.run(loop.arun(user_input="what is photosynthesis", available_tools=initial_tools))
        
        assert len(planner.captured_tools) == 2
        iter1_tool_names = [t.name for t in planner.captured_tools[0]]
        iter2_tool_names = [t.name for t in planner.captured_tools[1]]
        
        assert "web_search" not in iter2_tool_names

    def test_cascade_activates_only_once(self):
        """8. Integration: cascade activates once on first failure, assert it does NOT activate again."""
        exec1 = ExecutionResult(outputs="0 results", tool_messages=[], tool_used="search_wikipedia", last_result={}, status=ExecutionStatus.SUCCESS)
        exec2 = ExecutionResult(outputs="0 results", tool_messages=[], tool_used="search_arxiv", last_result={}, status=ExecutionStatus.SUCCESS)
        
        loop, planner = self._make_loop([exec1, exec2])
        initial_tools = [MockTool("search_wikipedia")]
        
        asyncio.run(loop.arun(user_input="super obscure string", available_tools=initial_tools))
        
        assert len(planner.captured_tools) == 3
        
        iter1_len = len(planner.captured_tools[0])
        iter2_len = len(planner.captured_tools[1])
        iter3_len = len(planner.captured_tools[2])
        
        assert iter2_len > iter1_len  # Exploded
        assert iter3_len == iter2_len  # Stayed the same


class TestCascadeSyncParity:
    def _make_loop_sync(self, execute_steps_responses):
        mock_runner = MagicMock()
        mock_runner.tool_map = {
            "search_wikipedia": MockTool("search_wikipedia"),
            "search_arxiv": MockTool("search_arxiv"),
            "web_search": MockTool("web_search")
        }
        
        planner = MagicMock()
        planner.captured_tools = []
        def mock_plan(*args, **kwargs):
            planner.captured_tools.append(kwargs.get("available_tools"))
            if len(planner.captured_tools) > len(execute_steps_responses):
                return {"steps": [], "complete": True}
            return {"steps": [{"tool": "dummy"}], "complete": False}
            
        planner.plan = mock_plan
        
        policy_mock = MagicMock()
        policy_mock.is_terminal.return_value = False
        
        loop = ReActLoop(
            planner=planner,
            tool_runner=mock_runner,
            output_handler=MagicMock(),
            policy=policy_mock
        )
        
        loop._execute_steps = MagicMock(side_effect=execute_steps_responses)
        return loop, planner

    def test_sync_wikipedia_failure_unlocks_web_search(self):
        """Sync path triggers cascade on Wikipedia failure identical to async path."""
        exec_res = ExecutionResult(
            outputs="No article found", 
            tool_messages=[MagicMock()], 
            tool_used="search_wikipedia",
            last_result={},
            status=ExecutionStatus.SUCCESS
        )
        loop, planner = self._make_loop_sync([exec_res])
        initial_tools = [MockTool("search_wikipedia")]
        
        # Monkeypatch ctx to avoid NameError inside the unmaintained sync run() method
        import sakura_assistant.core.execution.executor as executor_mod
        executor_mod.ctx = None
        
        loop.run(user_input="explain quantum chaos", graph_context="", available_tools=initial_tools)
        
        assert len(planner.captured_tools) == 2
        iter1_tool_names = [t.name for t in planner.captured_tools[0]]
        iter2_tool_names = [t.name for t in planner.captured_tools[1]]
        
        assert "web_search" not in iter1_tool_names
        assert "web_search" in iter2_tool_names
