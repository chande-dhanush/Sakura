"""
Sakura V13 Audio Tools
======================
Audio transcription and summarization using existing Google STT infrastructure.

Dependencies:
- speech_recognition (already installed for voice_engine)
- pydub (add to requirements.txt for audio conversion)
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool


def _get_uploads_dir() -> Path:
    """Get the uploads directory path."""
    from sakura_assistant.utils.pathing import get_project_root
    uploads = Path(get_project_root()) / "uploads"
    uploads.mkdir(exist_ok=True)
    return uploads


def _convert_to_wav(audio_path: str) -> str:
    """
    Convert audio file to WAV format using pydub.
    
    Args:
        audio_path: Path to source audio file
        
    Returns:
        Path to converted WAV file
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError(
            "pydub is required for audio processing. "
            "Install with: pip install pydub\n"
            "Also requires ffmpeg: https://ffmpeg.org/"
        )
    
    # V13: Check ffmpeg availability before attempting conversion
    import subprocess
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, timeout=5)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        raise EnvironmentError(
            "ffmpeg is not installed or not in PATH. "
            "Audio conversion requires ffmpeg.\n"
            "Install from: https://ffmpeg.org/ or use 'winget install FFmpeg'"
        )
    
    source_path = Path(audio_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    # If already WAV, return as-is
    if source_path.suffix.lower() == ".wav":
        return str(source_path)
    
    # Load and convert
    try:
        extension = source_path.suffix.lower().replace(".", "")
        audio = AudioSegment.from_file(str(source_path), format=extension)
        
        # Export to temp WAV
        wav_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        audio.export(wav_path, format="wav")
        
        return wav_path
    except Exception as e:
        raise RuntimeError(
            f"Failed to convert audio file: {e}\n"
            "Ensure ffmpeg is properly installed and the audio file is valid."
        )


def _transcribe_wav(wav_path: str, language: str = "en-US") -> str:
    """
    Transcribe WAV file using Google Speech Recognition (free tier).
    
    This reuses the same approach as VoiceEngine._listen_for_command().
    
    Args:
        wav_path: Path to WAV file
        language: Language code (default: en-US)
        
    Returns:
        Transcript text
    """
    import speech_recognition as sr
    
    recognizer = sr.Recognizer()
    
    with sr.AudioFile(wav_path) as source:
        audio_data = recognizer.record(source)
    
    try:
        # Use Google's free tier (no API key required)
        transcript = recognizer.recognize_google(audio_data, language=language)
        return transcript
    except sr.UnknownValueError:
        return "[Audio could not be understood]"
    except sr.RequestError as e:
        return f"[Google Speech API error: {e}]"


@tool
def transcribe_audio(file_path: str, language: str = "en-US") -> str:
    """
    Transcribe an audio file using Google Speech Recognition (free tier).
    
    Supports: WAV, MP3, M4A, OGG, FLAC (requires ffmpeg for non-WAV formats).
    
    Args:
        file_path: Path to audio file (can be in uploads/ or absolute path)
        language: Language code (default: en-US)
        
    Returns:
        Transcript text
        
    Example:
        transcribe_audio("meeting_recording.mp3")
    """
    # Resolve path
    if not os.path.isabs(file_path):
        file_path = str(_get_uploads_dir() / file_path)
    
    if not os.path.exists(file_path):
        return f"Error: File not found: {file_path}"
    
    try:
        # Convert to WAV if needed
        wav_path = _convert_to_wav(file_path)
        
        # Transcribe
        transcript = _transcribe_wav(wav_path, language)
        
        # Cleanup temp file if we created one
        if wav_path != file_path and os.path.exists(wav_path):
            os.unlink(wav_path)
        
        word_count = len(transcript.split())
        return f"📝 Transcript ({word_count} words):\n\n{transcript}"
        
    except ImportError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error transcribing audio: {e}"


@tool
def summarize_audio(
    file_path: str, 
    style: str = "concise",
    language: str = "en-US"
) -> str:
    """
    Transcribe audio file and generate an LLM summary.
    
    Uses Google STT (free tier) + existing responder LLM for summarization.
    
    Args:
        file_path: Path to audio file
        style: Summary style - "concise" (default), "detailed", or "bullet_points"
        language: Language code (default: en-US)
        
    Returns:
        Audio summary with key points
        
    Example:
        summarize_audio("lecture.mp3", style="bullet_points")
    """
    # First transcribe
    if not os.path.isabs(file_path):
        file_path = str(_get_uploads_dir() / file_path)
    
    if not os.path.exists(file_path):
        return f"Error: File not found: {file_path}"
    
    try:
        # Convert and transcribe
        wav_path = _convert_to_wav(file_path)
        transcript = _transcribe_wav(wav_path, language)
        
        # Cleanup temp file
        if wav_path != file_path and os.path.exists(wav_path):
            os.unlink(wav_path)
        
        if transcript.startswith("["):
            return transcript  # Error message
        
        word_count = len(transcript.split())
        
        # Too short to summarize
        if word_count < 30:
            return f"📝 Audio content ({word_count} words):\n\n{transcript}"
        
        # Generate summary using existing LLM
        from sakura_assistant.core.container import get_container
        
        container = get_container()
        responder = container.models.get("responder")
        
        if not responder:
            return f"📝 Transcript (no LLM available for summary):\n\n{transcript}"
        
        # Style-specific prompts
        style_prompts = {
            "concise": "Summarize this transcript in 2-3 sentences:",
            "detailed": "Provide a detailed summary of this transcript with main points and context:",
            "bullet_points": "Summarize this transcript as bullet points (• format):"
        }
        
        prompt = f"""{style_prompts.get(style, style_prompts["concise"])}

{transcript}

Summary:"""
        
        from langchain_core.messages import HumanMessage
        response = responder.invoke([HumanMessage(content=prompt)])
        summary = response.content.strip()
        
        return f"""🎧 Audio Summary ({style})

{summary}

---
Source: {Path(file_path).name} ({word_count} words transcribed)"""
        
    except ImportError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error summarizing audio: {e}"


# Export tools for registration
AUDIO_TOOLS = [transcribe_audio, summarize_audio]
