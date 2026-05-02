"""
Sakura V10.4: Async Token Bucket Rate Limiter
==============================================
Implements backpressure-based rate limiting for API calls.

Instead of crashing on 429, induces latency via asyncio.sleep().
Per-model limits based on free tier quotas.
"""
import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class RateLimitConfig:
    """Configuration for a rate-limited model."""
    rpm: int           # Requests per minute (steady state)
    burst: int         # Max concurrent burst (bucket capacity)
    tpm: int = 0       # Tokens per minute (0 = unlimited)
    context_window: int = 8192  # Max context size in tokens
    name: str = ""     # Display name for logging


class TokenBucket:
    """
    Token bucket algorithm for rate limiting.
    
    Refills at rate (rpm/60) tokens per second.
    Burst allows initial fast requests before throttling kicks in.
    """
    
    def __init__(self, config: RateLimitConfig):
        self.rate = config.rpm / 60.0  # Tokens per second
        self.capacity = float(config.burst)
        self.tokens = float(config.burst)  # Start full
        self.last_refill = time.monotonic()
        self.name = config.name
        self.tpm_limit = config.tpm
        self.context_limit = config.context_window
        self._lock = asyncio.Lock()
        
        # TPM tracking (resets every minute)
        self.tokens_used_this_minute = 0
        self.minute_start = time.monotonic()
        
        # Stats for observability
        self.total_requests = 0
        self.total_wait_time = 0.0
        self.total_tokens_used = 0
    
    async def acquire(self, cost: int = 1, token_count: int = 0) -> float:
        """
        Acquire tokens, sleeping if necessary.
        
        Returns:
            Wait time in seconds
        """
        wait_time = 0.0
        
        # 1. TPM check
        if self.tpm_limit > 0 and token_count > 0:
            while True:
                async with self._lock:
                    self._reset_minute_if_needed()
                    if self.tokens_used_this_minute + token_count <= self.tpm_limit:
                        self.tokens_used_this_minute += token_count
                        self.total_tokens_used += token_count
                        break
                    
                    time_in_minute = time.monotonic() - self.minute_start
                    sleep_time = 60.0 - time_in_minute + 0.1
                
                if sleep_time > 0:
                    print(f" [RL] model={self.name} wait={sleep_time:.1f}s (TPM Limit)")
                    from .broadcaster import broadcast
                    broadcast("rate_limit", {"model": self.name, "wait_time": sleep_time, "reason": "TPM Limit"})
                    await asyncio.sleep(sleep_time)
                    wait_time += sleep_time

        # 2. RPM check (token bucket)
        while True:
            async with self._lock:
                self._refill()
                
                if self.tokens >= cost:
                    self.tokens -= cost
                    self.total_requests += 1
                    if wait_time == 0:
                        print(f" [RL] model={self.name} immediate")
                    return wait_time
                
                deficit = cost - self.tokens
                sleep_time = deficit / self.rate
            
            print(f" [RL] model={self.name} wait={sleep_time:.2f}s (RPM Limit)")
            from .broadcaster import broadcast
            broadcast("rate_limit", {"model": self.name, "wait_time": sleep_time, "reason": "RPM Limit"})
            await asyncio.sleep(sleep_time)
            wait_time += sleep_time
            self.total_wait_time += sleep_time

    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        new_tokens = elapsed * self.rate
        
        if new_tokens > 0:
            self.tokens = min(self.capacity, self.tokens + new_tokens)
            self.last_refill = now
    
    def _reset_minute_if_needed(self):
        """Reset TPM counter if minute has elapsed."""
        now = time.monotonic()
        if now - self.minute_start >= 60.0:
            self.tokens_used_this_minute = 0
            self.minute_start = now
    
    def check_context_limit(self, token_count: int) -> bool:
        """Check if token count exceeds context window."""
        return token_count <= self.context_limit
    
    def get_stats(self) -> Dict:
        """Return limiter statistics for observability."""
        return {
            "name": self.name,
            "total_requests": self.total_requests,
            "total_wait_time_s": round(self.total_wait_time, 2),
            "total_tokens_used": self.total_tokens_used,
            "current_tokens": round(self.tokens, 2),
            "capacity": self.capacity,
            "tpm_limit": self.tpm_limit,
            "context_limit": self.context_limit,
        }


class ModelRateLimiter:
    """
    Registry of per-model token buckets.
    Ensures isolation between different models/providers.
    """
    
    # Model-specific rate limits
    MODEL_LIMITS = {
        "llama-3.3-70b-versatile": RateLimitConfig(rpm=30, burst=5, tpm=25000, context_window=128000, name="Llama-70B"),
        "llama-3.1-8b-instant": RateLimitConfig(rpm=30, burst=10, tpm=16000, context_window=128000, name="Llama-8B"),
        "gemini-2.0-flash": RateLimitConfig(rpm=15, burst=3, tpm=1000000, context_window=1000000, name="Gemini-Flash"),
        "gemini-2.0-flash-exp:free": RateLimitConfig(rpm=15, burst=3, tpm=1000000, context_window=1000000, name="Gemini-Flash"),
        "google/gemini-2.0-flash-exp:free": RateLimitConfig(rpm=15, burst=3, tpm=100000, context_window=128000, name="OR-Gemini"),
        "openai/gpt-oss-20b": RateLimitConfig(rpm=30, burst=5, tpm=8000, context_window=8192, name="OR-GPT"),
        "deepseek-chat": RateLimitConfig(rpm=1000, burst=10, tpm=1000000, context_window=64000, name="DeepSeek-Chat"),
        "deepseek-reasoner": RateLimitConfig(rpm=50, burst=5, tpm=100000, context_window=64000, name="DeepSeek-Reasoner"),
    }
    
    DEFAULT_LIMIT = RateLimitConfig(rpm=8, burst=2, tpm=3000, context_window=8192, name="Unknown")
    
    def __init__(self):
        self.buckets: Dict[str, TokenBucket] = {}
        self._enabled = True
    
    def get_bucket(self, model_name: str) -> TokenBucket:
        """Get or create a token bucket for the given model."""
        if model_name not in self.buckets:
            config = self.MODEL_LIMITS.get(model_name, self.DEFAULT_LIMIT)
            if config == self.DEFAULT_LIMIT:
                config = RateLimitConfig(
                    rpm=self.DEFAULT_LIMIT.rpm,
                    burst=self.DEFAULT_LIMIT.burst,
                    name=model_name[:20]
                )
            self.buckets[model_name] = TokenBucket(config)
            print(f" [RL] Created bucket for {model_name}")
        
        return self.buckets[model_name]
    
    async def acquire(self, model_name: str, cost: int = 1) -> float:
        """Acquire permission to make an API call for a specific model."""
        if not self._enabled:
            return 0.0
        bucket = self.get_bucket(model_name)
        return await bucket.acquire(cost)
    
    def disable(self): self._enabled = False
    def enable(self): self._enabled = True
    def get_all_stats(self) -> Dict[str, Dict]:
        return {name: bucket.get_stats() for name, bucket in self.buckets.items()}


# Singleton instance registry
_limiter: Optional[ModelRateLimiter] = None

def get_rate_limiter() -> ModelRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = ModelRateLimiter()
    return _limiter

async def acquire_rate_limit(model_name: str, cost: int = 1) -> float:
    return await get_rate_limiter().acquire(model_name, cost)
