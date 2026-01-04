
"""
Reliable LLM Wrapper
====================
Provides a failover-safe wrapper for LLM calls with timeout protection.
Handles primary/backup switching and specific provider error recovery (e.g., Groq XML leaks).

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
            print(f"❌ [TIMEOUT] LLM call timed out after {timeout}s")
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
        print(f"🔄 [{self.name}] Invoking LLM...")
        try:
            result = invoke_with_timeout(self.primary, messages, timeout=timeout, **kwargs)
            print(f"✅ [{self.name}] LLM call succeeded")
            return result
        except (TimeoutError, Exception) as e:
            # FIX: Recover from Groq "tool_use_failed" error with <function=...>
            # Llama 3 sometimes leaks XML tool calls that Groq API rejects.
            # We catch this rejection and parse the intent manually.
            err_str = str(e)
            if "failed_generation" in err_str and "<function=" in err_str:
                print(f"🔧 [{self.name}] Recovering from Groq XML tool call...")
                try:
                    # Parse kwargs like: query="git change origin"
                     match_tools = self._recover_groq_xml(err_str)
                     if match_tools:
                         return match_tools
                except Exception as parse_err:
                    print(f"❌ Recovery failed: {parse_err}")

            if self.backup:
                print(f"⚠️ {self.name} Primary failed: {e}. Switching to Backup (Gemini)...")
                try:
                    return invoke_with_timeout(self.backup, messages, timeout=timeout, **kwargs)
                except Exception as backup_err:
                    print(f"❌ {self.name} Backup also failed: {backup_err}")
                    raise backup_err
            print(f"❌ {self.name} Failed (No Backup Available): {e}")
            raise e

    def _recover_groq_xml(self, err_str: str):
        """Helper to recover XML tool calls from error string."""
        # Try JSON format first
        match = re.search(r"<function=(\w+)(\{.*?\})(?:</function>)?", err_str)
        
        args = {}
        tool_name = ""
        
        if match:
            tool_name = match.group(1)
            args_str = match.group(2)
            args = json.loads(args_str)
        else:
            # Try Python kwargs format: <function=name(key="value")>
            match = re.search(r"<function=(\w+)\(([^)]+)\)", err_str)
            if match:
                tool_name = match.group(1)
                kwargs_str = match.group(2)
                args = {}
                for pair in re.findall(r'(\w+)=["\']([^"\']*)["\']', kwargs_str):
                    args[pair[0]] = pair[1]
            else:
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

    def bind_tools(self, tools):
        """
        Bind tools to both primary and backup LLMs.
        Returns a new ReliableLLM instance with bound models.
        """
        print(f"🔗 [{self.name}] Binding {len(tools)} tools to Primary & Backup")
        
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
