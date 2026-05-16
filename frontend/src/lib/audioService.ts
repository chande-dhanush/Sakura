/**
 * Sakura V10 Native Audio Service
 * Frontend wrapper for Rust-based native playback (rodio)
 * Resolves volume capping and reliability issues in WebView
 */

import { invoke } from '@tauri-apps/api/core';

const BACKEND_URL = 'http://localhost:3210';

/**
 * Check if CPU is too high for TTS generation
 */
async function shouldSkipForCpu(): Promise<boolean> {
  try {
    const response = await fetch(`${BACKEND_URL}/system/cpu`);
    if (!response.ok) return false;
    const data = await response.json();
    const cpu = Number(data.cpu_percent);
    if (Number.isFinite(cpu) && cpu > 98) {
      console.warn(`[TTS] Skipped: CPU critical (>98%) (${cpu.toFixed(0)}%)`);
      return true;
    }
  } catch (e) {
    console.warn('[TTS] CPU guard unavailable:', e);
  }
  return false;
}

/**
 * Generate and play TTS audio using native Rust backend
 * @param text - Text to speak
 */
export async function speak(text: string): Promise<void> {
  if (!text?.trim()) return;
  
  try {
    if (await shouldSkipForCpu()) {
      throw new Error('Skipped: high CPU');
    }

    // Interrupt any current speech
    await stopSpeaking();
    
    // Tiny delay to ensure stop finishes
    await new Promise(r => setTimeout(r, 20));
    
    console.log('[TTS] Generating audio...');
    const audioPath = await invoke<string>('generate_speech', { text });
    
    console.log('[TTS] Playing via Native Rust...');
    await invoke('play_audio', { path: audioPath });
    
  } catch (error) {
    console.error('[TTS] Failed:', error);
    throw error;
  }
}

/**
 * Interrupt current playback
 */
export async function stopSpeaking(): Promise<void> {
  try {
    await invoke('stop_audio');
    console.log('[TTS] Native playback stopped');
  } catch (e) {
    console.error('[TTS] Failed to stop native playback:', e);
  }
}

/**
 * Check if currently speaking (polled from Rust sink)
 */
export async function isSpeaking(): Promise<boolean> {
  try {
    return await invoke<boolean>('is_audio_playing');
  } catch (e) {
    return false;
  }
}

/**
 * Set global output volume (Native WASAPI session)
 * @param volume - 0.0 to 1.0
 */
export async function setVolume(volume: number): Promise<void> {
  try {
    await invoke('set_audio_volume', { volume });
  } catch (e) {
    console.error('[TTS] Failed to set volume:', e);
  }
}
