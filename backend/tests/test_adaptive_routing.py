"""
Adaptive Routing Test Suite
===========================
Tests for urgency detection and routing with urgency.

Run: pytest sakura_assistant/tests/test_adaptive_routing.py -v
"""

import pytest
import sys
import os

# Add parent path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sakura_assistant.core.router import get_urgency, RouteResult


class TestUrgencyDetection:
    """Test urgency detection from query text."""
    
    def test_urgent_keyword_detection(self):
        """Queries with urgent keywords should be flagged URGENT."""
        urgent_queries = [
            "I need this urgently",
            "ASAP please check my email",
            "This is an emergency",
            "Hurry up and find this",
            "Quick! What's the weather?",
            "Immediately send this email",
        ]
        
        for query in urgent_queries:
            urgency = get_urgency(query)
            assert urgency == "URGENT", f"Expected URGENT for '{query}', got {urgency}"
    
    def test_normal_queries(self):
        """Normal queries should return NORMAL."""
        normal_queries = [
            "What's the weather in Tokyo?",
            "Play some music",
            "Tell me about quantum physics",
            "Search for restaurants nearby",
            "When is my next meeting?",
        ]
        
        for query in normal_queries:
            urgency = get_urgency(query)
            assert urgency == "NORMAL", f"Expected NORMAL for '{query}', got {urgency}"
    
    def test_case_insensitive(self):
        """Urgency detection should be case insensitive."""
        assert get_urgency("URGENT: check email") == "URGENT"
        assert get_urgency("Urgent: check email") == "URGENT"
        assert get_urgency("urgent: check email") == "URGENT"


class TestRouteResultWithUrgency:
    """Test RouteResult class with urgency field."""
    
    def test_route_result_default_urgency(self):
        """Default urgency should be NORMAL."""
        result = RouteResult("CHAT")
        assert result.urgency == "NORMAL"
        assert result.is_urgent == False
    
    def test_route_result_urgent(self):
        """URGENT result should have is_urgent=True."""
        result = RouteResult("DIRECT", "gmail_read_email", "URGENT")
        assert result.urgency == "URGENT"
        assert result.is_urgent == True
    
    def test_route_result_properties(self):
        """Test classification properties."""
        direct = RouteResult("DIRECT", "get_weather")
        plan = RouteResult("PLAN")
        chat = RouteResult("CHAT")
        
        assert direct.needs_tools == True
        assert direct.needs_planning == False
        
        assert plan.needs_tools == True
        assert plan.needs_planning == True
        
        assert chat.needs_tools == False
        assert chat.needs_planning == False


class TestForcedRouterPatterns:
    """Test code interpreter patterns in forced_router."""
    
    def test_analyze_data_pattern(self):
        """'analyze data' should route to execute_python."""
        from sakura_assistant.core.forced_router import get_forced_tool
        
        result = get_forced_tool("analyze this data file")
        assert result is not None
        assert result["tool"] == "execute_python"
    
    def test_plot_pattern(self):
        """'plot' queries should route to execute_python."""
        from sakura_assistant.core.forced_router import get_forced_tool
        
        result = get_forced_tool("plot my sales data")
        assert result is not None
        assert result["tool"] == "execute_python"
    
    def test_calculate_stats_pattern(self):
        """Stats calculations should route to execute_python."""
        from sakura_assistant.core.forced_router import get_forced_tool
        
        for query in ["calculate the mean", "compute the average", "calculate statistics"]:
            result = get_forced_tool(query)
            assert result is not None, f"No match for '{query}'"
            assert result["tool"] == "execute_python", f"Wrong tool for '{query}'"
    
    def test_run_python_pattern(self):
        """'run python' should route to execute_python."""
        from sakura_assistant.core.forced_router import get_forced_tool
        
        result = get_forced_tool("run this python code")
        assert result is not None
        assert result["tool"] == "execute_python"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
