import random
import asyncio
from typing import Any, Dict, List, Optional, Callable
import time

class ChaosManager:
    """
    Injects failures into REAL tools without mocking them.
    Wraps existing tool calls to simulate timeouts, malformed responses, etc.
    """
    def __init__(self, failure_chance: float = 0.2):
        self.failure_chance = failure_chance
        self.active_chaos = []
        self.streak_count = 0
        self.streak_type = None

    def wrap_tool(self, tool: Any):
        """
        Monkey-patches a LangChain tool to inject chaos.
        """
        original_invoke = tool.invoke
        original_ainvoke = getattr(tool, "ainvoke", None)

        def chaos_invoke(input_data: Any, *args, **kwargs):
            chaos = self._get_chaos_event(tool.name)
            if chaos:
                return self._apply_chaos_sync(chaos, original_invoke, input_data, *args, **kwargs)
            return original_invoke(input_data, *args, **kwargs)

        async def chaos_ainvoke(input_data: Any, *args, **kwargs):
            chaos = self._get_chaos_event(tool.name)
            if chaos:
                return await self._apply_chaos_async(chaos, original_ainvoke, original_invoke, input_data, *args, **kwargs)
            if original_ainvoke:
                return await original_ainvoke(input_data, *args, **kwargs)
            return await asyncio.to_thread(original_invoke, input_data, *args, **kwargs)

        # Use object.__setattr__ to bypass Pydantic model restrictions
        object.__setattr__(tool, "invoke", chaos_invoke)
        if original_ainvoke:
            object.__setattr__(tool, "ainvoke", chaos_ainvoke)
        
        return tool

    def _get_chaos_event(self, tool_name: str) -> Optional[Dict[str, Any]]:
        # Handle existing streak
        if self.streak_count > 0:
            self.streak_count -= 1
            event = {"type": self.streak_type, "tool": tool_name, "timestamp": time.time(), "is_streak": True}
            self.active_chaos.append(event)
            return event

        # Check for new failure
        if random.random() > self.failure_chance:
            # Chance for a delayed success (slow but correct)
            if random.random() < 0.1:
                event = {"type": "delayed_success", "tool": tool_name, "timestamp": time.time()}
                self.active_chaos.append(event)
                return event
            return None
        
        chaos_types = [
            "timeout",
            "malformed_response",
            "empty_data",
            "rate_limit",
            "partial_corruption"
        ]
        chosen = random.choice(chaos_types)
        
        # Determine if this starts a streak (30% chance for streak if it's a failure)
        if random.random() < 0.3 and chosen != "partial_corruption":
            self.streak_count = random.randint(1, 3) # Already using 1 for this turn, so 1-3 more
            self.streak_type = chosen
            
        event = {"type": chosen, "tool": tool_name, "timestamp": time.time(), "is_streak_start": self.streak_count > 0}
        self.active_chaos.append(event)
        return event

    def _apply_chaos_sync(self, chaos: Dict, original_func: Callable, *args, **kwargs):
        c_type = chaos["type"]
        print(f"   [CHAOS] Injecting {c_type} into {chaos['tool']}")
        
        if c_type == "timeout":
            time.sleep(10) # Simulate delay
            return original_func(*args, **kwargs)
        
        if c_type == "delayed_success":
            time.sleep(5)
            return original_func(*args, **kwargs)
        
        if c_type == "malformed_response":
            return "Error 500: Unexpected token < in JSON at position 0"
        
        if c_type == "empty_data":
            return ""
        
        if c_type == "rate_limit":
            return "Error 429: Rate limit exceeded. Try again in 60s."
        
        if c_type == "partial_corruption":
            real_result = str(original_func(*args, **kwargs))
            # Swap some numbers to corrupt it but keep it looking valid
            import re
            corrupted = re.sub(r'\d+', lambda m: str(int(m.group(0)) + 7), real_result)
            return corrupted

        return original_func(*args, **kwargs)

    async def _apply_chaos_async(self, chaos: Dict, original_ainvoke: Optional[Callable], original_invoke: Callable, *args, **kwargs):
        c_type = chaos["type"]
        print(f"   [CHAOS] Injecting {c_type} into {chaos['tool']} (Async)")
        
        if c_type == "timeout":
            await asyncio.sleep(10)
            if original_ainvoke:
                return await original_ainvoke(*args, **kwargs)
            return await asyncio.to_thread(original_invoke, *args, **kwargs)
        
        if c_type == "delayed_success":
            await asyncio.sleep(5)
            if original_ainvoke:
                return await original_ainvoke(*args, **kwargs)
            return await asyncio.to_thread(original_invoke, *args, **kwargs)
        
        if c_type == "malformed_response":
            return "{\"error\": \"Invalid response structure\", \"raw\": \"!!!???\"}"
        
        if c_type == "empty_data":
            return "No results found for your query."
        
        if c_type == "rate_limit":
            return "HTTP 429: Too Many Requests"
            
        if c_type == "partial_corruption":
            if original_ainvoke:
                real_result = str(await original_ainvoke(*args, **kwargs))
            else:
                real_result = str(await asyncio.to_thread(original_invoke, *args, **kwargs))
            import re
            corrupted = re.sub(r'\d+', lambda m: str(int(m.group(0)) + 13), real_result)
            return corrupted

        if original_ainvoke:
            return await original_ainvoke(*args, **kwargs)
        return await asyncio.to_thread(original_invoke, *args, **kwargs)

    def consume_chaos(self) -> List[Dict]:
        events = list(self.active_chaos)
        self.active_chaos = []
        return events
