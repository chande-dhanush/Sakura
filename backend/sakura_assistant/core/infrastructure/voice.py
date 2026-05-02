"""
Voice engine coordinator for wake-word interaction.

This module owns the always-on voice loop: shared microphone, DTW wake-word
detection, speech recognition, SmartAssistant dispatch, and response playback.
Neural synthesis itself lives in sakura_assistant.utils.tts; keep TTS model
loading/offload policy centralized there.
"""

from __future__ import annotations
import time
import threading
import queue
from typing import Optional, Callable, List, Any, TYPE_CHECKING
import sounddevice as sd
import numpy as np
import httpx
import io
import scipy.io.wavfile as wav
import os
import logging
import asyncio

from ...utils.wake_word import init_wake_detector, WakeState
from ...utils.shared_mic import (
    start_shared_mic, 
    stop_shared_mic, 
    register_mic_consumer, 
    activate_mic_consumer, 
    deactivate_mic_consumer,
    get_shared_mic_lock
)
from ...utils.tts import speak_async

logger = logging.getLogger("sakura.voice")

if TYPE_CHECKING:
    from ..llm import SmartAssistant

class VoiceEngine:
    """
    Manages the Voice Interaction Loop:
    Wake Word -> Listen (STT) -> Process (LLM) -> Speak (TTS)
    """
    
    def __init__(self, assistant: SmartAssistant):
        self.assistant = assistant
        self.listening = False
        self.processing = False
        self.should_stop = False
        
        # Initialize Wake Detector (running on shared_mic)
        self.wake_detector = init_wake_detector(
            on_wake_detected=self._on_wake_word
        )
    
    def start(self):
        """Start the Voice Engine background thread."""
        if not self.wake_detector:
            print(" Voice Engine: Wake Detector init failed (missing templates/libs?)")
            return

        print("  Voice Engine: Starting...")
        
        # Start Shared Mic
        if not start_shared_mic():
            print(" Voice Engine: Failed to start Shared Mic")
            return

        # Start Wake Detection
        if not self.wake_detector.start():
            print(" Voice Engine: Failed to start Wake Detector")
            return

        # Start Main Loop Thread
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print(" Voice Engine: Running (Say 'Sakura' to activate)")

    def stop(self):
        """Stop the Voice Engine."""
        self.should_stop = True
        if self.wake_detector:
            self.wake_detector.stop()
        print(" Voice Engine: Stopped")

    def _on_wake_word(self):
        """Callback when wake word is detected."""
        if self.processing or self.listening:
            return
            
        print(" WAKE WORD DETECTED! Listening for command...")
        
        # 1. Pause Wake Detection
        self.wake_detector.pause()
        
        # 2. Trigger Listening State
        self.listening = True

    def manual_trigger(self):
        """Manually trigger the listening state (e.g. from UI button)."""
        print(" Manual Voice Trigger")
        if not self.listening and not self.processing:
            if self.wake_detector:
                self.wake_detector.pause()
            self.listening = True


    async def _listen_for_command(self) -> str:
        """Record via sounddevice → transcribe via Groq Whisper"""
        logger.info("[STT] Listening...")
        
        SAMPLE_RATE = 16000
        GROQ_API_KEY = os.getenv("GROQ_API_KEY")
        
        try:
            # P0: Stop shared mic to release audio device
            stop_shared_mic()
            await asyncio.sleep(0.2)
            
            audio = await asyncio.to_thread(self._record_until_silence)
            
            # P0: ALWAYS restart shared mic
            start_shared_mic()

            if audio is None or len(audio) < SAMPLE_RATE * 0.3:
                logger.warning("[STT] Audio too short, ignoring")
                return ""
            
            logger.info(f"[STT] Recorded {len(audio)/SAMPLE_RATE:.1f}s, transcribing...")
            text = await self._transcribe_groq(audio)
            logger.info(f"[STT] Transcribed: '{text}'")
            return text
            
        except Exception as e:
            logger.error(f"[STT] Failed: {e}", exc_info=True)
            # Ensure mic is back on
            start_shared_mic()
            return ""

    def _record_until_silence(self) -> np.ndarray | None:
        SAMPLE_RATE = 16000
        SILENCE_THRESHOLD = 0.02
        SILENCE_SECONDS = 1.2
        chunks = []
        silence_chunks = 0
        speaking = False
        max_duration = 30  # 30s max recording
        
        logger.info("[STT] Waiting for speech...")
        
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32') as stream:
                for _ in range(int(max_duration * 10)):  # 100ms chunks
                    chunk, _ = stream.read(SAMPLE_RATE // 10)
                    rms = float(np.sqrt(np.mean(chunk**2)))
                    
                    if rms > SILENCE_THRESHOLD:
                        if not speaking:
                            logger.info("[STT] Speech detected")
                        speaking = True
                        silence_chunks = 0
                        chunks.append(chunk.copy())
                    elif speaking:
                        silence_chunks += 1
                        chunks.append(chunk.copy())
                        if silence_chunks >= int(SILENCE_SECONDS * 10):
                            logger.info("[STT] Silence detected, stopping")
                            break
        except Exception as e:
            logger.error(f"[STT] Recording device error: {e}")
            return None
    
        return np.concatenate(chunks) if chunks else None

    async def _transcribe_groq(self, audio: np.ndarray) -> str:
        SAMPLE_RATE = 16000
        GROQ_API_KEY = os.getenv("GROQ_API_KEY")
        
        if not GROQ_API_KEY:
            logger.error("[STT] GROQ_API_KEY missing")
            return "Error: Groq API key missing"

        buf = io.BytesIO()
        wav.write(buf, SAMPLE_RATE, (audio * 32767).astype(np.int16))
        buf.seek(0)
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    files={"file": ("audio.wav", buf, "audio/wav")},
                    data={"model": "whisper-large-v3-turbo"}
                )
                response.raise_for_status()
                return response.json().get("text", "").strip()
            except Exception as e:
                logger.error(f"[STT] Groq API error: {e}")
                return ""

    def _run_loop(self):
        """Main Voice Event Loop."""
        while not self.should_stop:
            if self.listening:
                # --- LISTENING PHASE ---
                # V19.5: Handle async listen in sync thread
                command = asyncio.run(self._listen_for_command())
                self.listening = False
                
                if command:
                    # --- PROCESSING PHASE ---
                    self.processing = True
                    print("   Processing command...")
                    
                    try:
                        # V10: Get history from central memory store
                        from ...memory.faiss_store import get_memory_store
                        store = get_memory_store()
                        
                        # 1. Sync User Message to UI
                        # Use append_to_history (Thread-safe, Syncs with UI)
                        store.append_to_history({"role": "user", "content": command})
                        
                        history = getattr(store, "conversation_history", [])
                        
                        # Direct call to LLM with history
                        response = self.assistant.run(command, history=history)
                        
                        # Extract text response
                        reply_text = response.get("content", "") if isinstance(response, dict) else str(response)
                        
                        # 2. Sync Assistant Message to UI
                        if reply_text:
                            store.append_to_history({"role": "assistant", "content": reply_text})
                        
                        # --- SPEAKING PHASE ---
                        if reply_text:
                            print(f" Speaking: {reply_text[:50]}...")
                            speak_async(reply_text)
                            
                            # Wait roughly for speech to finish (naive) or just cool down
                            # The speak_async is tracking its own queue.
                            # We just need to ensure we don't re-trigger immediately.
                            time.sleep(2) 
                            
                    except Exception as e:
                        print(f" Execution Error: {e}")
                        traceback.print_exc()
                    
                    self.processing = False
                
                # Resume Wake Detection
                self.wake_detector.resume()
                print(" Voice Engine: Resume listening for 'Sakura'")
            
            time.sleep(0.1)
