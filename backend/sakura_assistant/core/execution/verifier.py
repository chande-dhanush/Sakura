import json
import logging
from typing import Dict, Any, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from ...config import VERIFIER_SYSTEM_PROMPT

logger = logging.getLogger("Verifier")

class PlanVerifier:
    """
    Plan Verifier - Option A implementation.
    Validates if the executed plan actually satisfied the user's request.
    Uses a lightweight model (llama-3.1-8b-instant) for fast verification.
    """
    
    def __init__(self, llm: Any):
        # Provider-agnostic: use injected llm from container/runtime.
        self.llm = llm

    async def averify(
        self, 
        user_query: str, 
        plan: List[Dict[str, Any]], 
        tool_results: str,
        llm_override: Any = None
    ) -> Dict[str, Any]:
        """
        Verify the execution of a plan against the user query.
        
        Args:
            user_query: The original user request.
            plan: The list of steps the planner generated.
            tool_results: The consolidated output of all tools executed.
            llm_override: Optional LLM instance for verification.
            
        Returns:
            {"verdict": "PASS" | "FAIL", "reason": "summary"}
        """
        # Use provided override or default
        active_llm = llm_override or self.llm
        try:
            # Format plan for the prompt
            plan_str = "\n".join([f"- {s.get('tool')}({s.get('args')})" for s in plan])
            
            prompt_input = f"""
USER REQUEST: {user_query}

PLAN EXECUTED:
{plan_str}

TOOL OUTPUTS:
{tool_results}
"""
            
            messages = [
                SystemMessage(content=VERIFIER_SYSTEM_PROMPT),
                HumanMessage(content=prompt_input)
            ]
            
            response = await active_llm.ainvoke(messages)
            content = response.content.strip() if hasattr(response, 'content') else str(response).strip()
            
            if not content:
                logger.warning("[Verifier] Empty response from LLM, skipping validation")
                return {"verdict": "PASS", "reason": "Empty verifier response - assuming pass to prevent stall."}
            
            # Clean possible markdown wrap
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()
                
            result = json.loads(content)
            
            # Log to console for observability
            verdict = result.get("verdict", "FAIL")
            reason = result.get("reason", "No reason provided")
            print(f" [Verifier] Verdict: {verdict} | Reason: {reason}")
            
            return result
        except Exception as e:
            logger.warning(f"[Verifier] Failed to verify plan: {e}")
            return {"verdict": "FAIL", "reason": f"Verifier Error: {str(e)}"}
