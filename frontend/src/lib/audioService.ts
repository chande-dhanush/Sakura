/**
 * Sakura V18 Audio Service
 * Frontend-based TTS playback using HTML5 Audio API
 * Bypasses pygame.mixer issues in Tauri production builds
 */

import { invoke } from '@tauri-apps/api/core';
import { convertFileSrc } from '@tauri-apps/api/core';
import { remove, readFile } from '@tauri-apps/plugin-fs';

let currentAudio: HTMLAudioElement | null = null;
const BACKEND_URL = 'http://localhost:3210';

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
 * Generate and play TTS audio
 * @param text - Text to speak
 */
export async function speak(text: string): Promise<void> {
  // Guard empty text
  if (!text?.trim()) {
    console.warn('[TTS] Empty text, skipping');
    return;
  }
  
  try {
    if (await shouldSkipForCpu()) {
      throw new Error('Skipped: high CPU');
    }

    // Stop any current playback
    stopSpeaking();
    
    // Small delay to let stop complete (race condition fix)
    await new Promise(r => setTimeout(r, 50));
    
    console.log('[TTS] Generating audio for:', text.slice(0, 50) + '...');
    
    // Generate audio via backend
    const audioPath = await invoke<string>('generate_speech', { text });
    console.log('[TTS] Audio generated:', audioPath);
    
    // V19.5: Audio Playback with Blob Fallback
    // This is the most robust method for Tauri v2 on Windows
    let assetUrl = convertFileSrc(audioPath);
    console.log('[TTS] Primary Asset URL:', assetUrl);

    currentAudio = new Audio(assetUrl);
    
    // Add Blob fallback for 'no supported source' or protocol errors
    const playWithFallback = async () => {
      try {
        console.log('[TTS] Attempting playback...');
        currentAudio!.volume = 1.0; // Ensure volume is 100%
        await currentAudio!.play();
        console.log('[TTS] ✓ Playing audio');
      } catch (err) {
        console.warn('[TTS] Playback error:', err);
        console.log('[TTS] Trying Blob fallback...');
        try {
          const data = await readFile(audioPath);
          const blob = new Blob([data], { type: 'audio/wav' });
          const blobUrl = URL.createObjectURL(blob);
          
          currentAudio = new Audio(blobUrl);
          currentAudio.volume = 1.0; // Ensure volume is 100%
          currentAudio.onended = () => {
            URL.revokeObjectURL(blobUrl);
            cleanup(audioPath);
          };
          await currentAudio.play();
          console.log('[TTS] ✓ Playing audio via Blob');
        } catch (fallbackErr) {
          console.error('[TTS] Both play methods failed:', fallbackErr);
        }
      }
    };

    const cleanup = async (path: string) => {
      console.log('[TTS] Cleaning up...');
      try {
        await remove(path);
        console.log('[TTS] ✓ Audio file deleted');
      } catch (e) {
        console.warn('[TTS] Cleanup failed:', e);
      }
      currentAudio = null;
    };

    currentAudio.onended = () => cleanup(audioPath);
    await playWithFallback();
    
  } catch (error) {
    console.error('[TTS] Failed:', error);
    throw error;
  }
}

/**
 * Stop current TTS playback
 */
export function stopSpeaking(): void {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
    console.log('[TTS] Stopped');
  }
}

/**
 * Check if TTS is currently playing
 */
export function isSpeaking(): boolean {
  return currentAudio !== null && !currentAudio.paused;
}
