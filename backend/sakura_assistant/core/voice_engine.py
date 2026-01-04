import time
import threading
import queue
import speech_recognition as sr
from typing import Optional, Callable
import traceback

from ..utils.wake_word import init_wake_detector, WakeState
from ..utils.shared_mic import start_shared_mic, register_mic_consumer, activate_mic_consumer, deactivate_mic_consumer
from ..utils.tts import speak_async
from ..core.llm import SmartAssistant

class VoiceEngine:
    """
    Manages the Voice Interaction Loop:
    Wake Word -> Listen (STT) -> Process (LLM) -> Speak (TTS)
    """
    
    def __init__(self, assistant: SmartAssistant):
        self.assistant = assistant
        self.recognizer = sr.Recognizer()
        self.listening = False
        self.processing = False
        self.should_stop = False
        
        # Queue for passing audio from shared mic to SR
        self.audio_queue = queue.Queue()
        
        # Initialize Wake Detector (running on shared_mic)
        self.wake_detector = init_wake_detector(
            on_wake_detected=self._on_wake_word
        )
    
    def start(self):
        """Start the Voice Engine background thread."""
        if not self.wake_detector:
            print("❌ Voice Engine: Wake Detector init failed (missing templates/libs?)")
            return

        print("🎙️ Voice Engine: Starting...")
        
        # Start Shared Mic
        if not start_shared_mic():
            print("❌ Voice Engine: Failed to start Shared Mic")
            return

        # Start Wake Detection
        if not self.wake_detector.start():
            print("❌ Voice Engine: Failed to start Wake Detector")
            return

        # Start Main Loop Thread
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print("✅ Voice Engine: Running (Say 'Sakura' to activate)")

    def stop(self):
        """Stop the Voice Engine."""
        self.should_stop = True
        if self.wake_detector:
            self.wake_detector.stop()
        print("🛑 Voice Engine: Stopped")

    def _on_wake_word(self):
        """Callback when wake word is detected."""
        if self.processing or self.listening:
            return
            
        print("🌸 WAKE WORD DETECTED! Listening for command...")
        
        # 1. Pause Wake Detection
        self.wake_detector.pause()
        
        # 2. Trigger Listening State
        self.listening = True

    def manual_trigger(self):
        """Manually trigger the listening state (e.g. from UI button)."""
        print("👆 Manual Voice Trigger")
        if not self.listening and not self.processing:
            if self.wake_detector:
                self.wake_detector.pause()
            self.listening = True


    def _listen_for_command(self) -> Optional[str]:
        """
        Record audio and perform Speech-to-Text.
        Uses SpeechRecognition library with Google Speech API (Free tier).
        """
        try:
            print("👂 Listening...")
            
            # P0: Stop shared mic to release audio device for SpeechRecognition
            stop_shared_mic()
            time.sleep(0.2)
            
            try:
                with sr.Microphone() as source:
                    # Adjust for noise briefly
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    
                    # Listen (blocking, with timeout)
                    try:
                        audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                    except sr.WaitTimeoutError:
                        print("TIMEOUT: No speech detected.")
                        return None
            finally:
                # P0: ALWAYS restart shared mic for Wake Detector
                start_shared_mic()

            print("📝 Transcribing...")
            try:
                # Use Google Speech Recognition (free, reliable)
                text = self.recognizer.recognize_google(audio)
                print(f"🗣️ User said: '{text}'")
                return text
            except sr.UnknownValueError:
                print("❓ STT: Could not understand audio")
                return None
            except sr.RequestError as e:
                print(f"⚠️ STT Error: {e}")
                return None
                
        except Exception as e:
            print(f"❌ Listening Error: {e}")
            return None

    def _run_loop(self):
        """Main Voice Event Loop."""
        while not self.should_stop:
            if self.listening:
                # --- LISTENING PHASE ---
                command = self._listen_for_command()
                self.listening = False
                
                if command:
                    # --- PROCESSING PHASE ---
                    self.processing = True
                    print("⚙️ Processing command...")
                    
                    try:
                        # Direct call to LLM with history
                        history = getattr(self.assistant.store, "conversation_history", [])
                        response = self.assistant.run(command, history=history)
                        
                        # Extract text response
                        reply_text = response.get("content", "")
                        
                        # --- SPEAKING PHASE ---
                        if reply_text:
                            print(f"🤖 Speaking: {reply_text[:50]}...")
                            speak_async(reply_text)
                            
                            # Wait roughly for speech to finish (naive) or just cool down
                            # The speak_async is tracking its own queue.
                            # We just need to ensure we don't re-trigger immediately.
                            time.sleep(2) 
                            
                    except Exception as e:
                        print(f"❌ Execution Error: {e}")
                        traceback.print_exc()
                    
                    self.processing = False
                
                # Resume Wake Detection
                self.wake_detector.resume()
                print("👂 Voice Engine: Resume listening for 'Sakura'")
            
            time.sleep(0.1)
