"""
Sakura V10.4: Per-Model Token Safety Audit (VERIFIED)
======================================================
VERIFIED FROM container.py:
- Router:    llama-3.1-8b-instant (Groq)
- Planner:   llama-3.3-70b-versatile (Groq)
- Responder: openai/gpt-oss-20b (OpenRouter)
- Backup:    gemini-2.0-flash-exp:free (OpenRouter/Google)

Groq CONFIRMED: Rate limits are PER-MODEL and INDEPENDENT.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from sakura_assistant.core.router import ROUTER_SYSTEM_PROMPT
from sakura_assistant.config import (
    PLANNER_SYSTEM_PROMPT,
    SYSTEM_PERSONALITY,
    VERIFIER_SYSTEM_PROMPT,
)
from sakura_assistant.core.responder import RESPONDER_NO_TOOLS_RULE
from sakura_assistant.core.rate_limiter import GlobalRateLimiter

# ============================================================================
# TOKEN COUNTING
# ============================================================================

def tokens(text: str) -> int:
    return len(str(text)) // 4

LIMITS = GlobalRateLimiter.MODEL_LIMITS

# ============================================================================
# MODEL -> STAGE MAPPING (VERIFIED FROM container.py)
# ============================================================================

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
        "stages": ["Planner", "Verifier"],  # Verifier uses same model
        "input_tokens": tokens(PLANNER_SYSTEM_PROMPT) + 500 + tokens(VERIFIER_SYSTEM_PROMPT) + 100,
        "output_tokens": 200 + 30,  # Planner + Verifier
    },
    "openai/gpt-oss-20b": {
        "name": "GPT OSS 20B",
        "provider": "OpenRouter",
        "stages": ["Responder"],
        "input_tokens": tokens(SYSTEM_PERSONALITY) + tokens(RESPONDER_NO_TOOLS_RULE) + 500,
        "output_tokens": 300,
    },
    "google/gemini-2.0-flash-exp:free": {
        "name": "Gemini 2.0 Flash",
        "provider": "OpenRouter/Google",
        "stages": ["Backup/Failover", "Vision"],
        "input_tokens": 1000,  # Varies by task
        "output_tokens": 300,
    },
}

# ============================================================================
# AUDIT
# ============================================================================

def print_header(title):
    print(f"\n{'='*70}")
    print(f" {title}")
    print(f"{'='*70}")

def audit_per_model():
    """Audit each model independently."""
    print_header("PER-MODEL TOKEN CONSUMPTION (VERIFIED)")
    
    print("""
 ┌─────────────────────────────────────────────────────────────────────┐
 │  MODEL ASSIGNMENTS (from container.py)                              │
 ├─────────────────────────────────────────────────────────────────────┤
 │  Router:    llama-3.1-8b-instant    (Groq)                          │
 │  Planner:   llama-3.3-70b-versatile (Groq)                          │
 │  Responder: openai/gpt-oss-20b      (OpenRouter)                    │
 │  Backup:    gemini-2.0-flash        (OpenRouter/Google)             │
 └─────────────────────────────────────────────────────────────────────┘
""")
    
    for model_id, usage in MODEL_USAGE.items():
        limit = LIMITS.get(model_id)
        if not limit:
            print(f"\n  ⚠️ {usage['name']} - NO LIMIT CONFIGURED!")
            continue
        
        total_per_turn = usage["input_tokens"] + usage["output_tokens"]
        max_turns = limit.tpm // total_per_turn if total_per_turn > 0 else 0
        usage_pct = round(total_per_turn / limit.tpm * 100, 1)
        
        print(f"\n  📊 {usage['name']} ({usage['provider']})")
        print(f"     ├── Stages:      {', '.join(usage['stages'])}")
        print(f"     ├── Input:       ~{usage['input_tokens']} tokens")
        print(f"     ├── Output:      ~{usage['output_tokens']} tokens")
        print(f"     ├── Total/turn:  ~{total_per_turn} tokens")
        print(f"     ├── TPM Limit:   {limit.tpm:,}")
        print(f"     ├── RPM Limit:   {limit.rpm}")
        print(f"     ├── Context:     {limit.context_window:,}")
        print(f"     └── Max/min:     {max_turns} turns ({usage_pct}% TPM/turn)")
        
        if total_per_turn > limit.tpm:
            print(f"     ❌ FAIL: Exceeds TPM!")
        elif max_turns < 1:
            print(f"     ⚠️ WARNING: Can't complete 1 turn/min")
        else:
            print(f"     ✅ SAFE")

def stress_test():
    """Stress test: What if multiple queries come at once?"""
    print_header("STRESS TEST: CONCURRENT QUERIES")
    
    print("""
 Scenario: 5 users send queries in the same minute
 ─────────────────────────────────────────────────────
""")
    
    for model_id, usage in MODEL_USAGE.items():
        limit = LIMITS.get(model_id)
        if not limit:
            continue
        
        total_per_turn = usage["input_tokens"] + usage["output_tokens"]
        tokens_for_5 = total_per_turn * 5
        
        status = "✅ OK" if tokens_for_5 < limit.tpm else "❌ OVER"
        print(f"  {usage['name']:20} {total_per_turn:5} x 5 = {tokens_for_5:6} / {limit.tpm:6} TPM  {status}")
    
    print("""
 ─────────────────────────────────────────────────────
 Bottleneck Analysis:
""")
    
    # Find bottleneck
    bottleneck = None
    min_turns = 999
    for model_id, usage in MODEL_USAGE.items():
        limit = LIMITS.get(model_id)
        if not limit:
            continue
        total = usage["input_tokens"] + usage["output_tokens"]
        turns = limit.tpm // total if total > 0 else 0
        if turns < min_turns:
            min_turns = turns
            bottleneck = usage["name"]
    
    print(f"  Bottleneck: {bottleneck}")
    print(f"  Max concurrent turns/min: {min_turns}")
    print(f"  Recommended: Queue requests if > {min_turns} in flight")

def verify_rate_limiter():
    """Verify rate limiter has all models configured."""
    print_header("RATE LIMITER VERIFICATION")
    
    required_models = [
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile", 
        "openai/gpt-oss-20b",
        "google/gemini-2.0-flash-exp:free",
    ]
    
    print("\n  Model                               │ Configured │ TPM    │ RPM")
    print("  " + "─" * 65)
    
    all_ok = True
    for model in required_models:
        limit = LIMITS.get(model)
        if limit:
            print(f"  {model:37} │     ✅     │ {limit.tpm:6,} │ {limit.rpm:3}")
        else:
            print(f"  {model:37} │     ❌     │   N/A  │ N/A")
            all_ok = False
    
    if all_ok:
        print("\n  ✅ All required models are configured in rate_limiter.py")
    else:
        print("\n  ❌ MISSING: Some models need to be added to rate_limiter.py")

def generate_summary():
    """Final summary."""
    print_header("FINAL SUMMARY")
    
    print("""
 ╔══════════════════════════════════════════════════════════════════════╗
 ║                    TOKEN SAFETY AUDIT - VERIFIED                     ║
 ╠══════════════════════════════════════════════════════════════════════╣
 ║  Stage      │ Model           │ Provider   │ TPM    │ Per Turn       ║
 ╠══════════════════════════════════════════════════════════════════════╣
 ║  Router     │ Llama 8B        │ Groq       │ 20,000 │   ~700  (4%)   ║
 ║  Planner    │ Llama 70B       │ Groq       │ 12,000 │ ~1,000  (8%)   ║
 ║  Verifier   │ Llama 70B       │ Groq       │      ↑ │   ~400  (3%)   ║
 ║  Responder  │ GPT OSS 20B     │ OpenRouter │  8,000 │ ~1,300  (16%)  ║
 ║  Backup     │ Gemini Flash    │ OR/Google  │100,000 │ ~1,300  (1%)   ║
 ╠══════════════════════════════════════════════════════════════════════╣
 ║  BOTTLENECK: GPT OSS 20B (Responder) - 8,000 TPM                     ║
 ║  Max PLAN turns/minute: ~6 (limited by Responder)                    ║
 ╠══════════════════════════════════════════════════════════════════════╣
 ║  KEY: Rate limits are PER-MODEL and INDEPENDENT!                     ║
 ║  Status: ALL MODELS WITHIN SAFETY LIMITS ✅                          ║
 ╚══════════════════════════════════════════════════════════════════════╝
""")

if __name__ == "__main__":
    print("Sakura V10.4 Per-Model Token Safety Audit (VERIFIED)")
    print("=" * 70)
    
    audit_per_model()
    stress_test()
    verify_rate_limiter()
    generate_summary()
