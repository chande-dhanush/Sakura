"""
Test Suite: Responder Module
=============================
Tests for the ResponseGenerator class.
"""
import unittest
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestResponseGenerator(unittest.TestCase):
    """Test ResponseGenerator validation and guardrails."""
    
    @classmethod
    def setUpClass(cls):
        """Import the responder."""
        from sakura_assistant.core.models.responder import ResponseGenerator, ResponseContext
        cls.ResponseGenerator = ResponseGenerator
        cls.ResponseContext = ResponseContext
    
    def test_validate_output_clean(self):
        """Test clean output passes validation."""
        generator = self.ResponseGenerator(llm=None, personality="")
        
        text = "Here is your answer: The weather is sunny today."
        result, had_violation = generator.validate_output(text)
        
        self.assertEqual(result, text)
        self.assertFalse(had_violation)
    
    def test_validate_output_tool_json(self):
        """Test tool-call JSON is stripped."""
        generator = self.ResponseGenerator(llm=None, personality="")
        
        text = 'Let me help. {"name": "get_weather", "args": {"city": "NYC"}}'
        result, had_violation = generator.validate_output(text)
        
        self.assertTrue(had_violation)
        self.assertNotIn("name", result.lower())
    
    def test_validate_output_function_pattern(self):
        """Test function pattern is stripped."""
        generator = self.ResponseGenerator(llm=None, personality="")
        
        text = 'I will call: {"function": "search", "params": {}}'
        result, had_violation = generator.validate_output(text)
        
        self.assertTrue(had_violation)
    
    def test_check_action_claim_false_email(self):
        """Test false email claim detection."""
        generator = self.ResponseGenerator(llm=None, personality="")
        
        # False claim without tool execution
        response = "I have sent your email successfully!"
        result = generator._check_action_claim(response)
        
        self.assertIn("wasn't able to take any action", result)
    
    def test_check_action_claim_false_event(self):
        """Test false event claim detection."""
        generator = self.ResponseGenerator(llm=None, personality="")
        
        response = "The event has been created on your calendar."
        result = generator._check_action_claim(response)
        
        self.assertIn("wasn't able to take any action", result)
    
    def test_check_action_claim_legit(self):
        """Test legitimate responses pass through."""
        generator = self.ResponseGenerator(llm=None, personality="")
        
        response = "I can help you with that. What would you like to do?"
        result = generator._check_action_claim(response)
        
        self.assertEqual(result, response)
    
    def test_check_action_claim_playing_now(self):
        """Test 'playing now' detection."""
        generator = self.ResponseGenerator(llm=None, personality="")
        
        response = "Playing now: Your favorite song!"
        result = generator._check_action_claim(response)
        
        self.assertIn("wasn't able to take any action", result)


class TestResponseContext(unittest.TestCase):
    """Test ResponseContext dataclass."""
    
    def test_default_values(self):
        """Test ResponseContext defaults."""
        from sakura_assistant.core.models.responder import ResponseContext
        
        context = ResponseContext(user_input="Hello")
        
        self.assertEqual(context.user_input, "Hello")
        self.assertEqual(context.tool_outputs, "")
        self.assertEqual(context.history, [])
        self.assertEqual(context.current_mood, "Neutral")
        self.assertFalse(context.study_mode)
    
    def test_with_history(self):
        """Test ResponseContext with history."""
        from sakura_assistant.core.models.responder import ResponseContext
        
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"}
        ]
        
        context = ResponseContext(
            user_input="How are you?",
            history=history
        )
        
        self.assertEqual(len(context.history), 2)


class TestContextBuilding(unittest.TestCase):
    """Test context building for response generation."""
    
    def test_build_compact_context_empty(self):
        """Test compact context with empty history."""
        from sakura_assistant.core.models.responder import ResponseGenerator
        
        generator = ResponseGenerator(llm=None, personality="")
        result = generator._build_compact_context([], "test input")
        
        self.assertEqual(result, "")
    
    def test_build_compact_context_with_history(self):
        """Test compact context with history."""
        from sakura_assistant.core.models.responder import ResponseGenerator
        
        generator = ResponseGenerator(llm=None, personality="")
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        
        result = generator._build_compact_context(history, "test input")
        
        self.assertIn("<CONTEXT>", result)
        self.assertIn("user: Hello", result)
        self.assertIn("assistant: Hi there!", result)


if __name__ == "__main__":
    unittest.main()
