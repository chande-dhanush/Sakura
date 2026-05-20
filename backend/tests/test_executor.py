"""
Test Suite: Executor Module & OneShotRunner (Sakura Lite)
========================================================
"""
import unittest
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sakura_assistant.core.execution.executor import validate_path, SecurityError
from sakura_assistant.core.execution.oneshot_runner import OneShotRunner
from sakura_assistant.core.execution.context import ExecutionContext, ExecutionResult, ExecutionStatus, ExecutionMode


class MockTool:
    """Mock tool for testing."""
    def __init__(self, name: str, result: str = "OK"):
        self.name = name
        self._result = result
    
    def invoke(self, args: dict) -> str:
        return self._result

    async def ainvoke(self, args: dict) -> str:
        return self._result


class MockLLM:
    """Mock LLM for testing."""
    def __init__(self, response: str = ""):
        self.response = response
    def invoke(self, *args, **kwargs):
        return self.response
    async def ainvoke(self, *args, **kwargs):
        from langchain_core.messages import AIMessage
        return AIMessage(content=self.response)
    def bind_tools(self, tools):
        return self


class TestPathValidation(unittest.TestCase):
    """Test path validation and sanitization security gates."""
    
    def test_safe_paths(self):
        """Verify safe paths pass validation."""
        self.assertTrue(len(validate_path("notes/my_note.txt")) > 0)
        self.assertTrue(len(validate_path("data/world_graph.json")) > 0)
        
    def test_dangerous_paths(self):
        """Verify dangerous paths raise SecurityError."""
        with self.assertRaises(SecurityError):
            validate_path("../../../etc/passwd")
            
        with self.assertRaises(SecurityError):
            validate_path("c:\\windows\\system32\\cmd.exe")


class TestOneShotRunner(unittest.TestCase):
    """Test OneShotRunner execution pipeline."""

    def test_execute_not_found(self):
        """Test executing a tool that does not exist in map."""
        runner = OneShotRunner(tool_map={}, llm=MockLLM())
        ctx = ExecutionContext.create(
            mode=ExecutionMode.ONE_SHOT,
            request_id="test_req",
            user_input="test input"
        )
        
        # Running via asyncio.run since aexecute is async
        import asyncio
        result = asyncio.run(runner.aexecute("missing_tool", ctx))
        
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIn("not found", result.outputs)

    def test_execute_success(self):
        """Test successful execution with regex/mock tool."""
        mock_tool = MockTool("get_system_info", "CPU 10%")
        runner = OneShotRunner(tool_map={"get_system_info": mock_tool}, llm=MockLLM())
        ctx = ExecutionContext.create(
            mode=ExecutionMode.ONE_SHOT,
            request_id="test_req",
            user_input="get system info"
        )
        
        import asyncio
        result = asyncio.run(runner.aexecute("get_system_info", ctx))
        
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(result.tool_used, "get_system_info")


class TestMultiStepPlanner(unittest.TestCase):
    """Test MultiStepPlanner execution pipeline."""

    def test_execute_success(self):
        """Test successful planning loop where tool is executed."""
        from sakura_assistant.core.execution.planner import MultiStepPlanner
        from langchain_core.messages import AIMessage
        
        class MockPlanningLLM:
            def __init__(self):
                self.calls = 0
            def bind_tools(self, tools):
                return self
            async def ainvoke(self, messages):
                self.calls += 1
                if self.calls == 1:
                    # Request tool call
                    msg = AIMessage(content="Let's run the tool.")
                    msg.tool_calls = [{
                        "name": "get_system_info",
                        "args": {},
                        "id": "call_123"
                    }]
                    return msg
                else:
                    # Return final text
                    return AIMessage(content="The CPU is 10%. Done.")
        
        mock_tool = MockTool("get_system_info", "CPU 10%")
        planner = MultiStepPlanner(tool_map={"get_system_info": mock_tool}, llm=MockPlanningLLM())
        ctx = ExecutionContext.create(
            mode=ExecutionMode.ITERATIVE,
            request_id="test_req",
            user_input="how is the system status?"
        )
        
        import asyncio
        result = asyncio.run(planner.aexecute(ctx))
        
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(result.tool_used, "get_system_info")
        self.assertIn("The CPU is 10%. Done.", result.outputs)


if __name__ == "__main__":
    unittest.main()
