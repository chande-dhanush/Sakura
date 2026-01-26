"""
Test Suite: Container Module
============================
Tests for the DI container.
"""
import unittest
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestLLMConfig(unittest.TestCase):
    """Test LLMConfig dataclass."""
    
    def test_default_values(self):
        """Test LLMConfig default values."""
        from sakura_assistant.core.infrastructure.container import LLMConfig
        
        config = LLMConfig()
        
        self.assertEqual(config.router_model, "llama-3.1-8b-instant")
        self.assertEqual(config.planner_model, "llama-3.3-70b-versatile")
        self.assertEqual(config.router_temp, 0.0)
        self.assertEqual(config.timeout, 60)
        self.assertTrue(config.enable_cache)
    
    def test_custom_values(self):
        """Test LLMConfig with custom values."""
        from sakura_assistant.core.infrastructure.container import LLMConfig
        
        config = LLMConfig(
            router_model="custom-model",
            timeout=30
        )
        
        self.assertEqual(config.router_model, "custom-model")
        self.assertEqual(config.timeout, 30)


class TestContainer(unittest.TestCase):
    """Test Container dependency injection."""
    
    def setUp(self):
        """Reset container before each test."""
        from sakura_assistant.core.infrastructure.container import reset_container
        reset_container()
    
    def test_get_container_singleton(self):
        """Test get_container returns same instance."""
        from sakura_assistant.core.infrastructure.container import get_container
        
        c1 = get_container()
        c2 = get_container()
        
        self.assertIs(c1, c2)
    
    def test_reset_container(self):
        """Test reset_container clears instance."""
        from sakura_assistant.core.infrastructure.container import get_container, reset_container
        
        c1 = get_container()
        reset_container()
        c2 = get_container()
        
        self.assertIsNot(c1, c2)
    
    def test_has_api_keys_detection(self):
        """Test API key detection from environment."""
        from sakura_assistant.core.infrastructure.container import Container
        
        # Without any env vars set explicitly
        container = Container()
        
        # These may or may not be set depending on environment
        # Just verify the properties work
        self.assertIsInstance(container.has_groq, bool)
        self.assertIsInstance(container.has_openrouter, bool)
        self.assertIsInstance(container.has_backup, bool)


if __name__ == "__main__":
    unittest.main()
