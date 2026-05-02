"""
Wake Word Detection - ONNX-based openWakeWord
REPLACES: legacy DTW + MFCC matching
"""

import os
import time
import numpy as np
import logging
import asyncio
from typing import Optional, Callable
from openwakeword.model import Model

from .shared_mic import (
    register_mic_consumer, 
    activate_mic_consumer, 
    deactivate_mic_consumer
)

logger = logging.getLogger("sakura.wake")

class WakeWordDetector:
    """
    Production-grade wake word detector using openWakeWord (ONNX).
    Default: 'Hey Jarvis' (built-in)
    """
    
    def __init__(self, 
                 threshold: float = 0.5,
                 on_wake_detected: Optional[Callable] = None):
        self.threshold = threshold
        self.on_wake_detected = on_wake_detected
        
        self._running = False
        self._paused = False
        self._consumer_id = None
        
        # Initialize openWakeWord Model
        # This will download models to ~/.openwakeword/models on first run
        try:
            self.model = Model(
                wakeword_models=["hey_jarvis"],
                inference_framework="onnx"
            )
            logger.info("[WAKE] openWakeWord initialized with 'Sakura' model")
        except Exception as e:
            logger.error(f"[WAKE] Failed to initialize openWakeWord: {e}")
            self.model = None

    def start(self) -> bool:
        if not self.model:
            return False
        
        if self._running:
            return True
            
        try:
            # Register as mic consumer (priority 1 = lowest, always-on)
            self._consumer_id = register_mic_consumer(
                name="wake_word",
                callback=self._on_mic_frame,
                priority=1
            )
            activate_mic_consumer(self._consumer_id)
            self._running = True
            logger.info("[WAKE] Detection started")
            return True
        except Exception as e:
            logger.error(f"[WAKE] Start failed: {e}")
            return False

    def stop(self):
        self._running = False
        if self._consumer_id:
            deactivate_mic_consumer(self._consumer_id)
        logger.info("[WAKE] Detection stopped")

    def pause(self):
        self._paused = True
        logger.debug("[WAKE] Paused")

    def resume(self):
        self._paused = False
        logger.debug("[WAKE] Resumed")

    def _on_mic_frame(self, samples: np.ndarray, raw_bytes: bytes):
        """Callback from SharedMic"""
        if self._paused or not self._running or not self.model:
            return
        
        # openWakeWord expects 16kHz int16, 1280 samples (80ms) per frame ideally,
        # but Model.predict() handles internal buffering.
        audio_int16 = (samples * 32767).astype(np.int16)
        
        # Feed to model
        try:
            # predict() returns a dict of {model_name: score}
            prediction = self.model.predict(audio_int16)
            
            for ww, score in prediction.items():
                if score > self.threshold:
                    logger.info(f"[WAKE] TRIGGER: 'Sakura' detected (score: {score:.2f})")
                    if self.on_wake_detected:
                        # Call in a way that doesn't block the mic thread
                        try:
                            self.on_wake_detected()
                        except Exception as e:
                            logger.error(f"[WAKE] Callback error: {e}")
        except Exception as e:
            logger.error(f"[WAKE] Inference error: {e}")

# --- Legacy Compatibility & Helpers ---

_detector: Optional[WakeWordDetector] = None

def init_wake_detector(on_wake_detected: Callable, threshold: float = 0.5) -> Optional[WakeWordDetector]:
    global _detector
    if _detector:
        _detector.stop()
    _detector = WakeWordDetector(threshold=threshold, on_wake_detected=on_wake_detected)
    return _detector

def get_wake_detector() -> Optional[WakeWordDetector]:
    return _detector

def pause_wake_detection():
    if _detector: _detector.pause()

def resume_wake_detection():
    if _detector: _detector.resume()

class WakeState:
    # Minimal compatibility for VoiceEngine
    ACTIVE = "active"
    PAUSED = "paused"
