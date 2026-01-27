"""
Reliable LLM Wrapper
====================
Provides a failover-safe wrapper for LLM calls with timeout protection.
Handles primary/backup switching and specific provider error recovery (e.g., Groq XML leaks).

V17.4: Added token tracking and cost logging to FlightRecorder.

Extracted from llm.py.
"""
import concurrent.futures
import time
import re
import json
import uuid
from typing import Optional, List, Any, Dict
from langchain_core.messages import AIMessage

# Timeout in seconds
LLM_TIMEOUT = 60


def _extract_tokens(result: Any, messages: Any = None, model: str = "unknown") -> Dict[str, int]:
    """
    V17.5: Extract token usage from LLM response with precise counting fallback.
    
    Handles multiple LangChain response formats:
    - usage_metadata (newer LangChain)
    - response_metadata.token_usage (older LangChain)
    - llm_output.token_usage (alternative format)
    - Groq-specific response.usage
    
    If API doesn't report tokens, uses model-specific tokenizer for precise counting.
    """
    tokens = {"prompt": 0, "completion": 0, "total": 0}
    
    try:
        # Format 1: LangChain newer (usage_metadata)
        if hasattr(result, 'usage_metadata') and result.usage_metadata:
            usage = result.usage_metadata
            tokens = {
                "prompt": usage.get('input_tokens', 0),
                "completion": usage.get('output_tokens', 0),
                "total": usage.get('total_tokens', 0)
            }
            # Fallback total calculation
            if tokens["total"] == 0:
                tokens["total"] = tokens["prompt"] + tokens["completion"]
            if tokens["total"] > 0:
                return tokens
        
        # Format 2: LangChain older (response_metadata.token_usage)
        if hasattr(result, 'response_metadata') and result.response_metadata:
            if 'token_usage' in result.response_metadata:
                usage = result.response_metadata['token_usage']
                tokens = {
                    "prompt": usage.get('prompt_tokens', 0),
                    "completion": usage.get('completion_tokens', 0),
                    "total": usage.get('total_tokens', 0)
                }
                if tokens["total"] == 0:
                    tokens["total"] = tokens["prompt"] + tokens["completion"]
                if tokens["total"] > 0:
                    return tokens
        
        # Format 3: llm_output (alternative)
        if hasattr(result, 'llm_output') and result.llm_output:
            usage = result.llm_output.get('token_usage', {})
            tokens = {
                "prompt": usage.get('prompt_tokens', 0),
                "completion": usage.get('completion_tokens', 0),
                "total": usage.get('total_tokens', 0)
            }
            if tokens["total"] == 0:
                tokens["total"] = tokens["prompt"] + tokens["completion"]
            if tokens["total"] > 0:
                return tokens
        
        # Format 4: Groq-specific (response.usage)
        if hasattr(result, 'response') and hasattr(result.response, 'usage'):
            usage = result.response.usage
            tokens = {
                "prompt": getattr(usage, 'prompt_tokens', 0),
                "completion": getattr(usage, 'completion_tokens', 0),
                "total": getattr(usage, 'total_tokens', 0)
            }
            if tokens["total"] == 0:
                tokens["total"] = tokens["prompt"] + tokens["completion"]
            if tokens["total"] > 0:
                return tokens
        
        # V17.5: If API didn't report tokens, use precise token counting
        if tokens["total"] == 0 and messages is not None:
            try:
                from ...utils.token_counter import count_tokens
                
                # Count prompt tokens from messages
                prompt_tokens = count_tokens(messages, model)
                
                # Count completion tokens from result
                completion_text = ""
                if hasattr(result, 'content'):
                    completion_text = result.content
                elif hasattr(result, 'text'):
                    completion_text = result.text
                else:
                    completion_text = str(result)
                
                completion_tokens = count_tokens(completion_text, model)
                
                tokens = {
                    "prompt": prompt_tokens,
                    "completion": completion_tokens,
                    "total": prompt_tokens + completion_tokens
                }
                
                print(f"🔢 [TokenCounter] Calculated tokens: {tokens['total']} (prompt: {tokens['prompt']}, completion: {tokens['completion']}) [PRECISE]")
                return tokens
                
            except Exception as tc_err:
                print(f"⚠️ [TokenCounter] Precise counting failed: {tc_err}")
            
    except Exception as e:
        print(f"⚠️ [Token Extract] Failed: {e}")
    
    return tokens


def _log_llm_tokens(stage: str, model_name: str, result: Any, messages: Any, duration_ms: float, success: bool = True):
    """
    V17.5: Log token usage to FlightRecorder with precise counting.
    
    Safe wrapper that won't break on errors.
    """
    try:
        from ...utils.flight_recorder import get_recorder
        from ...utils.token_counter import estimate_cost
        
        tokens = _extract_tokens(result, messages, model_name)
        
        # Only log if we have meaningful token data
        if tokens["total"] > 0:
            recorder = get_recorder()
            recorder.log_llm_call(
                stage=stage,
                model=model_name,
                tokens=tokens,
                duration_ms=duration_ms,
                success=success
            )
            cost = estimate_cost(tokens, model_name)
            print(f"📊 [{stage}] Logged {tokens['total']} tokens (${cost:.6f})")
    except Exception as e:
        # Never break the request due to logging failures
        print(f"⚠️ [Token Log] Failed (non-fatal): {e}")

def invoke_with_timeout(llm, messages, timeout=LLM_TIMEOUT, **kwargs):
    """
    Invoke LLM with a timeout to prevent hanging after idle.
    Returns response or raises TimeoutError.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(llm.invoke, messages, **kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            print(f" [TIMEOUT] LLM call timed out after {timeout}s")
            raise TimeoutError(f"LLM call timed out after {timeout}s")

class ReliableLLM:
    """
    A wrapper that tries a Primary LLM, and falls back to a Backup LLM on error.
    Implements the standard LangChain 'invoke' interface with timeout protection.
    """
    def __init__(self, primary, backup=None, name="Model"):
        self.primary = primary
        self.backup = backup
        self.name = name
    
    def invoke(self, messages, timeout=LLM_TIMEOUT, **kwargs):
        """
        Synchronous LLM invocation with rate limiting.
        
        V10.4: All models (Router, Planner, Responder) are rate limited.
        """
        from ..infrastructure.rate_limiter import get_rate_limiter
        import asyncio
        
        # Get model name for rate limiting
        model_name = getattr(self.primary, 'model_name', None) or \
                     getattr(self.primary, 'model', 'unknown')
        
        # Acquire rate limit (blocking for sync context)
        limiter = get_rate_limiter()
        bucket = limiter.get_bucket(model_name)
        
        # Use event loop if available, otherwise skip async acquire
        try:
            loop = asyncio.get_running_loop()
            # Can't await in sync context, just proceed
        except RuntimeError:
            # No event loop, do blocking check
            import time
            while bucket.tokens < 1:
                bucket._refill()
                if bucket.tokens < 1:
                    sleep_time = (1 - bucket.tokens) / bucket.rate
                    print(f"⏳ [{self.name}] Rate limited: waiting {sleep_time:.2f}s")
                    time.sleep(min(sleep_time, 2.0))  # Cap at 2s per iteration
            bucket.tokens -= 1
            bucket.total_requests += 1
        
        print(f" [{self.name}] Invoking LLM...")
        start_time = time.time()
        try:
            result = invoke_with_timeout(self.primary, messages, timeout=timeout, **kwargs)
            duration_ms = (time.time() - start_time) * 1000
            print(f" [{self.name}] LLM call succeeded")
            
            # V17.5: Log token usage to FlightRecorder with precise counting
            _log_llm_tokens(self.name, model_name, result, messages, duration_ms, success=True)
            
            return result
        except (TimeoutError, Exception) as e:
            # FIX: Recover from Groq "tool_use_failed" error with <function=...>
            # Llama 3 sometimes leaks XML tool calls that Groq API rejects.
            # We catch this rejection and parse the intent manually.
            err_str = str(e)
            duration_ms = (time.time() - start_time) * 1000
            if "failed_generation" in err_str and "<function=" in err_str:
                print(f" [{self.name}] Recovering from Groq XML tool call...")
                try:
                    # Parse kwargs like: query="git change origin"
                    match_tools = self._recover_groq_xml(err_str)
                    if match_tools:
                        # V17.4: Log estimated tokens for recovered call
                        try:
                            from ...utils.flight_recorder import get_recorder
                            recorder = get_recorder()
                            estimated_tokens = {"prompt": 400, "completion": 100, "total": 500}
                            recorder.log_llm_call(
                                stage=f"{self.name} (Recovered)",
                                model=model_name,
                                tokens=estimated_tokens,
                                duration_ms=duration_ms,
                                success=True
                            )
                            print(f"📊 [{self.name}] Logged ~500 estimated tokens (recovered from XML)")
                        except:
                            pass
                        return match_tools
                except Exception as parse_err:
                    print(f" Recovery failed: {parse_err}")

            if self.backup:
                print(f"⚠️ {self.name} Primary failed: {e}. Switching to Backup (Gemini)...")
                try:
                    backup_start = time.time()
                    backup_model = getattr(self.backup, 'model_name', None) or \
                                   getattr(self.backup, 'model', 'backup-unknown')
                    result = invoke_with_timeout(self.backup, messages, timeout=timeout, **kwargs)
                    backup_duration = (time.time() - backup_start) * 1000
                    
                    # V17.5: Log backup model tokens
                    _log_llm_tokens(f"{self.name} (Backup)", backup_model, result, messages, backup_duration, success=True)
                    
                    return result
                except Exception as backup_err:
                    print(f" {self.name} Backup also failed: {backup_err}")
                    raise backup_err
            print(f" {self.name} Failed (No Backup Available): {e}")
            raise e

    def _recover_groq_xml(self, err_str: str):
        """
        Helper to recover XML tool calls from error string.
        V17.3: Robust parsing for truncated JSON and key-value patterns.
        """
        # Match from <function=name until </function> or end of string
        match = re.search(r"<function=(\w+)\s*(.*?)(?:</function>|$)", err_str, re.DOTALL)
        
        args = {}
        tool_name = ""
        
        if match:
            tool_name = match.group(1)
            payload = match.group(2).strip()
            
            # 1. Try to extract and fix JSON from payload
            json_match = re.search(r"(\{.*\})", payload, re.DOTALL)
            if json_match:
                try:
                    args = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    # Fix truncated JSON (common in Groq errors)
                    try:
                        args = json.loads(json_match.group(1) + "}")
                    except:
                        pass
            
            # 2. Key-Value Extraction Fallback
            if not args and payload:
                # Matches query="value", "query": "value", or 'query': 'value'
                pairs = re.findall(r'(\w+)\s*[:=]\s*["\']([^"\']*)["\']', payload)
                for k, v in pairs:
                    args[k] = v
            
            # 3. Last-ditch extraction for play_youtube (most common failure)
            if not args and tool_name == "play_youtube":
                # Extract first quoted string as topic
                topic_match = re.search(r'["\']([^"\']+)["\']', payload)
                if topic_match:
                    args["topic"] = topic_match.group(1)

        if not tool_name:
            return None
        
        print(f"   Parsed: {tool_name} args={args}")
        call_id = f"call_{uuid.uuid4().hex[:8]}"
        
        return AIMessage(
            content="",
            tool_calls=[{
                "name": tool_name,
                "args": args,
                "id": call_id
            }]
        )
    
    async def ainvoke(self, messages, timeout=LLM_TIMEOUT, **kwargs):
        """
        True async invocation with backpressure rate limiting.
        
        V10.4: 
        - Uses native LangChain ainvoke() for true async
        - Rate limits via token bucket (induces latency, not 429 crashes)
        - Enables parallel tool execution via asyncio.gather()
        """
        from ..infrastructure.rate_limiter import get_rate_limiter
        
        # Get model name for rate limiting
        model_name = getattr(self.primary, 'model_name', None) or \
                     getattr(self.primary, 'model', 'unknown')
        
        # Acquire rate limit (will sleep if bucket empty)
        limiter = get_rate_limiter()
        wait_time = await limiter.acquire(model_name)
        
        if wait_time > 0:
            print(f"⏳ [{self.name}] Rate limited: waited {wait_time:.2f}s")
        
        print(f" [{self.name}] Async invoking LLM...")
        start_time = time.time()
        
        try:
            # LangChain models have native ainvoke() support
            if hasattr(self.primary, 'ainvoke'):
                result = await self.primary.ainvoke(messages, **kwargs)
            else:
                # Fallback to sync in thread if no native async
                import asyncio
                result = await asyncio.to_thread(self.primary.invoke, messages, **kwargs)
            
            duration_ms = (time.time() - start_time) * 1000
            print(f" [{self.name}] Async LLM call succeeded")
            
            # V17.5: Log token usage to FlightRecorder with precise counting
            _log_llm_tokens(self.name, model_name, result, messages, duration_ms, success=True)
            
            return result
            
        except Exception as e:
            err_str = str(e)
            duration_ms = (time.time() - start_time) * 1000
            
            # Try XML recovery for Groq errors
            if "failed_generation" in err_str and "<function=" in err_str:
                print(f" [{self.name}] Recovering from Groq XML tool call...")
                try:
                    match_tools = self._recover_groq_xml(err_str)
                    if match_tools:
                        # V17.4: Log estimated tokens for recovered call
                        # Groq doesn't provide usage in error responses, estimate ~500 tokens
                        try:
                            from ...utils.flight_recorder import get_recorder
                            recorder = get_recorder()
                            estimated_tokens = {"prompt": 400, "completion": 100, "total": 500}
                            recorder.log_llm_call(
                                stage=f"{self.name} (Recovered)",
                                model=model_name,
                                tokens=estimated_tokens,
                                duration_ms=duration_ms,
                                success=True
                            )
                            print(f"📊 [{self.name}] Logged ~500 estimated tokens (recovered from XML)")
                        except:
                            pass
                        return match_tools
                except Exception as parse_err:
                    print(f" Recovery failed: {parse_err}")
            
            # Try backup
            if self.backup:
                print(f"⚠️ {self.name} Primary async failed: {e}. Switching to Backup...")
                try:
                    backup_start = time.time()
                    backup_model = getattr(self.backup, 'model_name', None) or \
                                   getattr(self.backup, 'model', 'backup-unknown')
                    
                    if hasattr(self.backup, 'ainvoke'):
                        result = await self.backup.ainvoke(messages, **kwargs)
                    else:
                        import asyncio
                        result = await asyncio.to_thread(self.backup.invoke, messages, **kwargs)
                    
                    backup_duration = (time.time() - backup_start) * 1000
                    
                    # V17.5: Log backup model tokens
                    _log_llm_tokens(f"{self.name} (Backup)", backup_model, result, messages, backup_duration, success=True)
                    
                    return result
                except Exception as backup_err:
                    print(f" {self.name} Backup async also failed: {backup_err}")
                    raise backup_err
            
            print(f" {self.name} Async Failed (No Backup): {e}")
            raise e

    def bind_tools(self, tools):
        """
        Bind tools to both primary and backup LLMs.
        Returns a new ReliableLLM instance with bound models.
        """
        print(f" [{self.name}] Binding {len(tools)} tools to Primary & Backup")
        
        # Bind to primary
        bound_primary = self.primary.bind_tools(tools)
        
        # Bind to backup if exists
        bound_backup = None
        if self.backup:
            # Check if backup supports binding (some might not)
            if hasattr(self.backup, "bind_tools"):
                bound_backup = self.backup.bind_tools(tools)
            else:
                bound_backup = self.backup # Keep unbound if not supported
        
        # Return new wrapper so invoke() works heavily
        return ReliableLLM(bound_primary, bound_backup, f"{self.name}+Tools")
