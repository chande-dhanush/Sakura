"""
Test Suite: Executor Module
===========================
Tests for the ToolExecutor class.
"""
import unittest
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockTool:
    """Mock tool for testing."""
    def __init__(self, name: str, result: str = "OK"):
        self.name = name
        self._result = result
    
    def invoke(self, args: dict) -> str:
        return self._result


class FailingTool:
    """Tool that always fails."""
    def __init__(self, name: str):
        self.name = name
    
    def invoke(self, args: dict) -> str:
        raise Exception("Tool failed intentionally")


class TestToolExecutor(unittest.TestCase):
    """Test ToolExecutor functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Import the executor."""
        from sakura_assistant.core.executor import ToolExecutor, ExecutionResult
        cls.ToolExecutor = ToolExecutor
        cls.ExecutionResult = ExecutionResult
    
    def test_execute_single_success(self):
        """Test single tool execution success."""
        tools = [MockTool("test_tool", "Success!")]
        executor = self.ToolExecutor(tools)
        
        result, success = executor.execute_single("test_tool", {})
        
        self.assertTrue(success)
        self.assertEqual(result, "Success!")
    
    def test_execute_single_not_found(self):
        """Test single tool execution with missing tool."""
        executor = self.ToolExecutor([])
        
        result, success = executor.execute_single("missing_tool", {})
        
        self.assertFalse(success)
        self.assertIn("not found", result)
    
    def test_execute_plan_success(self):
        """Test plan execution with multiple tools."""
        tools = [
            MockTool("tool_a", "Result A"),
            MockTool("tool_b", "Result B"),
        ]
        executor = self.ToolExecutor(tools)
        
        steps = [
            {"id": 1, "tool": "tool_a", "args": {}},
            {"id": 2, "tool": "tool_b", "args": {}},
        ]
        
        result = executor.execute_plan(steps)
        
        self.assertTrue(result.success)
        self.assertEqual(result.tool_used, "tool_b")
        self.assertIn("Result A", result.outputs)
        self.assertIn("Result B", result.outputs)
        self.assertEqual(len(result.tool_messages), 2)
    
    def test_execute_plan_partial_failure(self):
        """Test plan execution with one failing tool."""
        tools = [
            MockTool("good_tool", "OK"),
            FailingTool("bad_tool"),
        ]
        executor = self.ToolExecutor(tools)
        
        steps = [
            {"id": 1, "tool": "good_tool", "args": {}},
            {"id": 2, "tool": "bad_tool", "args": {}},
        ]
        
        result = executor.execute_plan(steps)
        
        self.assertFalse(result.success)  # Overall failure
        self.assertIn("Error", result.outputs)
    
    def test_execute_plan_max_iterations(self):
        """Test that plan execution respects max_iterations."""
        tools = [MockTool(f"tool_{i}", f"Result {i}") for i in range(10)]
        executor = self.ToolExecutor(tools)
        
        steps = [{"id": i, "tool": f"tool_{i}", "args": {}} for i in range(10)]
        
        result = executor.execute_plan(steps, max_iterations=3)
        
        # Should only execute 3 steps
        self.assertEqual(len(result.tool_messages), 3)
    
    def test_prune_output_short(self):
        """Test that short outputs are not pruned."""
        executor = self.ToolExecutor([])
        
        short_text = "This is a short output."
        result = executor.prune_output(short_text)
        
        self.assertEqual(result, short_text)
    
    def test_prune_output_long_text(self):
        """Test that long text is truncated."""
        executor = self.ToolExecutor([])
        
        long_text = "x" * 2000
        result = executor.prune_output(long_text, max_chars=100)
        
        self.assertLess(len(result), 200)
        self.assertIn("TRUNCATED", result)
    
    def test_prune_output_json(self):
        """Test JSON-aware pruning."""
        executor = self.ToolExecutor([])
        
        large_json = '{"html_body": "' + "x" * 5000 + '", "title": "Test"}'
        result = executor.prune_output(large_json, max_chars=500)
        
        # Should prune html_body but keep title
        self.assertIn("title", result)
        self.assertLess(len(result), 600)


class TestExecutionResult(unittest.TestCase):
    """Test ExecutionResult dataclass."""
    
    def test_dataclass_fields(self):
        """Test ExecutionResult has correct fields."""
        from sakura_assistant.core.executor import ExecutionResult
        
        result = ExecutionResult(
            outputs="test output",
            tool_messages=[],
            tool_used="test_tool",
            last_result={"tool": "test_tool", "success": True},
            success=True
        )
        
        self.assertEqual(result.outputs, "test output")
        self.assertEqual(result.tool_used, "test_tool")
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
