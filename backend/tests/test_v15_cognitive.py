#!/usr/bin/env python3
"""
Sakura V15: Cognitive Architecture Tests
=========================================
Tests for DesireSystem, ProactiveScheduler, and mood injection.

Run with: pytest tests/test_v15_cognitive.py -v
"""

import pytest
import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDesireSystem:
    """Tests for DesireSystem (the heart)."""
    
    def test_import(self):
        """Can import DesireSystem."""
        from sakura_assistant.core.cognitive.desire import DesireSystem, get_desire_system
        assert DesireSystem is not None
        assert get_desire_system is not None
    
    def test_singleton(self):
        """DesireSystem is a singleton."""
        from sakura_assistant.core.cognitive.desire import get_desire_system
        ds1 = get_desire_system()
        ds2 = get_desire_system()
        assert ds1 is ds2
    
    def test_initial_state(self):
        """Initial state has full social battery."""
        from sakura_assistant.core.cognitive.desire import DesireSystem
        ds = DesireSystem.__new__(DesireSystem)
        ds._initialized = False
        ds.__init__()
        
        assert ds.state.social_battery == 1.0
        assert ds.state.loneliness == 0.0
        assert ds.state.curiosity == 0.3
    
    def test_user_message_drains_battery(self):
        """User message drains social battery."""
        from sakura_assistant.core.cognitive.desire import DesireSystem
        ds = DesireSystem.__new__(DesireSystem)
        ds._initialized = False
        ds.__init__()
        
        initial_battery = ds.state.social_battery
        ds.on_user_message("Hello, how are you?")
        
        assert ds.state.social_battery < initial_battery
        assert ds.state.loneliness < 0.3  # Should decrease
    
    def test_user_message_resets_loneliness(self):
        """User message resets loneliness."""
        from sakura_assistant.core.cognitive.desire import DesireSystem
        ds = DesireSystem.__new__(DesireSystem)
        ds._initialized = False
        ds.__init__()
        
        ds.state.loneliness = 0.9
        ds.on_user_message("I'm back!")
        
        assert ds.state.loneliness < 0.9
    
    def test_mood_prompt_generation(self):
        """Can generate mood prompt."""
        from sakura_assistant.core.cognitive.desire import get_desire_system
        ds = get_desire_system()
        
        prompt = ds.get_mood_prompt()
        
        assert "[MOOD:" in prompt
        assert len(prompt) > 10
    
    def test_mood_tired_when_low_battery(self):
        """Mood is TIRED when social battery is low."""
        from sakura_assistant.core.cognitive.desire import DesireSystem, Mood
        ds = DesireSystem.__new__(DesireSystem)
        ds._initialized = False
        ds.__init__()
        
        ds.state.social_battery = 0.1
        
        assert ds.get_mood() == Mood.TIRED
    
    def test_mood_melancholic_when_lonely(self):
        """Mood is MELANCHOLIC when loneliness is high."""
        from sakura_assistant.core.cognitive.desire import DesireSystem, Mood
        ds = DesireSystem.__new__(DesireSystem)
        ds._initialized = False
        ds.__init__()
        
        ds.state.loneliness = 0.8
        ds.state.social_battery = 0.5  # Not tired
        
        assert ds.get_mood() == Mood.MELANCHOLIC
    
    def test_should_initiate_false_when_not_lonely(self):
        """Should not initiate when loneliness is low."""
        from sakura_assistant.core.cognitive.desire import DesireSystem
        ds = DesireSystem.__new__(DesireSystem)
        ds._initialized = False
        ds.__init__()
        
        ds.state.loneliness = 0.3
        should_act, reason = ds.should_initiate()
        
        assert should_act is False
        assert "too low" in reason.lower()
    
    def test_should_initiate_false_when_already_initiated(self):
        """Should not initiate if already initiated today."""
        from sakura_assistant.core.cognitive.desire import DesireSystem
        ds = DesireSystem.__new__(DesireSystem)
        ds._initialized = False
        ds.__init__()
        
        ds.state.loneliness = 0.9
        ds.state.last_user_message = time.time() - 5 * 3600  # 5 hours ago
        ds.state.initiations_today = 1  # Already initiated
        
        should_act, reason = ds.should_initiate()
        
        assert should_act is False
        assert "limit" in reason.lower()


class TestProactiveScheduler:
    """Tests for ProactiveScheduler."""
    
    def test_import(self):
        """Can import ProactiveScheduler."""
        from sakura_assistant.core.cognitive.proactive import ProactiveScheduler, get_proactive_scheduler
        assert ProactiveScheduler is not None
        assert get_proactive_scheduler is not None
    
    def test_singleton(self):
        """ProactiveScheduler is a singleton."""
        from sakura_assistant.core.cognitive.proactive import get_proactive_scheduler
        ps1 = get_proactive_scheduler()
        ps2 = get_proactive_scheduler()
        assert ps1 is ps2
    
    def test_get_planned_initiations_empty(self):
        """Returns empty list when no file exists."""
        from sakura_assistant.core.cognitive.proactive import ProactiveScheduler
        ps = ProactiveScheduler.__new__(ProactiveScheduler)
        ps._initialized = False
        ps.__init__()
        ps.initiations_path = "/nonexistent/path.json"
        
        messages = ps.get_planned_initiations()
        
        assert messages == []
    
    def test_save_and_load_initiations(self, tmp_path):
        """Can save and load planned initiations."""
        from sakura_assistant.core.cognitive.proactive import ProactiveScheduler
        ps = ProactiveScheduler.__new__(ProactiveScheduler)
        ps._initialized = False
        ps.__init__()
        ps.initiations_path = str(tmp_path / "initiations.json")
        
        ps.save_planned_initiations(["Hello!", "How are you?", "Miss you!"])
        messages = ps.get_planned_initiations()
        
        assert len(messages) == 3
        assert "Hello!" in messages
    
    def test_pop_initiation(self, tmp_path):
        """Pop removes and returns first message."""
        from sakura_assistant.core.cognitive.proactive import ProactiveScheduler
        ps = ProactiveScheduler.__new__(ProactiveScheduler)
        ps._initialized = False
        ps.__init__()
        ps.initiations_path = str(tmp_path / "initiations.json")
        
        ps.save_planned_initiations(["First", "Second", "Third"])
        
        msg = ps.pop_initiation()
        assert msg == "First"
        
        remaining = ps.get_planned_initiations()
        assert len(remaining) == 2
        assert "First" not in remaining


class TestMoodInjection:
    """Tests for mood prompt injection."""
    
    def test_mood_in_graph_context(self):
        """Mood prompt should be injectable into graph context."""
        from sakura_assistant.core.cognitive.desire import get_desire_system
        ds = get_desire_system()
        
        mood_prompt = ds.get_mood_prompt()
        
        # Simulate what llm.py does
        graph_context = "[USER IDENTITY]\nTest user."
        enhanced = f"{mood_prompt}\n\n{graph_context}"
        
        assert "[MOOD:" in enhanced
        assert "[USER IDENTITY]" in enhanced


class TestSchedulerIntegration:
    """Tests for scheduler integration."""
    
    def test_schedule_cognitive_tasks_import(self):
        """Can import schedule_cognitive_tasks."""
        from sakura_assistant.core.scheduler import schedule_cognitive_tasks
        assert schedule_cognitive_tasks is not None
    
    def test_precompute_initiations_import(self):
        """Can import precompute_initiations."""
        from sakura_assistant.core.scheduler import precompute_initiations
        assert precompute_initiations is not None
    
    def test_run_hourly_desire_tick_import(self):
        """Can import run_hourly_desire_tick."""
        from sakura_assistant.core.scheduler import run_hourly_desire_tick
        assert run_hourly_desire_tick is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
