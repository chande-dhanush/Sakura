"""
FIX-08 Tests: LLM Call Counter Enforcement
==========================================
Verifies that the ExecutionContext enforces a hard max limit
of 6 LLM calls per request, preventing ReAct iteration loops.
"""
import pytest
import asyncio
from unittest.mock import MagicMock
from sakura_assistant.core.execution.context import ExecutionContext, ExecutionMode, execution_context_var, LLMBudgetExceededError

class TestLLMBudget:

    def test_budget_enforcement(self):
        """1. When LLM calls exceed max_llm_calls (6) -> 
        record_and_check_llm_call() returns False."""
        ctx = ExecutionContext.create(
            mode=ExecutionMode.ITERATIVE,
            request_id="test1"
        )
        
        for _ in range(ctx.max_llm_calls):
            assert ctx.record_and_check_llm_call() is True
            
        # The 7th call must return False
        assert ctx.record_and_check_llm_call() is False

    def test_reliable_llm_budget_exceeded(self):
        """2. ReliableLLM raises LLMBudgetExceededError when context is exceeded."""
        from sakura_assistant.core.models.wrapper import ReliableLLM
        
        ctx = ExecutionContext.create(
            mode=ExecutionMode.ITERATIVE,
            request_id="test2"
        )
        token = execution_context_var.set(ctx)
        
        mock_llm = MagicMock()
        async def _ainvoke(*args, **kwargs):
            return "ok"
            
        mock_llm.ainvoke = _ainvoke
        
        wrapper = ReliableLLM(mock_llm)
        
        try:
            # Fast-forward to the precipice: 6 calls made
            ctx.llm_call_count = ctx.max_llm_calls
            
            # The 7th call through ainvoke must raise Exception
            with pytest.raises(LLMBudgetExceededError):
                asyncio.run(wrapper.ainvoke("say hi"))
                
        finally:
            execution_context_var.reset(token)
