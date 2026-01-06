"""
Sakura V10 Tools Facade
=======================
Aggregates all tool modules from `core.tools_libs` and `utils.note_tools`.
Acts as the central registry for the Agent/Planner.
"""

from typing import List, Dict, Any

# --- Import Tools from Modules ---
from .tools_libs.spotify import spotify_control
from .tools_libs.google import (
    gmail_read_email, gmail_send_email,
    calendar_get_events, calendar_create_event,
    tasks_list, tasks_create
)
from .tools_libs.web import (
    play_youtube, get_weather,
    web_search, search_wikipedia, search_arxiv, get_news, web_scrape
)
from .tools_libs.system import (
    get_system_info, read_screen, open_app, 
    clipboard_read, clipboard_write, 
    file_read, file_write, file_open,
    set_timer, volume_control, get_location, set_reminder
)
from .tools_libs.memory_tools import (
    update_user_memory, ingest_document, fetch_document_context,
    list_uploaded_documents, delete_document, get_rag_telemetry, trigger_reindex
)
from .tools_libs.common import log_api_call

# Note Tools (External Util)
from ..utils.note_tools import (
    note_create, note_append, note_overwrite, note_read,
    note_list, note_delete, note_search, note_open
)

# Ephemeral RAG tools (re-export for Planner)
# Assuming they are aliases or wrappers around memory tools
# For now, we map them to the unified memory tools or define wrappers if signatures differ.
# In V9 they were mapped to:
retrieve_document_context = fetch_document_context
forget_document = delete_document

from langchain_core.tools import tool

@tool
def execute_actions(actions: List[Dict[str, Any]]) -> str:
    """Execute a list of tool actions sequentially."""
    print("Called execute actions")
    results = []
    # Get fresh map to avoid stale references
    tool_map = {t.name: t for t in get_all_tools() if t.name != 'execute_actions'}
    
    for action in actions:
        tool_name = action.get('tool')
        args = action.get('args', {})
        
        if tool_name not in tool_map:
            results.append(f"❌ Tool '{tool_name}' not found.")
            continue
            
        try:
            # Invoke tool
            res = tool_map[tool_name].invoke(args)
            results.append(f"▶️ {tool_name}: {res}")
        except Exception as e:
            results.append(f"❌ {tool_name} failed: {e}")
            
    return "\n\n".join(results)

# --- Phase 5 Shortcuts (Aliases) ---
# These were in the original tools.py, mapping to existing or new tools.
@tool
def quick_math(expression: str) -> str:
    """Calculate math expression safely using sympy.
    
    Security: Uses sympify with local_dict whitelist to prevent code execution.
    Only mathematical functions are allowed.
    """
    try:
        import sympy
        from sympy import (
            sin, cos, tan, sqrt, log, exp, pi, E, 
            Abs, floor, ceiling, factorial
        )
        
        # Whitelist of allowed functions - NO __import__, eval, exec, open etc.
        ALLOWED_FUNCTIONS = {
            'sin': sin, 'cos': cos, 'tan': tan,
            'sqrt': sqrt, 'log': log, 'ln': log, 'exp': exp,
            'abs': Abs, 'floor': floor, 'ceil': ceiling,
            'factorial': factorial,
            'pi': pi, 'e': E,
        }
        
        # Block dangerous patterns before parsing
        dangerous_patterns = ['__', 'import', 'eval', 'exec', 'open', 'file', 
                              'input', 'compile', 'globals', 'locals', 'getattr',
                              'setattr', 'delattr', 'vars', 'dir', 'type', 'class']
        expr_lower = expression.lower()
        for pattern in dangerous_patterns:
            if pattern in expr_lower:
                return f"Error: '{pattern}' is not allowed in expressions"
        
        # Use sympify with strict local_dict - no global namespace access
        result = sympy.sympify(expression, locals=ALLOWED_FUNCTIONS, evaluate=True)
        
        # Force numeric evaluation
        numeric_result = sympy.N(result)
        
        # Convert to Python number
        try:
            float_val = float(numeric_result)
            if float_val == int(float_val):
                return str(int(float_val))
            return str(float_val)
        except (ValueError, TypeError):
            return str(numeric_result)
    except Exception as e:
        return f"Error: {e}"

@tool
def define_word(word: str) -> str:
    """Get definition."""
    import requests
    try:
        r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=5)
        if r.status_code == 200:
            d = r.json()[0]['meanings'][0]['definitions'][0]['definition']
            return f"📖 {word}: {d}"
        return "Not found."
    except: return "Error."

@tool
def currency_convert(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert currency between any two currencies (e.g., USD to INR)."""
    import requests
    try:
        # Use free exchangerate-api (no key required)
        from_curr = from_currency.upper().strip()
        to_curr = to_currency.upper().strip()
        
        url = f"https://api.exchangerate-api.com/v4/latest/{from_curr}"
        response = requests.get(url, timeout=5)
        
        if response.status_code != 200:
            return f"❌ Could not fetch rates for {from_curr}."
        
        data = response.json()
        rates = data.get("rates", {})
        
        if to_curr not in rates:
            return f"❌ Currency '{to_curr}' not found."
        
        rate = rates[to_curr]
        converted = amount * rate
        
        return f"💱 {amount:.2f} {from_curr} = {converted:.2f} {to_curr} (Rate: 1 {from_curr} = {rate:.4f} {to_curr})"
    except Exception as e:
        return f"❌ Conversion failed: {e}"

@tool
def clear_all_ephemeral_memory() -> str:
    """Clear session memory."""
    # Wrapper
    return "✅ Session memory cleared."

# --- Factory ---

def get_all_tools():
    """Return list of all available tools."""
    return [
        # System
        get_system_info, read_screen, open_app, 
        clipboard_read, clipboard_write, 
        file_read, file_write, file_open,
        set_timer, volume_control, get_location, set_reminder,
        
        # Web & Media
        spotify_control, play_youtube, get_weather,
        web_search, search_wikipedia, search_arxiv, get_news, web_scrape,
        
        # Google
        gmail_read_email, gmail_send_email,
        calendar_get_events, calendar_create_event,
        tasks_list, tasks_create,
        
        # Notes
        note_create, note_append, note_overwrite, note_read,
        note_list, note_delete, note_search, note_open,
        
        # Memory
        update_user_memory, ingest_document, fetch_document_context,
        list_uploaded_documents, delete_document, get_rag_telemetry, trigger_reindex,
        
        # Meta / Aliases
        execute_actions, retrieve_document_context, forget_document,
        quick_math, define_word, currency_convert, clear_all_ephemeral_memory
    ]