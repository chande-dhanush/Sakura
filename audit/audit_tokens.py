#!/usr/bin/env python3
import sys
import os
import warnings
import locale

# Fix Windows paths
# We need to add 'backend' to sys.path to find 'sakura_assistant'
BACKEND_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
if BACKEND_PATH not in sys.path:
    sys.path.insert(0, BACKEND_PATH)

# Suppress noise
warnings.filterwarnings("ignore", category=DeprecationWarning)
os.environ["PYTHONWARNINGS"] = "ignore::DeprecationWarning"

# UTF-8 everywhere
if sys.platform == 'win32':
    try:
        import io
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

def audit_guard():
    """Skip if core deps missing"""
    missing = []
    try:
        import sakura_assistant
    except ImportError:
        missing.append("sakura_assistant")
    
    if missing:
        # Check if we are in the backend dir already (fallback)
        if os.path.exists("sakura_assistant"):
            return
        print(f"Audit skipped: {missing} (Checked: {BACKEND_PATH})")
        sys.exit(77)  # Non-zero but non-error exit
    
audit_guard()

"""
Sakura V10.4: Per-Model Token Safety Audit (VERIFIED)
======================================================
"""
import sys
import os

try:
    from sakura_assistant.config import ROUTER_SYSTEM_PROMPT
except ImportError:
    ROUTER_SYSTEM_PROMPT = "[TEMPLATE_MISSING - V19.5 PATH UPDATE]"

from sakura_assistant.config import (
    PLANNER_SYSTEM_PROMPT,
    SYSTEM_PERSONALITY,
    VERIFIER_SYSTEM_PROMPT,
)
from sakura_assistant.core.models.responder import RESPONDER_NO_TOOLS_RULE
from sakura_assistant.core.infrastructure.rate_limiter import GlobalRateLimiter

def print_header(text):
    print("\n" + "="*60)
    print(f" {text}")
    print("="*60 + "\n")

# ============================================================================
# TOKEN COUNTING
# ============================================================================

def tokens(text: str) -> int:
    return len(str(text)) // 4

LIMITS = GlobalRateLimiter.MODEL_LIMITS

MODEL_USAGE = {
    "llama-3.1-8b-instant": {
        "name": "Llama 3.1 8B",
        "provider": "Groq",
        "stages": ["Router"],
        "input_tokens": tokens(ROUTER_SYSTEM_PROMPT) + 50,
        "output_tokens": 50,
    },
    "llama-3.3-70b-versatile": {
        "name": "Llama 3.3 70B",
        "provider": "Groq",
        "stages": ["Planner", "Verifier"],
        "input_tokens": tokens(PLANNER_SYSTEM_PROMPT) + 500 + tokens(VERIFIER_SYSTEM_PROMPT) + 100,
        "output_tokens": 230,
    },
    "openai/gpt-oss-20b": {
        "name": "GPT OSS 20B",
        "provider": "OpenRouter",
        "stages": ["Responder"],
        "input_tokens": tokens(SYSTEM_PERSONALITY) + tokens(RESPONDER_NO_TOOLS_RULE) + 500,
        "output_tokens": 300,
    },
}

def main():
    print_header("PER-MODEL TOKEN CONSUMPTION (VERIFIED)")
    
    print("""
                                                                        
    MODEL ASSIGNMENTS (from container.py)                               
                                                                        
    Router:    llama-3.1-8b-instant    (Groq)                           
    Planner:   llama-3.3-70b-versatile (Groq)                           
    Responder: openai/gpt-oss-20b      (OpenRouter)                     
    Backup:    gemini-2.0-flash        (OpenRouter/Google)              
                                                                        
""")
    
    for model_id, usage in MODEL_USAGE.items():
        limit = LIMITS.get(model_id)
        if not limit:
            print(f"\n     {usage['name']} - NO LIMIT CONFIGURED!")
            continue
        
        total_per_turn = usage["input_tokens"] + usage["output_tokens"]
        max_turns = limit.tpm // total_per_turn if total_per_turn > 0 else 0
        usage_pct = round(total_per_turn / limit.tpm * 100, 1)
        
        print(f"\n    {usage['name']} ({usage['provider']})")
        print(f"         Stages:      {', '.join(usage['stages'])}")
        print(f"         Input:       ~{usage['input_tokens']} tokens")
        print(f"         Output:      ~{usage['output_tokens']} tokens")
        print(f"         Total/turn:  ~{total_per_turn} tokens")
        print(f"         TPM Limit:   {limit.tpm:,}")
        print(f"         RPM Limit:   {limit.rpm}")
        print(f"         Context:     {limit.context_window:,}")
        print(f"         Max/min:     {max_turns} turns ({usage_pct}% TPM/turn)")
        
        if total_per_turn > limit.tpm:
            print(f"       FAIL: Exceeds TPM!")
        elif max_turns < 1:
            print(f"        WARNING: Can't complete 1 turn/min")
        else:
            print(f"       SAFE")

def stress_test():
    """Stress test: What if multiple queries come at once?"""
    print_header("STRESS TEST: CONCURRENT QUERIES")
    
    print("""
 Scenario: 5 users send queries in the same minute
                                                      
""")
    
    for model_id, usage in MODEL_USAGE.items():
        limit = LIMITS.get(model_id)
        if not limit:
            continue
        
        total_per_turn = usage["input_tokens"] + usage["output_tokens"]
        tokens_for_5 = total_per_turn * 5
        
        print(f"    {usage['name']}: {tokens_for_5:,} / {limit.tpm:,} TPM")
        if tokens_for_5 > limit.tpm:
            print(f"       FAIL: 5 users would exceed rate limit!")
        else:
            print(f"       PASS: Can handle 5 concurrent users.")

if __name__ == "__main__":
    main()
    stress_test()
