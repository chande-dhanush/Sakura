"""
FIX-07 Tests: Responder Tool-Result Fidelity Check
===================================================
Verifies the Responder does not silently ignore factual tool data.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from langchain_core.messages import AIMessage
from sakura_assistant.core.models.responder import ResponseGenerator, ResponseContext

class TestResponderFidelity:
    
    def _make_generator(self, responses):
        mock_llm = MagicMock()
        resp_funcs = [AIMessage(content=r) for r in responses]
        call_count = {"n": 0}
        
        def _invoke(*args, **kwargs):
            idx = min(call_count["n"], len(resp_funcs) - 1)
            call_count["n"] += 1
            return resp_funcs[idx]
            
        async def _ainvoke(*args, **kwargs):
            idx = min(call_count["n"], len(resp_funcs) - 1)
            call_count["n"] += 1
            return resp_funcs[idx]
            
        mock_llm.invoke = MagicMock(side_effect=_invoke)
        mock_llm.ainvoke = AsyncMock(side_effect=_ainvoke)
        
        gen = ResponseGenerator(llm=mock_llm, personality="You are AI.")
        return gen, mock_llm, call_count

    def test_fidelity_passes_when_data_referenced(self):
        """1. When tool_outputs contains '28°C Partly Cloudy' and response contains '28' 
        or 'cloudy' -> fidelity check passes, no regeneration."""
        gen, mock_llm, counter = self._make_generator(["The temperature is 28°C and it's cloudy."])
        
        # Must be >50 chars to trigger fidelity check
        tool_output = "Weather Data: 28°C Partly Cloudy. Location: Bangalore, India. Additional padding so length is >50 chars for the check."
        context = ResponseContext(user_input="weather", tool_outputs=tool_output)
        
        result = gen.generate(context)
        
        assert counter["n"] == 1
        assert "28°C" in result

    def test_fidelity_fails_triggers_regeneration(self):
        """2. When response ignores data -> fidelity fails, regeneration fires exactly once."""
        gen, mock_llm, counter = self._make_generator([
            "It has a warm tropical climate", # Ignition: Hallucination 
            "The weather in Bangalore is 28°C."      # Retry: Grounded
        ])
        
        tool_output = "Weather Data: 28°C Partly Cloudy. Location: Bangalore, India. Additional padding so length is >50 chars for the check."
        context = ResponseContext(user_input="weather", tool_outputs=tool_output)
        
        result = gen.generate(context)
        
        assert counter["n"] == 2
        assert "28" in result

    def test_fidelity_skipped_on_empty_tools(self):
        """3. When tool_outputs is empty -> fidelity check is skipped entirely."""
        gen, mock_llm, counter = self._make_generator(["Just chatting here!"])
        
        context = ResponseContext(user_input="hi", tool_outputs="")
        
        result = gen.generate(context)
        
        assert counter["n"] == 1

    def test_fidelity_fires_at_most_once(self):
        """4. Regeneration fires at most once per response (no infinite loop)."""
        gen, mock_llm, counter = self._make_generator([
            "It is a nice place.",
            "It is located in Asia."
        ])
        
        tool_output = "Weather Data: 28°C Partly Cloudy. Location: Bangalore, India. Additional padding so length is >50 chars for the check."
        context = ResponseContext(user_input="weather", tool_outputs=tool_output)
        
        result = gen.generate(context)
        
        assert counter["n"] == 2

    def test_async_fidelity_fails_triggers_regeneration(self):
        """Ensure the async path also executes fidelity correctly."""
        gen, mock_llm, counter = self._make_generator([
            "It has a warm tropical climate", 
            "The weather in Bangalore is 28°C."      
        ])
        
        tool_output = "Weather Data: 28°C Partly Cloudy. Location: Bangalore, India. Additional padding so length is >50 chars for the check."
        context = ResponseContext(user_input="weather", tool_outputs=tool_output)
        
        import asyncio
        result = asyncio.run(gen.agenerate(context))
        
        assert counter["n"] == 2
        assert "28" in result
