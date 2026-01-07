<!-- 
    VoiceSetup.svelte - Wake Word Template Recording Component
    Records 5 samples of user saying "Sakura" using the BACKEND microphone (PyAudio)
-->
<script>
    import { createEventDispatcher } from 'svelte';
    import { checkVoiceStatus } from '$lib/stores/chat.js';
    
    const dispatch = createEventDispatcher();
    
    let step = 0; // 0 = intro, 1-3 = recording steps, 4 = done
    let isRecording = false;
    let countdown = 0;
    let error = null;
    
    const BACKEND_URL = 'http://localhost:8000';
    
    async function startRecording() {
        error = null;
        
        // Countdown first
        countdown = 3;
        const interval = setInterval(() => {
            countdown--;
            if (countdown === 0) {
                clearInterval(interval);
                doBackendRecord();
            }
        }, 1000);
    }
    
    async function doBackendRecord() {
        isRecording = true;
        
        try {
            // Call backend to record with PyAudio (2 seconds)
            const response = await fetch(`${BACKEND_URL}/voice/record-template`, {
                method: 'POST'
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                step++;
                if (step > 3) {
                    // Refresh voice status
                    await checkVoiceStatus();
                }
            } else {
                error = result.error || 'Failed to record. Please try again.';
            }
        } catch (e) {
            console.error('Recording error:', e);
            error = 'Failed to connect to backend.';
        }
        
        isRecording = false;
    }
    
    function close() {
        dispatch('close');
    }
</script>

<div class="voice-setup-overlay" 
    on:click|self={close} 
    on:keydown|stopPropagation
    role="dialog" 
    aria-modal="true"
    tabindex="0">
    <div class="voice-setup-modal">
        <button class="close-btn" on:click={close}>×</button>
        
        {#if step === 0}
            <!-- INTRO -->
            <div class="step-content">
                <div class="icon">🎤</div>
                <h2>Set Up Voice Wake Word</h2>
                <p>You'll record yourself saying <strong>"Sakura"</strong> three times. This helps the AI recognize when you're calling it.</p>
                <p class="hint">Make sure your microphone is connected!</p>
                <button class="primary-btn" on:click={() => { step = 1; }}>
                    Start Recording
                </button>
            </div>
            
        {:else if step <= 5}
            <!-- RECORDING STEPS -->
            <div class="step-content">
                <div class="progress-dots">
                    {#each [1, 2, 3, 4, 5] as i}
                        <div class="dot" class:active={step === i} class:done={step > i}></div>
                    {/each}
                </div>
                
                <h2>Recording {step} of 5</h2>
                <p>Say <strong>"Sakura"</strong> clearly when recording starts</p>
                
                {#if countdown > 0}
                    <div class="countdown">{countdown}</div>
                    <p class="hint">Get ready...</p>
                {:else if isRecording}
                    <div class="recording-indicator">
                        <div class="pulse-ring"></div>
                        <span>🎙️</span>
                    </div>
                    <p class="recording-text">Recording... Say "Sakura" now!</p>
                {:else}
                    <button class="primary-btn" on:click={startRecording}>
                        🎙️ Record "Sakura"
                    </button>
                {/if}
                
                {#if error}
                    <p class="error">{error}</p>
                {/if}
            </div>
            
        {:else}
            <!-- DONE -->
            <div class="step-content">
                <div class="icon success">✅</div>
                <h2>Voice Setup Complete!</h2>
                <p>Wake word detection is now configured. You can say "Sakura" to activate the assistant.</p>
                <p class="hint">Restart the app for wake word to take effect.</p>
                <button class="primary-btn" on:click={close}>
                    Done
                </button>
            </div>
        {/if}
    </div>
</div>

<style>
    .voice-setup-overlay {
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0, 0, 0, 0.7);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 2000;
        backdrop-filter: blur(4px);
    }
    
    .voice-setup-modal {
        background: rgba(20, 20, 30, 0.98);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 32px;
        width: 320px;
        position: relative;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
    }
    
    .close-btn {
        position: absolute;
        top: 12px;
        right: 12px;
        background: transparent;
        border: none;
        color: rgba(255, 255, 255, 0.5);
        font-size: 24px;
        cursor: pointer;
        width: 32px;
        height: 32px;
        border-radius: 8px;
        transition: all 0.15s;
    }
    
    .close-btn:hover {
        background: rgba(255, 255, 255, 0.1);
        color: white;
    }
    
    .step-content {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        gap: 16px;
    }
    
    .icon {
        font-size: 48px;
    }
    
    .icon.success {
        font-size: 56px;
    }
    
    h2 {
        font-size: 18px;
        font-weight: 600;
        color: white;
        margin: 0;
    }
    
    p {
        font-size: 14px;
        color: rgba(255, 255, 255, 0.6);
        margin: 0;
        line-height: 1.5;
    }
    
    p strong {
        color: #8888ff;
    }
    
    .hint {
        font-size: 12px;
        color: rgba(255, 255, 255, 0.4);
    }
    
    .primary-btn {
        background: linear-gradient(135deg, #8888ff 0%, #6666dd 100%);
        border: none;
        color: white;
        padding: 12px 24px;
        border-radius: 10px;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s;
        margin-top: 8px;
    }
    
    .primary-btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 20px rgba(136, 136, 255, 0.4);
    }
    
    .progress-dots {
        display: flex;
        gap: 8px;
        margin-bottom: 8px;
    }
    
    .dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.2);
        transition: all 0.2s;
    }
    
    .dot.active {
        background: #8888ff;
        box-shadow: 0 0 10px rgba(136, 136, 255, 0.5);
    }
    
    .dot.done {
        background: #44ff88;
    }
    
    .countdown {
        font-size: 64px;
        font-weight: 700;
        color: #8888ff;
        animation: pulse 1s ease-in-out;
    }
    
    .recording-indicator {
        position: relative;
        font-size: 48px;
    }
    
    .pulse-ring {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        width: 80px;
        height: 80px;
        border: 2px solid #ff4444;
        border-radius: 50%;
        animation: pulse-ring 1s ease-out infinite;
    }
    
    .recording-text {
        color: #ff6666;
        font-weight: 500;
    }
    
    .error {
        color: #ff6666;
        font-size: 12px;
    }
    
    @keyframes pulse-ring {
        0% { transform: translate(-50%, -50%) scale(0.8); opacity: 1; }
        100% { transform: translate(-50%, -50%) scale(1.5); opacity: 0; }
    }
    
    @keyframes pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.1); }
    }
</style>
