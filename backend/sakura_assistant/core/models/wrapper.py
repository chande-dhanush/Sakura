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
import os
from typing import Optional, List, Any, Dict
from langchain_core.messages import AIMessage

# Timeout in seconds
def _get_int_env(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < min_value or value > max_value:
        return default
    return value


LLM_TIMEOUT = _get_int_env("LLM_TIMEOUT_SECONDS", 60, 5, 180)


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
            usage = result.response_metadata.get('token_usage')
            if usage:
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
                "prompt": getattr(usage, 'prompt_tokens', 0) or getattr(usage, 'input_tokens', 0),
                "completion": getattr(usage, 'completion_tokens', 0) or getattr(usage, 'output_tokens', 0),
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
                
                print(f"  [TokenCounter] Calculated tokens: {tokens['total']} (prompt: {tokens['prompt']}, completion: {tokens['completion']}) [PRECISE]")
                return tokens
                
            except Exception as tc_err:
                print(f"   [TokenCounter] Precise counting failed: {tc_err}")
            
    except Exception as e:
        print(f"   [Token Extract] Failed: {e}")
    
    return tokens


def _log_llm_tokens(stage: str, model_name: str, result: Any, messages: Any, duration_ms: float, success: bool = True, trace_id: Optional[str] = None):
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
                success=success,
                trace_id=trace_id # V19 FIX: Pass trace_id
            )
            cost = estimate_cost(tokens, model_name)
            print(f"  [{stage}] Logged {tokens['total']} tokens (${cost:.6f})")
    except Exception as e:
        # Never break the request due to logging failures
        print(f"   [Token Log] Failed (non-fatal): {e}")

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

    def _get_model_name(self, model) -> str:
        """Extract model name from LangChain model object."""
        return getattr(model, 'model_name', None) or \
               getattr(model, 'model', 'unknown')

    def _acquire_limit_sync(self, model_name: str):
        """Blocking rate limit acquisition for sync context."""
        from ..infrastructure.rate_limiter import get_rate_limiter
        bucket = get_rate_limiter().get_bucket(model_name)
        
        import time
        while bucket.tokens < 1:
            bucket._refill()
            if bucket.tokens < 1:
                sleep_time = (1 - bucket.tokens) / bucket.rate
                print(f" [RL] model={model_name} wait={sleep_time:.2f}s (Sync)")
                time.sleep(min(sleep_time, 2.0))
        bucket.tokens -= 1
        bucket.total_requests += 1
    
    def invoke(self, messages, timeout=LLM_TIMEOUT, trace_id=None, **kwargs):
        """Synchronous LLM invocation with model-specific rate limiting."""
        try:
            from ..execution.context import execution_context_var, LLMBudgetExceededError
            ctx = execution_context_var.get()
            if ctx and not ctx.record_and_check_llm_call():
                raise LLMBudgetExceededError(f"Budget exceeded in {self.name}.")
        except (ImportError, LookupError): pass

        # 1. Rate limit primary
        primary_model = self._get_model_name(self.primary)
        self._acquire_limit_sync(primary_model)
        
        print(f" [{self.name}] Invoking Primary model={primary_model}")
        start_time = time.time()
        try:
            result = invoke_with_timeout(self.primary, messages, timeout=timeout, **kwargs)
            _log_llm_tokens(self.name, primary_model, result, messages, (time.time()-start_time)*1000, trace_id=trace_id)
            return result
        except Exception as e:
            # FIX: Recover from Groq "tool_use_failed" error with <function=...>
            err_str = str(e)
            duration_ms = (time.time() - start_time) * 1000
            if "failed_generation" in err_str and "<function=" in err_str:
                print(f" [{self.name}] Recovering from Groq XML tool call...")
                try:
                    match_tools = self._recover_groq_xml(err_str)
                    if match_tools:
                        _log_llm_tokens(f"{self.name} (Recovered)", primary_model, match_tools, messages, duration_ms, trace_id=trace_id)
                        return match_tools
                except Exception as parse_err:
                    print(f" Recovery failed: {parse_err}")

            if self.backup:
                # 2. Rate limit backup on fallback
                backup_model = self._get_model_name(self.backup)
                print(f" [RL] Primary failed, switching to backup={backup_model}")
                self._acquire_limit_sync(backup_model)
                
                backup_start = time.time()
                result = invoke_with_timeout(self.backup, messages, timeout=timeout, **kwargs)
                _log_llm_tokens(f"{self.name} (Backup)", backup_model, result, messages, (time.time()-backup_start)*1000)
                return result
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
    
    async def ainvoke(self, messages, timeout=LLM_TIMEOUT, trace_id=None, **kwargs):
        """True async invocation with model-specific backpressure."""
        try:
            from ..execution.context import execution_context_var, LLMBudgetExceededError
            ctx = execution_context_var.get()
            if ctx and not ctx.record_and_check_llm_call():
                raise LLMBudgetExceededError(f"Budget exceeded in {self.name}.")
        except (ImportError, LookupError): pass

        from ..infrastructure.rate_limiter import get_rate_limiter
        limiter = get_rate_limiter()

        # 1. Rate limit primary
        primary_model = self._get_model_name(self.primary)
        await limiter.acquire(primary_model)
        
        print(f" [{self.name}] Async invoking Primary model={primary_model}")
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
            _log_llm_tokens(self.name, primary_model, result, messages, duration_ms, success=True, trace_id=trace_id)
            return result
        except Exception as e:
            # Try XML recovery for Groq errors
            err_str = str(e)
            duration_ms = (time.time() - start_time) * 1000
            if "failed_generation" in err_str and "<function=" in err_str:
                print(f" [{self.name}] Recovering from Groq XML tool call...")
                try:
                    match_tools = self._recover_groq_xml(err_str)
                    if match_tools:
                        _log_llm_tokens(f"{self.name} (Recovered)", primary_model, match_tools, messages, duration_ms, trace_id=trace_id)
                        return match_tools
                except Exception as parse_err:
                    print(f" Recovery failed: {parse_err}")

            if self.backup:
                # 2. Rate limit backup on fallback
                backup_model = self._get_model_name(self.backup)
                print(f" [RL] Primary async failed, switching to backup={backup_model}")
                await limiter.acquire(backup_model)
                
                backup_start = time.time()
                if hasattr(self.backup, 'ainvoke'):
                    result = await self.backup.ainvoke(messages, **kwargs)
                else:
                    import asyncio
                    result = await asyncio.to_thread(self.backup.invoke, messages, **kwargs)
                
                _log_llm_tokens(f"{self.name} (Backup)", backup_model, result, messages, (time.time()-backup_start)*1000, success=True)
                return result
            
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
