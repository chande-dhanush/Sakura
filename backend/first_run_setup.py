#!/usr/bin/env python3
"""
Sakura V19.5 — First Run Setup
Automatically called on first launch to download all required models.
Safe to re-run (idempotent).
"""
import asyncio
import logging
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

logger = logging.getLogger("sakura.setup")

async def run_setup():
    results = {}
    
    # 1. Check/download openWakeWord models
    print("[Setup] Checking wake word models...")
    try:
        import openwakeword
        model_path = Path(openwakeword.__file__).parent / "resources/models/hey_jarvis_v0.1.onnx"
        if not model_path.exists():
            print("[Setup] Downloading wake word models (~8MB)...")
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: openwakeword.utils.download_models(['hey_jarvis'])
            )
        results['wake_word'] = '[OK] Ready'
    except Exception as e:
        results['wake_word'] = f'[FAIL] Failed: {e}'
    
    # 2. Check Kokoro model
    print("[Setup] Checking Kokoro TTS model...")
    try:
        # P0: Set HF_HOME before importing TTS to ensure it checks the right place
        MODELS_DIR = Path(__file__).parent / "models" / "kokoro"
        os.environ["HF_HOME"] = str(MODELS_DIR)
        
        from sakura_assistant.utils.tts import get_pipeline
        # This will trigger download if missing
        await asyncio.get_event_loop().run_in_executor(None, get_pipeline)
        results['kokoro'] = '[OK] Ready'
    except Exception as e:
        results['kokoro'] = f'[FAIL] Failed: {e}'
    
    # 3. Check sounddevice / microphone
    print("[Setup] Checking microphone access...")
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devices = [d for d in devices if d['max_input_channels'] > 0]
        if input_devices:
            results['microphone'] = f'[OK] {len(input_devices)} input devices found'
        else:
            results['microphone'] = '[WARN] No input devices found'
    except Exception as e:
        results['microphone'] = f'[FAIL] Failed: {e}'
    
    # 4. Check Groq API key
    print("[Setup] Checking Groq API key...")
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key and groq_key.startswith("gsk_"):
        results['groq_stt'] = '[OK] API key present'
    else:
        results['groq_stt'] = '[WARN] GROQ_API_KEY missing (STT will not work)'
    
    # Print summary
    print("\n" + "="*50)
    print("SAKURA FIRST RUN SETUP - RESULTS")
    print("="*50)
    for component, status in results.items():
        print(f"  {component:20} {status}")
    print("="*50)
    
    failed = [k for k, v in results.items() if v.startswith('[FAIL]')]
    if failed:
        print(f"\n[WARN] {len(failed)} component(s) need attention: {failed}")
        sys.exit(1)
    else:
        print("\n[OK] All components ready. Sakura is good to go!")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run_setup())
