"""
Sakura V10 Tool Executor
========================
Executes tool plans with ReAct loop support.

Extracted from llm.py as part of SOLID refactoring.
- Single Responsibility: Only handles tool execution
- Manages output pruning and summarization
"""
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from langchain_core.messages import ToolMessage
from .planner import Planner


@dataclass
class ExecutionResult:
    """Result of tool execution."""
    outputs: str                    # Formatted tool output text
    tool_messages: List[ToolMessage]  # For ReAct loop history
    tool_used: str                  # Last tool name used
    last_result: Optional[Dict]     # Last tool result details
    success: bool                   # Overall success status


class ToolExecutor:
    """
    Executes tool plans with ReAct loop support.
    
    Features:
    - Single and multi-step execution
    - Smart output pruning (JSON-aware)
    - Summarization for large outputs
    - ReAct-compatible ToolMessage history
    """
    
    def __init__(self, tools: List, summarizer_llm=None):
        """
        Args:
            tools: List of LangChain tools
            summarizer_llm: Optional LLM for summarizing large outputs
        """
        self.tools = tools
        self.tool_map = {t.name: t for t in tools}
        self.summarizer_llm = summarizer_llm
        if summarizer_llm:
            self.planner = Planner(summarizer_llm)
        else:
            self.planner = None
    
    def execute_single(self, tool_name: str, args: Dict) -> Tuple[str, bool]:
        """
        Execute a single tool call.
        
        Returns:
            Tuple of (result_string, success_boolean)
        """
        if tool_name not in self.tool_map:
            return f"Error: Tool '{tool_name}' not found.", False
        
        try:
            result = self.tool_map[tool_name].invoke(args)
            return str(result), True
        except Exception as e:
            return f"Error: {e}", False

    def execute(self, user_input: str, route_result: Any, graph_context: str, state: Any = None) -> ExecutionResult:
        """
        Main execution entry point. Runs the ReAct loop.
        """
        print(f"🔄 [Executor] Starting ReAct loop for: {user_input[:50]}...")
        
        all_tool_messages = []
        all_outputs = []
        final_tool_used = "None"
        
        # Max iterations for the loop (Plan -> Act -> Observe -> Plan)
        MAX_REACT_STEPS = 5
        
        for i in range(MAX_REACT_STEPS):
            print(f"🔄 [Executor] Iteration {i+1}/{MAX_REACT_STEPS}")
            
            # 1. PLAN
            if not self.planner:
                return ExecutionResult("Error: No planner configured", [], "Error", None, False)
                
            plan_result = self.planner.plan(
                user_input=user_input,
                context=graph_context,
                tool_history=all_tool_messages,
                intent_mode=route_result.classification if hasattr(route_result, 'classification') else "action"
            )
            
            steps = plan_result.get("plan", [])
            if not steps:
                print("⏹️ [Executor] Checkmate - No more steps needed.")
                break
                
            # 2. EXECUTE
            exec_res = self.execute_plan(steps, state=state)
            
            # 3. OBSERVE (Accumulate history)
            all_tool_messages.extend(exec_res.tool_messages)
            if exec_res.outputs:
                all_outputs.append(exec_res.outputs)
            
            final_tool_used = exec_res.tool_used
            
            # Logic to stop if "final answer" tools are used or if explicitly done?
            # Planner logic handles this (returns empty plan if satisfied)
            
        return ExecutionResult(
            outputs="\n".join(all_outputs),
            tool_messages=all_tool_messages,
            tool_used=final_tool_used,
            last_result=None,
            success=True
        )
    
    def execute_plan(self, steps: List[Dict], state=None, 
                     max_iterations: int = 5,
                     max_output_chars: int = 2000) -> ExecutionResult:
        """
        Execute multiple tool steps from a plan.
        
        Args:
            steps: List of {"tool": name, "args": {}, "id": n} dicts
            state: Optional AgentState for tracking
            max_iterations: Cap on number of steps
            max_output_chars: Max chars per output
            
        Returns:
            ExecutionResult with all outputs and history
        """
        results_text = []
        tool_messages = []
        tool_used = "None"
        last_result = None
        all_success = True
        
        # Cap iterations
        steps = steps[:max_iterations]
        if len(steps) > max_iterations:
            print(f"⚠️ Executor: Capped at {max_iterations} steps")
        
        for step in steps:
            tool_name = step.get("tool")
            tool_args = step.get("args", {})
            call_id = step.get("tool_call_id", f"call_{step.get('id', 0)}")
            
            if tool_name not in self.tool_map:
                err = f"Tool '{tool_name}' not found."
                results_text.append(f"Step {step.get('id')} Error: {err}")
                tool_messages.append(ToolMessage(
                    tool_call_id=call_id, 
                    content=err, 
                    name=tool_name, 
                    status="error"
                ))
                all_success = False
                if state:
                    state.record_tool_result(success=False)
                continue
            
            print(f"▶️ Executing Step {step.get('id')}: {tool_name} {tool_args}")
            
            try:
                res = self.tool_map[tool_name].invoke(tool_args)
                res_str = str(res)
                
                # Prune output for ReAct history
                pruned_res = self.prune_output(res_str)
                
                # Create ToolMessage for history
                tool_messages.append(ToolMessage(
                    tool_call_id=call_id,
                    content=pruned_res,
                    name=tool_name
                ))
                
                # Truncate for display
                if len(res_str) > max_output_chars:
                    res_str = res_str[:max_output_chars] + "... [truncated]"
                
                results_text.append(f"Step {step.get('id')} ({tool_name}): {res_str}")
                tool_used = tool_name
                last_result = {
                    "tool": tool_name, 
                    "args": tool_args, 
                    "output": res_str, 
                    "success": True
                }
                
                if state:
                    state.record_tool_result(success=True)
                    
            except Exception as e:
                err_msg = f"Error: {e}"
                tool_messages.append(ToolMessage(
                    tool_call_id=call_id,
                    content=err_msg,
                    name=tool_name,
                    status="error"
                ))
                results_text.append(f"Step {step.get('id')} Error: {e}")
                last_result = {
                    "tool": tool_name, 
                    "args": tool_args, 
                    "output": str(e), 
                    "success": False
                }
                all_success = False
                
                if state:
                    state.record_tool_result(success=False)
        
        # Format outputs
        outputs = ""
        if results_text:
            outputs = "\n\n=== TOOL EXECUTION LOG ===\n" + "\n".join(results_text)
        
        return ExecutionResult(
            outputs=outputs,
            tool_messages=tool_messages,
            tool_used=tool_used,
            last_result=last_result,
            success=all_success
        )
    
    def prune_output(self, output: str, max_chars: int = 1000) -> str:
        """
        Smart pruner with summarization fallback.
        
        For large outputs, preserves structure while reducing size:
        - JSON: Prunes large keys, truncates arrays
        - Text: Word-boundary truncation
        - Very large: LLM summarization (if available)
        """
        if len(output) <= max_chars:
            return output
        
        # Try LLM summarization for very large outputs
        if len(output) > 2000 and self.summarizer_llm:
            try:
                summary = self._summarize_output(output)
                if summary:
                    return f"[SUMMARY of {len(output)} chars]\n{summary}"
            except Exception as e:
                print(f"⚠️ Summarization failed: {e}")
        
        # Try JSON-aware pruning
        stripped = output.strip()
        if self._looks_like_json(stripped):
            try:
                data = json.loads(output)
                pruned_data = self._prune_json(data)
                pruned_json = json.dumps(pruned_data, indent=2, ensure_ascii=False)
                
                if len(pruned_json) <= max_chars:
                    return pruned_json
                return json.dumps({"_truncated": True, "preview": str(data)[:500]})
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Text truncation at word boundary
        return self._truncate_text(output, max_chars)
    
    def _looks_like_json(self, text: str) -> bool:
        """Check if text looks like JSON."""
        return ((text.startswith('{') and text.endswith('}')) or
                (text.startswith('[') and text.endswith(']')))
    
    def _prune_json(self, obj, depth: int = 0) -> Any:
        """Recursively prune large values in JSON."""
        if depth > 5:
            return "[NESTED]"
        
        if isinstance(obj, dict):
            pruned = {}
            for k, v in obj.items():
                # Skip known large keys
                if k.lower() in ('html', 'html_body', 'raw_content', 'body', 'content'):
                    pruned[k] = f"[{len(str(v))} chars - use retrieve_document_context()]"
                else:
                    pruned[k] = self._prune_json(v, depth + 1)
            return pruned
        
        elif isinstance(obj, list):
            if len(obj) > 5:
                return [self._prune_json(obj[0], depth + 1), f"... [{len(obj) - 1} more items]"]
            return [self._prune_json(item, depth + 1) for item in obj]
        
        elif isinstance(obj, str) and len(obj) > 200:
            return obj[:200] + "..."
        
        return obj
    
    def _truncate_text(self, text: str, max_chars: int) -> str:
        """Truncate text at word/sentence boundary."""
        truncated = text[:max_chars]
        
        last_space = truncated.rfind(' ')
        last_newline = truncated.rfind('\n')
        cut_point = max(last_space, last_newline, max_chars - 100)
        
        if cut_point > 0:
            truncated = text[:cut_point]
        
        remaining = len(text) - len(truncated)
        return f"{truncated}\n... [TRUNCATED: {remaining} chars]"
    
    def _summarize_output(self, output: str) -> Optional[str]:
        """Use LLM to summarize large output."""
        if not self.summarizer_llm:
            return None
        
        from langchain_core.messages import SystemMessage, HumanMessage
        
        prompt = """Summarize this tool output in 2-3 sentences.
Focus on: key facts, numbers, names, and actionable information.
Do NOT add information not present in the output."""
        
        try:
            messages = [
                SystemMessage(content=prompt),
                HumanMessage(content=output[:4000])  # Cap context
            ]
            response = self.summarizer_llm.invoke(messages)
            return response.content
        except Exception:
            return None
