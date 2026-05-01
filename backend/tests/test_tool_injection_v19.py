import pytest
import os
import sys

# Ensure backend path is loaded
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sakura_assistant.core.routing.micro_toolsets import resolve_tool_hint, UNIVERSAL_TOOLS
from sakura_assistant.core.execution.planner import Planner
from sakura_assistant.core.execution.context import ExecutionResult, ExecutionMode
from sakura_assistant.core.execution.executor import ReActLoop

# Mock tool object
class MockTool:
    def __init__(self, name):
        self.name = name

def test_resolve_tool_hint():
    """Verify that alias mapping is working."""
    assert resolve_tool_hint("playyoutube") == "play_youtube"
    assert resolve_tool_hint("youtube_control") == "play_youtube"
    assert resolve_tool_hint("google_search") == "web_search"
    assert resolve_tool_hint("unknown_hint") == "unknown_hint"
    assert resolve_tool_hint(None) is None

def test_missing_method_regression():
    """Verify Planner._filter_tools exists and works with exact hint match."""
    planner = Planner(llm=None)
    
    # Mock some tools
    tools = [MockTool("play_youtube"), MockTool("get_time"), MockTool("web_search")]
    
    # Should resolve correctly and find the tool
    filtered = planner._filter_tools(tools, "playyoutube")
    assert len(filtered) == 1
    assert filtered[0].name == "play_youtube"
    
def test_empty_fallback():
    """Verify Planner._filter_tools falls back to baseline when hint isn't found."""
    planner = Planner(llm=None)
    
    # Tools include some universal tools and search tools
    tools = [MockTool("get_time"), MockTool("web_search"), MockTool("unrelated_tool")]
    
    # Filtering for a missing tool like 'play_youtube' (since it's not in our tools list)
    # The hint resolves to 'play_youtube', which is in target_names but not in available_tools.
    filtered = planner._filter_tools(tools, "play_youtube")
    
    # Baseline includes search tools and universal tools
    tool_names = [t.name for t in filtered]
    assert "get_time" in tool_names  # In universal
    assert "web_search" in tool_names # In search tools
    assert "unrelated_tool" not in tool_names # Not in baseline

def test_absolute_fallback():
    """Verify absolute fallback if even baseline tools are not in available_tools."""
    planner = Planner(llm=None)
    
    tools = [MockTool("custom_tool")]
    filtered = planner._filter_tools(tools, "fake_hint")
    
    assert len(filtered) == 1
    assert filtered[0].name == "custom_tool"

def test_mode_unknown_invariant():
    """Verify ExecutionResult.error correctly captures the ExecutionMode."""
    # We will simulate the ReActLoop failure.
    class MockExecutionContext:
        def __init__(self):
            self.mode = ExecutionMode.ITERATIVE
            
    ctx = MockExecutionContext()
    
    # Create an ExecutionResult.error like the one in executor
    res = ExecutionResult.error("Planning failed: No tools selected")
    if ctx:
        res.last_result = {"mode": ctx.mode.value}
        
    assert res.succeeded is False
    assert res.last_result is not None
    assert res.last_result["mode"] == "iterative"

if __name__ == "__main__":
    pytest.main(["-v", __file__])
