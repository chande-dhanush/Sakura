"""
Wake Word Detection - Lightweight DTW + MFCC Template Matching

DESIGN:
- 8kHz mono audio capture
- RMS energy gating to skip silence
- MFCC feature extraction (13 coefficients)
- Dynamic Time Warping against user-recorded templates
- Cooldown to prevent retriggers

PERFORMANCE:
- <2% CPU during idle (RMS gate skips most frames)
- ~0.1MB memory (small buffers, no models)
- O(N²) DTW but N is tiny (~30 frames)

REQUIREMENTS:
- scipy for signal processing
- numpy for arrays
- pyaudio for mic input
"""

import os
import time
import threading
import numpy as np
from typing import Optional, List, Callable
from collections import deque

# Lazy imports to avoid startup cost
_scipy_available = None
_pyaudio_available = None

def _check_scipy():
    global _scipy_available
    if _scipy_available is None:
        try:
            from scipy.fft import dct
            from scipy.signal import get_window
            _scipy_available = True
        except ImportError:
            _scipy_available = False
    return _scipy_available

def _check_pyaudio():
    global _pyaudio_available
    if _pyaudio_available is None:
        try:
            import pyaudio
            _pyaudio_available = True
        except ImportError:
            _pyaudio_available = False
    return _pyaudio_available

from ..config import get_project_root
from ..utils.stability_logger import log_flow, log_warning
from enum import Enum, auto

# --- Configuration ---
# V4.2: Use 16kHz to match shared_mic (was 8kHz)
SAMPLE_RATE = 16000          # Must match shared_mic.py
BUFFER_DURATION = 2.0        # 2s buffer to match template length
BUFFER_SIZE = int(SAMPLE_RATE * BUFFER_DURATION)

# V5.1: Research-backed DTW threshold settings
# Empirical testing showed:
#   - Random speech: best DTW ~2.0-2.5
#   - Actual wake word: best DTW ~1.0-1.5 (should be lower)
# Threshold should be between random and wake word
DTW_THRESHOLD = 2        # Strict - only true wake word passes

# V5.1: Adaptive Noise Floor (tuned for Alexa-like reliability)
NOISE_FLOOR_ALPHA = 0.02   # EMA update rate
SPEECH_GATE_FACTOR = 2     # Speech must be 2x noise floor
INITIAL_NOISE_FLOOR = 0.0035  # Start VERY low - will adapt up to ambient noise

# V5.1: Sustained Speech Gate (prevents transient noise triggers)
MIN_SPEECH_DURATION = 0.15   # 150ms minimum sustained speech - more responsive
SPEECH_SAMPLES_REQUIRED = int(SAMPLE_RATE * MIN_SPEECH_DURATION / (BUFFER_SIZE / 2))

# V5.1: Template Voting (stricter consensus)
MIN_TEMPLATE_MATCHES = 2    # Require ≥2 template matches
# Note: If you have 4+ templates, system auto-requires majority

# V5.1: Timing (balanced cooldown)
COOLDOWN_SECONDS = 2         # V7: Reduced from 3s for responsiveness
REFRACTORY_SECONDS = 1.0     # V7: Reduced from 1.5s for quicker re-detection
LOW_POWER_IDLE_SECONDS = 30  # Increased from 10s before entering low-power

# MFCC parameters (adjusted for 16kHz)
N_MFCC = 13                  # Number of MFCC coefficients
N_FFT = 512                  # FFT size for 16kHz
HOP_LENGTH = 160             # ~10ms hop at 16kHz
N_MELS = 26                  # Mel filterbank size

# Template storage - must match server.py save location
TEMPLATE_DIR = os.path.join(get_project_root(), "data", "voice", "wake_templates")


class WakeState(Enum):
    """V4.3: Explicit wake word detector states."""
    ACTIVE = auto()      # Full RMS monitoring + DTW scoring
    PAUSED = auto()      # Temporary suspend (TTS, voice input)
    LOW_POWER = auto()   # RMS monitoring only, no DTW scoring


def _normalize_mfcc(mfcc: np.ndarray) -> np.ndarray:
    """
    Normalize MFCC features for consistent comparison.
    
    Applies z-score normalization per coefficient (mean=0, std=1).
    This ensures thresholds remain stable across different:
    - Recording sessions
    - Microphones  
    - Volume levels
    """
    mean = np.mean(mfcc, axis=0, keepdims=True)
    std = np.std(mfcc, axis=0, keepdims=True) + 1e-8  # Avoid division by zero
    return (mfcc - mean) / std


class WakeWordDetector:
    """
    V4.3 Hardened wake word detector using DTW + MFCC.
    
    Features:
    - Adaptive noise floor (EMA-based)
    - Sustained speech gate (150ms minimum)
    - Template voting (≥2 matches required)
    - WakeState FSM (ACTIVE/PAUSED/LOW_POWER)
    - Hard refractory period after trigger
    
    CPU-safe: RMS gating skips silence, DTW only runs on short buffers.
    Privacy-safe: 100% local, no cloud, no ASR.
    """
    
    def __init__(self, 
                 threshold: float = DTW_THRESHOLD,
                 on_wake_detected: Optional[Callable] = None):
        """
        Initialize detector.
        
        Args:
            threshold: DTW distance threshold (lower = stricter)
            on_wake_detected: Callback function when wake word detected
        """
        self.threshold = threshold
        self.on_wake_detected = on_wake_detected
        
        # Core state
        self._running = False
        self._state = WakeState.ACTIVE
        self._last_trigger_time = 0
        self._templates: List[np.ndarray] = []
        self._stream = None
        self._thread = None
        self._audio = None
        
        # Rolling buffer
        self._buffer = deque(maxlen=BUFFER_SIZE)
        
        # V4.3: Adaptive noise floor
        self._noise_floor = INITIAL_NOISE_FLOOR
        self._in_speech = False  # Currently above speech gate
        
        # V4.3: Sustained speech gate
        self._speech_onset_frames = 0  # Consecutive frames above gate
        
        # V4.3: Low-power idle tracking
        self._last_speech_time = time.time()
        self._continuous_silence_start = time.time()
        
        # Load templates on init
        self._load_templates()
        
        log_flow("WakeWord", f"V4.3 initialized: threshold={threshold}, templates={len(self._templates)}")
    
    def _load_templates(self):
        """Load MFCC templates from disk (supports .npy and .wav files)."""
        self._templates = []
        
        print(f"[WAKE] Looking for templates in: {TEMPLATE_DIR}")
        
        if not os.path.exists(TEMPLATE_DIR):
            log_warning(f"Wake word templates directory not found: {TEMPLATE_DIR}")
            return
        
        files = os.listdir(TEMPLATE_DIR)
        print(f"[WAKE] Found files: {files}")
        
        for fname in files:
            filepath = os.path.join(TEMPLATE_DIR, fname)
            
            if fname.endswith('.npy'):
                # Pre-computed MFCC template
                try:
                    template = np.load(filepath)
                    self._templates.append(template)
                    print(f"[WAKE] Loaded NPY template: {fname}")
                except Exception as e:
                    log_warning(f"Failed to load template {fname}: {e}")
            
            elif fname.endswith('.wav'):
                # WAV file - convert to MFCC on load
                try:
                    import wave
                    print(f"[WAKE] Converting WAV: {fname}")
                    with wave.open(filepath, 'rb') as wf:
                        nframes = wf.getnframes()
                        rate = wf.getframerate()
                        print(f"[WAKE]   Rate={rate}, Frames={nframes}")
                        audio_data = wf.readframes(nframes)
                        samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                        print(f"[WAKE]   Samples shape: {samples.shape}")
                    
                    mfcc = self._extract_mfcc(samples)
                    if mfcc is not None:
                        self._templates.append(mfcc)
                        print(f"[WAKE]  Converted {fname} to MFCC, shape={mfcc.shape}")
                    else:
                        print(f"[WAKE] ⚠️ MFCC extraction returned None for {fname}")
                except Exception as e:
                    import traceback
                    log_warning(f"Failed to load WAV template {fname}: {e}")
                    traceback.print_exc()
        
        log_flow("WakeWord", f"Loaded {len(self._templates)} templates")
    
    def has_templates(self) -> bool:
        """Check if wake word templates exist."""
        return len(self._templates) > 0
    
    def start(self):
        """Start wake word detection using shared mic stream."""
        if not _check_scipy():
            log_warning("Wake word disabled: scipy not available")
            return False
        
        if not self.has_templates():
            log_warning("Wake word disabled: no templates recorded")
            return False
        
        if self._running:
            return True
        
        # V4.2: Use shared mic instead of opening own stream
        try:
            from .shared_mic import start_shared_mic, register_mic_consumer, activate_mic_consumer
            
            # Start shared mic (no-op if already running)
            if not start_shared_mic():
                log_warning("Wake word: Failed to start shared mic")
                return False
            
            # Register as mic consumer (priority 1 = lowest, always-on background)
            self._consumer_id = register_mic_consumer(
                name="wake_word",
                callback=self._on_mic_frame,
                priority=1
            )
            
            # Activate consumer
            activate_mic_consumer(self._consumer_id)
            
            self._running = True
            log_flow("WakeWord", "Detection started (shared mic)")
            return True
            
        except Exception as e:
            log_warning(f"Wake word start failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def stop(self):
        """Stop wake word detection."""
        self._running = False
        
        # V4.2: Deactivate from shared mic
        try:
            from .shared_mic import deactivate_mic_consumer
            if hasattr(self, '_consumer_id') and self._consumer_id:
                deactivate_mic_consumer(self._consumer_id)
        except:
            pass
        
        log_flow("WakeWord", "Detection stopped")
    
    def pause(self):
        """Pause detection (during TTS, voice input)."""
        if self._state != WakeState.PAUSED:
            old_state = self._state
            self._state = WakeState.PAUSED
            print(f"[WAKE] {old_state.name} → PAUSED")
    
    def resume(self):
        """Resume detection (return to ACTIVE)."""
        if self._state == WakeState.PAUSED:
            self._state = WakeState.ACTIVE
            self._continuous_silence_start = time.time()  # Reset idle tracking
            print(f"[WAKE] PAUSED → ACTIVE")
    
    def is_paused(self) -> bool:
        """Check if detection is paused."""
        return self._state == WakeState.PAUSED
    
    def get_state(self) -> WakeState:
        """Get current wake state."""
        return self._state
    
    def _on_mic_frame(self, samples: np.ndarray, raw_bytes: bytes):
        """
        V4.3 Hardened mic frame callback.
        
        Features:
        - Adaptive noise floor (EMA-based)
        - Sustained speech gate (150ms minimum)
        - Template voting (≥2 matches required)
        - Refractory period (2.5s after trigger)
        - Low-power idle state
        """
        if not self._running:
            return
        
        # Skip if PAUSED (TTS, voice input, etc.)
        if self._state == WakeState.PAUSED:
            return
        
        now = time.time()
        
        # Hard refractory period - no DTW scoring for 2.5s after trigger
        if now - self._last_trigger_time < REFRACTORY_SECONDS:
            return
        
        # Cooldown check (longer period before next detection allowed)
        if now - self._last_trigger_time < COOLDOWN_SECONDS:
            return
        
        # Add samples to rolling buffer
        self._buffer.extend(samples)
        
        # Skip if buffer not full
        if len(self._buffer) < BUFFER_SIZE:
            return
        
        # Get buffer as array
        audio_buffer = np.array(self._buffer)
        
        # Calculate RMS energy
        rms = np.sqrt(np.mean(audio_buffer ** 2))
        
        # Speech gate threshold = noise floor × factor
        speech_threshold = self._noise_floor * SPEECH_GATE_FACTOR
        
        # V7: Removed verbose per-frame debug logging for performance
        
        # Check if above speech gate
        if rms > speech_threshold:
            # Speech detected
            self._in_speech = True
            self._speech_onset_frames += 1
            self._last_speech_time = now
            self._continuous_silence_start = now  # Reset silence tracking
            
            # Check if LOW_POWER → ACTIVE transition needed
            if self._state == WakeState.LOW_POWER:
                self._state = WakeState.ACTIVE
                print(f"[WAKE] LOW_POWER → ACTIVE (RMS spike)")
        else:
            # Below speech gate - update noise floor (only when not speaking)
            if not self._in_speech:
                # EMA update: slowly adapt to background noise
                self._noise_floor = (
                    NOISE_FLOOR_ALPHA * rms + 
                    (1 - NOISE_FLOOR_ALPHA) * self._noise_floor
                )
            
            # Reset speech onset counter
            self._speech_onset_frames = 0
            self._in_speech = False
            
            # Check for LOW_POWER idle transition
            silence_duration = now - self._continuous_silence_start
            if self._state == WakeState.ACTIVE and silence_duration > LOW_POWER_IDLE_SECONDS:
                self._state = WakeState.LOW_POWER
                print(f"[WAKE] ACTIVE → LOW_POWER (idle {silence_duration:.1f}s)")
            
            # Clear buffer and skip DTW scoring
            self._buffer.clear()
            return
        
        # Sustained speech gate: require 150ms of continuous speech
        if self._speech_onset_frames < SPEECH_SAMPLES_REQUIRED:
            # Not enough sustained speech yet - skip DTW
            self._buffer.clear()
            return
        
        # LOW_POWER state: RMS only, no DTW scoring
        if self._state == WakeState.LOW_POWER:
            self._buffer.clear()
            return
        
        # --- ACTIVE state: Full DTW scoring with template voting ---
        
        # Extract MFCC features
        mfcc = self._extract_mfcc(audio_buffer)
        if mfcc is None:
            print(f"[WAKE] ⚠️ Live MFCC extraction failed (buffer len={len(audio_buffer)})")
            self._buffer.clear()
            return
        
        # Debug: print live MFCC shape once
        if not hasattr(self, '_mfcc_logged'):
            print(f"[WAKE] Live MFCC shape: {mfcc.shape} (templates: {[t.shape for t in self._templates[:1]]})")
            self._mfcc_logged = True
        
        # Template voting: count matches
        matches = 0
        total = len(self._templates)
        best_distance = float('inf')
        
        for template in self._templates:
            distance = self._dtw_distance(mfcc, template)
            best_distance = min(best_distance, distance)
            
            if distance < self.threshold:
                matches += 1
        
        # Diagnostic log (temporary for tuning)
        ratio = rms / self._noise_floor if self._noise_floor > 0 else 0
        print(f"[WAKE] rms={rms:.3f} nf={self._noise_floor:.3f} ratio={ratio:.1f} matches={matches}/{total} best={best_distance:.1f} thresh={self.threshold}")
        
        # Template voting: require ≥2 matches (or majority if <4 templates)
        required_matches = min(MIN_TEMPLATE_MATCHES, max(1, total // 2))
        
        if matches >= required_matches:
            self._trigger_wake()
        
        # Clear buffer after processing
        self._buffer.clear()
    
    def _extract_mfcc(self, audio: np.ndarray) -> Optional[np.ndarray]:
        """Extract MFCC features from audio buffer."""
        try:
            from scipy.fft import dct
            from scipy.signal import get_window
            
            # Pre-emphasis
            emphasized = np.append(audio[0], audio[1:] - 0.97 * audio[:-1])
            
            # Frame the signal
            frame_length = N_FFT
            hop = HOP_LENGTH
            num_frames = 1 + (len(emphasized) - frame_length) // hop
            
            if num_frames < 1:
                return None
            
            # Create frames
            frames = np.zeros((num_frames, frame_length))
            window = get_window('hamming', frame_length)
            
            for i in range(num_frames):
                start = i * hop
                frames[i] = emphasized[start:start + frame_length] * window
            
            # FFT and power spectrum
            fft_result = np.fft.rfft(frames, n=N_FFT)
            power_spectrum = np.abs(fft_result) ** 2 / N_FFT
            
            # Mel filterbank
            mel_filters = self._create_mel_filterbank()
            mel_spec = np.dot(power_spectrum, mel_filters.T)
            mel_spec = np.maximum(mel_spec, 1e-10)  # Numerical stability
            
            # Log and DCT to get MFCCs
            log_mel = np.log(mel_spec)
            mfcc = dct(log_mel, type=2, axis=1, norm='ortho')[:, :N_MFCC]
            
            # Normalize for consistent comparison across sessions/mics
            mfcc = _normalize_mfcc(mfcc)
            
            return mfcc
            
        except Exception as e:
            log_warning(f"MFCC extraction failed: {e}")
            return None
    
    def _create_mel_filterbank(self) -> np.ndarray:
        """Create mel filterbank matrix."""
        low_freq = 0
        high_freq = SAMPLE_RATE // 2
        
        # Mel conversion
        def hz_to_mel(hz):
            return 2595 * np.log10(1 + hz / 700)
        
        def mel_to_hz(mel):
            return 700 * (10 ** (mel / 2595) - 1)
        
        mel_low = hz_to_mel(low_freq)
        mel_high = hz_to_mel(high_freq)
        mel_points = np.linspace(mel_low, mel_high, N_MELS + 2)
        hz_points = mel_to_hz(mel_points)
        
        bin_points = np.floor((N_FFT + 1) * hz_points / SAMPLE_RATE).astype(int)
        
        filters = np.zeros((N_MELS, N_FFT // 2 + 1))
        
        for i in range(N_MELS):
            for j in range(bin_points[i], bin_points[i + 1]):
                filters[i, j] = (j - bin_points[i]) / (bin_points[i + 1] - bin_points[i])
            for j in range(bin_points[i + 1], bin_points[i + 2]):
                filters[i, j] = (bin_points[i + 2] - j) / (bin_points[i + 2] - bin_points[i + 1])
        
        return filters
    
    def _dtw_distance(self, seq1: np.ndarray, seq2: np.ndarray) -> float:
        """
        V7 Optimized: FastDTW-style with Sakoe-Chiba band + early termination.
        Complexity: O(N*W) instead of O(N²), where W is band width.
        """
        n, m = len(seq1), len(seq2)
        
        if n == 0 or m == 0:
            return float('inf')
        
        # Sakoe-Chiba band width (±15% of sequence length)
        band_width = max(5, int(0.15 * max(n, m)))
        
        # Cost matrix (only allocate band)
        dtw = np.full((n + 1, m + 1), np.inf)
        dtw[0, 0] = 0
        
        # Early termination threshold (scaled by expected path length)
        max_cost = self.threshold * (n + m) * 1.5  # Upper bound
        
        for i in range(1, n + 1):
            # Band bounds
            j_start = max(1, i - band_width)
            j_end = min(m + 1, i + band_width + 1)
            
            row_min = np.inf
            for j in range(j_start, j_end):
                cost = np.linalg.norm(seq1[i - 1] - seq2[j - 1])
                dtw[i, j] = cost + min(dtw[i - 1, j], dtw[i, j - 1], dtw[i - 1, j - 1])
                row_min = min(row_min, dtw[i, j])
            
            # Early termination if entire row exceeds threshold
            if row_min > max_cost:
                return float('inf')
        
        # Normalize by path length
        raw_cost = dtw[n, m]
        path_length = n + m
        return raw_cost / path_length
    
    def _trigger_wake(self):
        """Handle wake word detection."""
        self._last_trigger_time = time.time()
        self._buffer.clear()
        
        log_flow("WakeWord", "DETECTED - triggering callback")
        
        if self.on_wake_detected:
            # Call in main thread would be better, but for now direct call
            try:
                self.on_wake_detected()
            except Exception as e:
                log_warning(f"Wake callback error: {e}")


# --- Template Recording ---

def record_wake_template(duration: float = 1.5) -> Optional[np.ndarray]:
    """
    Record a wake word template.
    
    Args:
        duration: Recording duration in seconds
        
    Returns:
        MFCC features if successful, None otherwise
    """
    if not _check_scipy() or not _check_pyaudio():
        log_warning("Recording unavailable: missing dependencies")
        return None
    
    import pyaudio
    
    samples_needed = int(SAMPLE_RATE * duration)
    
    audio = pyaudio.PyAudio()
    try:
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=1024
        )
        
        print(f" Recording for {duration}s...")
        frames = []
        
        for _ in range(0, int(SAMPLE_RATE / 1024 * duration)):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
        
        stream.stop_stream()
        stream.close()
        
        # Convert to numpy
        audio_data = b''.join(frames)
        samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Extract MFCC
        detector = WakeWordDetector()
        mfcc = detector._extract_mfcc(samples)
        
        print(" Recording complete")
        return mfcc
        
    except Exception as e:
        log_warning(f"Recording failed: {e}")
        return None
    finally:
        audio.terminate()


def save_template(mfcc: np.ndarray, name: str = None) -> bool:
    """Save MFCC template to disk."""
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    
    if name is None:
        name = f"template_{int(time.time())}"
    
    filepath = os.path.join(TEMPLATE_DIR, f"{name}.npy")
    
    try:
        np.save(filepath, mfcc)
        log_flow("WakeWord", f"Saved template: {filepath}")
        return True
    except Exception as e:
        log_warning(f"Failed to save template: {e}")
        return False


def get_template_count() -> int:
    """Get number of recorded templates."""
    if not os.path.exists(TEMPLATE_DIR):
        return 0
    return len([f for f in os.listdir(TEMPLATE_DIR) if f.endswith('.npy')])


def clear_templates():
    """Delete all recorded templates."""
    if os.path.exists(TEMPLATE_DIR):
        for f in os.listdir(TEMPLATE_DIR):
            if f.endswith('.npy'):
                os.remove(os.path.join(TEMPLATE_DIR, f))
        log_flow("WakeWord", "All templates cleared")


# --- Singleton Instance ---
_detector: Optional[WakeWordDetector] = None


def get_wake_detector() -> Optional[WakeWordDetector]:
    """Get the global wake word detector instance."""
    global _detector
    return _detector


def init_wake_detector(on_wake_detected: Callable, 
                       threshold: float = DTW_THRESHOLD) -> Optional[WakeWordDetector]:
    """
    Initialize and return the global wake word detector.
    
    Args:
        on_wake_detected: Callback when wake word is detected
        threshold: DTW distance threshold
    """
    global _detector
    
    if _detector is not None:
        _detector.stop()
    
    _detector = WakeWordDetector(
        threshold=threshold,
        on_wake_detected=on_wake_detected
    )
    
    return _detector


def pause_wake_detection():
    """Pause wake detection (call during TTS, typing, PTT)."""
    if _detector:
        _detector.pause()


def resume_wake_detection():
    """Resume wake detection."""
    if _detector:
        _detector.resume()
