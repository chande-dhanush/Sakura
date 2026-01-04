"""
Sakura V10: Smart Cache Manager

Simple TTL-based dict cache for tool results.
Prevents redundant API calls for weather, search, etc.

Usage:
    from .cache_manager import cache_get, cache_set

    # Check cache before calling tool
    cached = cache_get("get_weather", {"city": "Tokyo"})
    if cached:
        return cached
    
    # After tool execution, store result
    result = tool.execute(...)
    cache_set("get_weather", {"city": "Tokyo"}, result)
"""
import time
from typing import Optional, Any, Dict

# TTL in seconds per tool type
CACHE_TTL = {
    "get_weather": 1800,          # 30 mins (weather changes slowly)
    "web_search": 86400,          # 24 hours (facts don't change fast)
    "search_wikipedia": 86400,    # 24 hours
    "get_news": 3600,             # 1 hour (news updates)
    "define_word": 604800,        # 7 days (definitions are stable)
}

# In-memory cache store
_tool_cache: Dict[str, Dict] = {}


def _make_key(tool_name: str, args: dict) -> str:
    """Generate cache key from tool name and args."""
    # Sort args for consistent hashing
    sorted_args = tuple(sorted((k, v) for k, v in args.items() if v))
    return f"{tool_name}:{hash(sorted_args)}"


def cache_get(tool_name: str, args: dict) -> Optional[Any]:
    """
    Get cached result if exists and not expired.
    
    Args:
        tool_name: Name of the tool (e.g., "get_weather")
        args: Tool arguments dict
        
    Returns:
        Cached result if valid, None otherwise
    """
    if tool_name not in CACHE_TTL:
        return None  # Tool not cacheable
    
    key = _make_key(tool_name, args)
    
    if key in _tool_cache:
        entry = _tool_cache[key]
        age = time.time() - entry["time"]
        
        if age < CACHE_TTL[tool_name]:
            print(f"⚡ [Cache] HIT: {tool_name} (age: {age:.0f}s)")
            return entry["result"]
        else:
            # Expired, clean up
            print(f"🗑️ [Cache] EXPIRED: {tool_name} (age: {age:.0f}s)")
            del _tool_cache[key]
    
    return None


def cache_set(tool_name: str, args: dict, result: Any) -> None:
    """
    Store result in cache if tool is cacheable.
    
    Args:
        tool_name: Name of the tool
        args: Tool arguments dict
        result: Result to cache
    """
    if tool_name not in CACHE_TTL:
        return  # Tool not cacheable
    
    # Don't cache errors
    if isinstance(result, str) and any(err in result.lower() for err in ["error", "failed", "exception"]):
        print(f"⚠️ [Cache] SKIP: {tool_name} (error result)")
        return
    
    key = _make_key(tool_name, args)
    _tool_cache[key] = {
        "result": result,
        "time": time.time()
    }
    print(f"💾 [Cache] SET: {tool_name} (TTL: {CACHE_TTL[tool_name]}s)")


def cache_clear() -> int:
    """Clear all cache entries. Returns number of entries cleared."""
    global _tool_cache
    count = len(_tool_cache)
    _tool_cache = {}
    print(f"🧹 [Cache] CLEARED: {count} entries")
    return count


def cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    now = time.time()
    stats = {
        "total_entries": len(_tool_cache),
        "entries_by_tool": {},
        "memory_estimate_kb": 0
    }
    
    for key, entry in _tool_cache.items():
        tool_name = key.split(":")[0]
        stats["entries_by_tool"][tool_name] = stats["entries_by_tool"].get(tool_name, 0) + 1
        # Rough memory estimate
        stats["memory_estimate_kb"] += len(str(entry.get("result", ""))) / 1024
    
    return stats
