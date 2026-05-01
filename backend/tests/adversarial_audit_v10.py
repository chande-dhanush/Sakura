import sys
import os
import asyncio
import unittest
import json
from unittest.mock import MagicMock, AsyncMock

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Mock environment variable for control layer
os.environ["ENABLE_CONTROL_LAYER"] = "true"

from sakura_assistant.core.execution.executor import ReActLoop, ExecutionResult, ExecutionStatus

class MockPlanner:
    def __init__(self, plan_sequence):
        self.plan_sequence = plan_sequence
        self.call_count = 0
        self.llm = MagicMock()
    
    async def aplan(self, **kwargs):
        if self.call_count >= len(self.plan_sequence):
            return {"steps": []}
        plan = self.plan_sequence[self.call_count]
        self.call_count += 1
        return plan

class TestAdversarialHardening(unittest.IsolatedAsyncioTestCase):
    async def test_loop_guard_repeating_args(self):
        """Test Phase 1: Loop Guard terminates identical repeated calls."""
        # Planner keeps returning the same tool and args
        plan = {"steps": [{"tool": "web_search", "args": {"query": "test"}}]}
        planner = MockPlanner([plan, plan, plan])
        
        policy = MagicMock()
        policy.is_terminal.return_value = False
        loop = ReActLoop(
            planner=planner,
            tool_runner=MagicMock(),
            output_handler=MagicMock(),
            policy=policy
        )
        
        # Mock _aexecute_steps to return success but planner keeps looping
        loop._aexecute_steps = AsyncMock(return_value=ExecutionResult(
            outputs="Search result", 
            tool_messages=[], 
            tool_used="web_search",
            last_result={"success": True},
            status=ExecutionStatus.SUCCESS
        ))
        
        result = await loop.arun(user_input="search for test", ctx=None)
        
        # Should terminate with loop detection error
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIn("Catastrophic loop detected", result.outputs)
        self.assertEqual(planner.call_count, 2) # Second call should trigger guard

    async def test_max_attempts_per_tool(self):
        """Test Phase 2: max_attempts_per_tool = 1 enforced."""
        # Planner tries same tool with different args
        plan1 = {"steps": [{"tool": "web_search", "args": {"query": "test1"}}]}
        plan2 = {"steps": [{"tool": "web_search", "args": {"query": "test2"}}]}
        planner = MockPlanner([plan1, plan2])
        
        policy = MagicMock()
        policy.is_terminal.return_value = False
        loop = ReActLoop(
            planner=planner,
            tool_runner=MagicMock(),
            output_handler=MagicMock(),
            policy=policy
        )
        
        loop._aexecute_steps = AsyncMock(return_value=ExecutionResult(
            outputs="No results", 
            tool_messages=[], 
            tool_used="web_search",
            last_result={"success": False},
            status=ExecutionStatus.PARTIAL
        ))
        
        result = await loop.arun(user_input="search for test", ctx=None)
        
        # Should terminate with max attempts error
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIn("Maximum attempts reached for tool: web_search", result.outputs)

    async def test_rate_limit_early_exit(self):
        """Test Phase 2: RATE_LIMITED tool outcome triggers early exit."""
        # Tool returns RATE_LIMITED
        plan = {"steps": [{"tool": "web_search", "args": {"query": "test"}}]}
        planner = MockPlanner([plan, plan])
        
        policy = MagicMock()
        policy.is_terminal.return_value = False
        loop = ReActLoop(
            planner=planner,
            tool_runner=MagicMock(),
            output_handler=MagicMock(),
            policy=policy
        )
        
        loop._aexecute_steps = AsyncMock(return_value=ExecutionResult(
            outputs="Rate limited", 
            tool_messages=[], 
            tool_used="web_search",
            last_result={"success": False},
            status=ExecutionStatus.RATE_LIMITED
        ))
        
        result = await loop.arun(user_input="search for test", ctx=None)
        
        # Should exit immediately after first RATE_LIMITED result
        self.assertEqual(planner.call_count, 1)
        self.assertEqual(result.status, ExecutionStatus.RATE_LIMITED)

    async def test_progress_detection(self):
        """Test Phase 1: Progress Detection stops loop if no new info."""
        # Planner tries different tools but output length doesn't change
        plan1 = {"steps": [{"tool": "tool1", "args": {}}]}
        plan2 = {"steps": [{"tool": "tool2", "args": {}}]}
        planner = MockPlanner([plan1, plan2])
        
        policy = MagicMock()
        policy.is_terminal.return_value = False
        loop = ReActLoop(
            planner=planner,
            tool_runner=MagicMock(),
            output_handler=MagicMock(),
            policy=policy
        )
        
        # First call gains info, second call gains nothing
        loop._aexecute_steps = AsyncMock()
        loop._aexecute_steps.side_effect = [
            ExecutionResult(outputs="Some info", tool_messages=[], tool_used="tool1", last_result={}, status=ExecutionStatus.PARTIAL),
            ExecutionResult(outputs="Some info", tool_messages=[], tool_used="tool2", last_result={}, status=ExecutionStatus.PARTIAL)
        ]
        
        result = await loop.arun(user_input="test", ctx=None)
        
        # Should terminate after second call due to no progress
        self.assertEqual(planner.call_count, 2)
        # Note: break in loop means it returns the collected outputs
        self.assertIn("Some info", result.outputs)

if __name__ == "__main__":
    unittest.main()
