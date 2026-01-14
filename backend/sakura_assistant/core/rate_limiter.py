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
        
        Args:
            cost: Number of request tokens (usually 1)
            token_count: Estimated tokens for this request (for TPM tracking)
        
        Returns:
            Wait time in seconds (0 if no wait needed)
        """
        async with self._lock:
            wait_time = 0.0
            
            # TPM check (if limit is set and token count provided)
            if self.tpm_limit > 0 and token_count > 0:
                self._reset_minute_if_needed()
                
                if self.tokens_used_this_minute + token_count > self.tpm_limit:
                    # Wait until minute resets
                    time_in_minute = time.monotonic() - self.minute_start
                    sleep_time = 60.0 - time_in_minute + 0.1
                    
                    if sleep_time > 0:
                        print(f"⏳ [RateLimiter:{self.name}] TPM limit hit, waiting {sleep_time:.1f}s")
                        
                        # V12: Broadcast throttling event
                        from .broadcaster import broadcast
                        broadcast("rate_limit", {
                            "model": self.name,
                            "wait_time": sleep_time,
                            "reason": "TPM Limit"
                        })
                        
                        self._lock.release()
                        await asyncio.sleep(sleep_time)
                        await self._lock.acquire()
                        wait_time += sleep_time
                        self._reset_minute_if_needed()
                
                self.tokens_used_this_minute += token_count
                self.total_tokens_used += token_count
            
            # RPM check (token bucket)
            while True:
                self._refill()
                
                if self.tokens >= cost:
                    self.tokens -= cost
                    self.total_requests += 1
                    return wait_time
                
                # Calculate wait time for deficit
                deficit = cost - self.tokens
                sleep_time = deficit / self.rate
                
                print(f"⏳ [RateLimiter:{self.name}] RPM backpressure: waiting {sleep_time:.2f}s")
                
                # V12: Broadcast throttling event
                from .broadcaster import broadcast
                broadcast("rate_limit", {
                    "model": self.name,
                    "wait_time": sleep_time,
                    "reason": "RPM Limit"
                })
                
                self._lock.release()
                await asyncio.sleep(sleep_time)
                await self._lock.acquire()
                
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


class GlobalRateLimiter:
    """
    Singleton rate limiter managing per-model buckets.
    
    VERIFIED Groq Free Tier Limits (Jan 2025):
    - Llama 3.3 70B: 30 RPM, 1000 TPM, 128K context
    - Llama 3.1 8B: 30 RPM, 20000 TPM, 128K context
    - Gemma2 9B: 30 RPM, 15000 TPM, 8K context
    
    Google Gemini Free Tier:
    - Gemini 2.0 Flash: 15 RPM, 1M TPM, 1M context
    """
    
    # Model-specific rate limits (VERIFIED from Groq console Jan 2026)
    MODEL_LIMITS = {
        # Groq models
        "llama-3.3-70b-versatile": RateLimitConfig(
            rpm=30, burst=5, tpm=10000, context_window=128000, name="Llama-70B"
        ),
        "llama-3.1-8b-instant": RateLimitConfig(
            rpm=30, burst=10, tpm=16000, context_window=128000, name="Llama-8B"
        ),
        
        # Google Gemini (generous free tier)
        "gemini-2.0-flash": RateLimitConfig(
            rpm=15, burst=3, tpm=1000000, context_window=1000000, name="Gemini-Flash"
        ),
        "gemini-2.0-flash-exp:free": RateLimitConfig(
            rpm=15, burst=3, tpm=1000000, context_window=1000000, name="Gemini-Flash"
        ),
        
        # OpenRouter models (user-verified limits)
        "google/gemini-2.0-flash-exp:free": RateLimitConfig(
            rpm=15, burst=3, tpm=100000, context_window=128000, name="OR-Gemini"
        ),
        "openai/gpt-oss-20b": RateLimitConfig(
            rpm=30, burst=5, tpm=8000, context_window=8192, name="OR-GPT"
        ),
    }
    
    # Default for unknown models (conservative)
    DEFAULT_LIMIT = RateLimitConfig(rpm=8, burst=2, tpm=3000, context_window=8192, name="Unknown")
    
    def __init__(self):
        self.buckets: Dict[str, TokenBucket] = {}
        self._enabled = True
    
    def get_bucket(self, model_name: str) -> TokenBucket:
        """Get or create a token bucket for the given model."""
        if model_name not in self.buckets:
            config = self.MODEL_LIMITS.get(model_name, self.DEFAULT_LIMIT)
            # Update name if using default
            if config == self.DEFAULT_LIMIT:
                config = RateLimitConfig(
                    rpm=self.DEFAULT_LIMIT.rpm,
                    burst=self.DEFAULT_LIMIT.burst,
                    name=model_name[:20]
                )
            self.buckets[model_name] = TokenBucket(config)
            print(f"🪣 [RateLimiter] Created bucket for {model_name}: {config.rpm} RPM, burst={config.burst}")
        
        return self.buckets[model_name]
    
    async def acquire(self, model_name: str, cost: int = 1) -> float:
        """
        Acquire permission to make an API call.
        
        Args:
            model_name: The model being called
            cost: Number of tokens to consume (default 1)
            
        Returns:
            Wait time in seconds
        """
        if not self._enabled:
            return 0.0
        
        bucket = self.get_bucket(model_name)
        return await bucket.acquire(cost)
    
    def disable(self):
        """Disable rate limiting (for testing)."""
        self._enabled = False
        print("⚠️ [RateLimiter] DISABLED")
    
    def enable(self):
        """Enable rate limiting."""
        self._enabled = True
        print("✅ [RateLimiter] ENABLED")
    
    def get_all_stats(self) -> Dict[str, Dict]:
        """Get statistics for all buckets."""
        return {name: bucket.get_stats() for name, bucket in self.buckets.items()}


# Singleton instance
_limiter: Optional[GlobalRateLimiter] = None


def get_rate_limiter() -> GlobalRateLimiter:
    """Get the global rate limiter instance."""
    global _limiter
    if _limiter is None:
        _limiter = GlobalRateLimiter()
    return _limiter


# Convenience function
async def acquire_rate_limit(model_name: str, cost: int = 1) -> float:
    """Acquire rate limit permission for a model."""
    return await get_rate_limiter().acquire(model_name, cost)
