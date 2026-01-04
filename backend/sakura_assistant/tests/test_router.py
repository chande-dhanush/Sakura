"""
Test Suite: Router Module
=========================
Tests for the IntentRouter class.
"""
import unittest
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestIntentRouter(unittest.TestCase):
    """Test IntentRouter functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Import the router."""
        from sakura_assistant.core.router import IntentRouter, RouteResult
        cls.IntentRouter = IntentRouter
        cls.RouteResult = RouteResult
    
    def test_route_result_needs_tools(self):
        """Test RouteResult.needs_tools property."""
        direct = self.RouteResult("DIRECT", "spotify_control")
        plan = self.RouteResult("PLAN", "web_search")
        chat = self.RouteResult("CHAT")
        
        self.assertTrue(direct.needs_tools)
        self.assertTrue(plan.needs_tools)
        self.assertFalse(chat.needs_tools)
    
    def test_route_result_needs_planning(self):
        """Test RouteResult.needs_planning property."""
        direct = self.RouteResult("DIRECT")
        plan = self.RouteResult("PLAN")
        chat = self.RouteResult("CHAT")
        
        self.assertFalse(direct.needs_planning)
        self.assertTrue(plan.needs_planning)
        self.assertFalse(chat.needs_planning)
    
    def test_is_action_command_music(self):
        """Test action command detection for music."""
        # Create router with mock LLM (won't be called for action commands)
        router = self.IntentRouter(llm=None)
        
        self.assertTrue(router._is_action_command("play music"))
        self.assertTrue(router._is_action_command("pause"))
        self.assertTrue(router._is_action_command("skip to next"))
        self.assertTrue(router._is_action_command("queue this song"))
    
    def test_is_action_command_apps(self):
        """Test action command detection for apps."""
        router = self.IntentRouter(llm=None)
        
        self.assertTrue(router._is_action_command("open chrome"))
        self.assertTrue(router._is_action_command("launch spotify"))
        self.assertTrue(router._is_action_command("start notepad"))
    
    def test_is_action_command_search(self):
        """Test action command detection for search."""
        router = self.IntentRouter(llm=None)
        
        self.assertTrue(router._is_action_command("search for python tutorials"))
        self.assertTrue(router._is_action_command("find restaurants nearby"))
        self.assertTrue(router._is_action_command("google best laptops"))
    
    def test_is_action_command_negative(self):
        """Test that chat messages are not action commands."""
        router = self.IntentRouter(llm=None)
        
        self.assertFalse(router._is_action_command("hello"))
        self.assertFalse(router._is_action_command("what is the meaning of life"))
        self.assertFalse(router._is_action_command("can you explain quantum physics"))
        self.assertFalse(router._is_action_command("I like playing games"))
    
    def test_guess_tool_hint(self):
        """Test tool hint guessing."""
        router = self.IntentRouter(llm=None)
        
        self.assertEqual(router._guess_tool_hint("play some music"), "spotify_control")
        self.assertEqual(router._guess_tool_hint("check the weather"), "get_weather")
        self.assertEqual(router._guess_tool_hint("set a timer for 5 min"), "set_timer")
        self.assertEqual(router._guess_tool_hint("search for news"), "web_search")
    
    def test_parse_response_json(self):
        """Test JSON response parsing."""
        router = self.IntentRouter(llm=None)
        
        # Valid JSON
        classification, hint = router._parse_response('{"classification": "DIRECT", "tool_hint": "get_weather"}')
        self.assertEqual(classification, "DIRECT")
        self.assertEqual(hint, "get_weather")
        
        # With markdown code block
        classification, hint = router._parse_response('```json\n{"classification": "PLAN", "tool_hint": null}\n```')
        self.assertEqual(classification, "PLAN")
        self.assertIsNone(hint)
    
    def test_parse_response_fallback(self):
        """Test fallback parsing for non-JSON responses."""
        router = self.IntentRouter(llm=None)
        
        # Old format fallback
        classification, hint = router._parse_response("This is a COMPLEX query")
        self.assertEqual(classification, "PLAN")
        
        classification, hint = router._parse_response("This is SIMPLE")
        self.assertEqual(classification, "CHAT")
        
        # Invalid format
        classification, hint = router._parse_response("random text")
        self.assertEqual(classification, "CHAT")  # Default


class TestRouterIntegration(unittest.TestCase):
    """Integration tests for router with mocked LLM."""
    
    def test_route_action_command_no_llm(self):
        """Action commands should not need LLM call."""
        from sakura_assistant.core.router import IntentRouter
        
        router = IntentRouter(llm=None)  # No LLM
        result = router.route("play some music")
        
        self.assertEqual(result.classification, "DIRECT")
        self.assertEqual(result.tool_hint, "spotify_control")


if __name__ == "__main__":
    unittest.main()
