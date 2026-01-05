<script>
    import { fade, fly } from 'svelte/transition';
    import { backendStatus } from '$lib/stores/chat.js';
    
    let groqKey = "";
    let tavilyKey = "";
    let openRouterKey = "";
    let spotifyClientId = "";
    let spotifyClientSecret = "";
    let micIndex = "";  // Optional override
    
    let showAdvanced = false;
    let isSubmitting = false;
    let error = "";
    let success = "";
    
    export let isUpdateMode = false;
    export let onClose = () => {};
    
    // BACKEND_URL from environment or default
    const BACKEND_URL = "http://localhost:8000"; // Should match chat.js

    async function handleSubmit() {
        if (!groqKey.trim()) {
            error = "Groq API Key is required to power the brain 🧠";
            return;
        }
        
        isSubmitting = true;
        error = "";
        
        try {
            const res = await fetch(`${BACKEND_URL}/setup`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    GROQ_API_KEY: groqKey.trim(),
                    TAVILY_API_KEY: tavilyKey.trim(),
                    OPENROUTER_API_KEY: openRouterKey.trim(),
                    SPOTIPY_CLIENT_ID: spotifyClientId.trim(),
                    SPOTIPY_CLIENT_SECRET: spotifyClientSecret.trim(),
                    MICROPHONE_INDEX: micIndex.trim()
                })
            });
            
            const data = await res.json();
            
            if (data.success) {
                success = "Configuration saved! Rebooting brain...";
                setTimeout(() => {
                    // Force re-check of backend status to switch to Chat view
                    backendStatus.set("connected"); 
                    location.reload(); // Simple reload to clear state and re-fetch health
                }, 1500);
            } else {
                error = data.message || "Setup failed. Check keys.";
            }
        } catch (e) {
            error = "Connection failed: " + e.message;
        } finally {
            isSubmitting = false;
        }
    }
</script>

<div class="setup-container" in:fade>
    <div class="setup-card" in:fly={{ y: 20, duration: 600 }}>
        <!-- Close Button (only in Update Mode) -->
        {#if isUpdateMode}
            <button class="close-btn" on:click={onClose}>×</button>
        {/if}

        <div class="header">
            <div class="logo">🌸</div>
            <h1>{isUpdateMode ? 'Settings' : 'Welcome to Sakura'}</h1>
            <p>
                {isUpdateMode 
                    ? 'Update configurations. WARNING: This will overwrite existing keys.' 
                    : "Let's get you set up. I need a few keys to wake up my brain."}
            </p>
        </div>
        
        <div class="scroll-container">
            <div class="form-group">
                <label for="groq">
                    Groq API Key <span class="required">(Required)</span>
                </label>
                <input 
                    id="groq" 
                    type="password" 
                    bind:value={groqKey} 
                    placeholder="gsk_..." 
                    class:error={error && !groqKey}
                />
                <small>Get free key at <a href="https://console.groq.com" target="_blank">console.groq.com</a></small>
            </div>

            <div class="form-group">
                <label for="tavily">
                    Tavily API Key <span class="optional">(Recommended)</span>
                </label>
                <input 
                    id="tavily" 
                    type="password" 
                    bind:value={tavilyKey} 
                    placeholder="tvly-..." 
                />
            </div>

            <div class="form-group">
                <label for="openrouter">
                    OpenRouter Key <span class="optional">(Optional)</span>
                </label>
                <input 
                    id="openrouter" 
                    type="password" 
                    bind:value={openRouterKey} 
                    placeholder="sk-or-..." 
                />
            </div>

            <!-- Advanced Toggle -->
            <button class="toggle-advanced" on:click={() => showAdvanced = !showAdvanced}>
                {showAdvanced ? '▼ Hide Advanced' : '▶ Show Advanced (Spotify, Mic)'}
            </button>

            {#if showAdvanced}
                <div class="advanced-section" transition:fade>
                    <div class="form-group">
                        <label for="spotify-id">Spotify Client ID</label>
                        <input id="spotify-id" type="text" bind:value={spotifyClientId} placeholder="Client ID from dashboard" />
                    </div>
                    <div class="form-group">
                        <label for="spotify-secret">Spotify Client Secret</label>
                        <input id="spotify-secret" type="password" bind:value={spotifyClientSecret} placeholder="Client Secret" />
                    </div>
                    <div class="form-group">
                        <label for="mic-index">Microphone Index (Optional)</label>
                        <input id="mic-index" type="number" bind:value={micIndex} placeholder="Default: 1" />
                        <small>Change only if voice detection fails.</small>
                    </div>
                </div>
            {/if}
        </div>

        {#if error}
            <div class="error-msg" transition:fade>{error}</div>
        {/if}
        
        {#if success}
            <div class="success-msg" transition:fade>{success}</div>
        {/if}

        <div class="actions">
            {#if isUpdateMode}
                <button class="cancel-btn" on:click={onClose} disabled={isSubmitting}>Cancel</button>
            {/if}
            <button class="submit-btn" on:click={handleSubmit} disabled={isSubmitting}>
                {#if isSubmitting}
                    Connecting...
                {:else}
                    {isUpdateMode ? 'Update Configuration' : 'Wake Up Sakura 🌸'}
                {/if}
            </button>
        </div>
        
        <div class="footer">
            <p>Keys are stored locally in %APPDATA%/SakuraV10</p>
        </div>
    </div>
</div>

<style>
    /* ===== SETUP CONTAINER (Full-screen overlay) ===== */
    .setup-container {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 9999;
        color: white;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* ===== SETUP CARD (Glassmorphism) ===== */
    .setup-card {
        position: relative;
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 40px;
        border-radius: 24px;
        width: 100%;
        max-width: 480px;
        max-height: 90vh;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
        overflow: hidden;
    }
    
    /* ===== HEADER ===== */
    .header {
        text-align: center;
        margin-bottom: 30px;
    }
    
    .logo {
        font-size: 48px;
        margin-bottom: 10px;
        filter: drop-shadow(0 0 15px rgba(255, 105, 180, 0.6));
    }
    
    .header h1 {
        margin: 0;
        font-size: 28px;
        font-weight: 600;
        background: linear-gradient(to right, #fff, #ffb6c1);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .header p {
        color: rgba(255, 255, 255, 0.6);
        font-size: 14px;
        margin-top: 8px;
    }
    
    /* ===== CLOSE BUTTON ===== */
    .close-btn {
        position: absolute;
        top: 20px;
        right: 20px;
        background: none;
        border: none;
        color: rgba(255, 255, 255, 0.5);
        font-size: 24px;
        cursor: pointer;
        transition: color 0.2s;
        z-index: 10;
    }
    .close-btn:hover { color: white; }
    
    /* ===== SCROLL CONTAINER ===== */
    .scroll-container {
        max-height: 50vh;
        overflow-y: auto;
        padding-right: 8px;
        margin-bottom: 20px;
    }
    
    /* ===== FORM ELEMENTS ===== */
    .form-group {
        margin-bottom: 20px;
        display: flex;
        flex-direction: column;
        gap: 8px;
    }
    
    label {
        font-size: 13px;
        font-weight: 500;
        color: rgba(255, 255, 255, 0.8);
    }
    
    .required { color: #ff6b6b; font-size: 11px; }
    .optional { color: rgba(255, 255, 255, 0.4); font-size: 11px; }
    
    input {
        background: rgba(0, 0, 0, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 12px 16px;
        border-radius: 12px;
        color: white;
        font-size: 14px;
        transition: all 0.2s;
        outline: none;
        width: 100%;
        box-sizing: border-box;
    }
    
    input:focus {
        border-color: #ffb6c1;
        background: rgba(0, 0, 0, 0.5);
        box-shadow: 0 0 0 2px rgba(255, 182, 193, 0.2);
    }
    
    input.error {
        border-color: #ff6b6b;
    }
    
    small {
        font-size: 11px;
        color: rgba(255, 255, 255, 0.4);
    }
    
    small a { color: #ffb6c1; text-decoration: none; }
    small a:hover { text-decoration: underline; }
    
    /* ===== TOGGLE ADVANCED ===== */
    .toggle-advanced {
        background: none;
        border: none;
        color: rgba(255, 255, 255, 0.5);
        font-size: 12px;
        cursor: pointer;
        padding: 8px 0;
        margin-bottom: 10px;
        text-align: left;
        width: 100%;
    }
    .toggle-advanced:hover { color: #ffb6c1; }
    
    .advanced-section {
        border-top: 1px solid rgba(255, 255, 255, 0.1);
        padding-top: 15px;
        margin-top: 5px;
    }
    
    /* ===== ACTIONS (Buttons) ===== */
    .actions {
        display: flex;
        gap: 10px;
        margin-top: 10px;
    }

    .cancel-btn {
        flex: 1;
        padding: 14px;
        background: rgba(255, 255, 255, 0.1);
        border: none;
        border-radius: 12px;
        color: rgba(255, 255, 255, 0.8);
        font-weight: 600;
        font-size: 16px;
        cursor: pointer;
        transition: background 0.2s;
    }
    .cancel-btn:hover {
        background: rgba(255, 255, 255, 0.15);
    }
    
    .submit-btn {
        flex: 2;
        padding: 14px;
        background: linear-gradient(135deg, #ff6b6b, #ffb6c1);
        border: none;
        border-radius: 12px;
        color: #fff;
        font-weight: 600;
        font-size: 16px;
        cursor: pointer;
        transition: all 0.2s;
        text-shadow: 0 1px 2px rgba(0,0,0,0.2);
    }
    
    .submit-btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(255, 107, 107, 0.3);
    }
    
    .submit-btn:disabled {
        opacity: 0.7;
        cursor: not-allowed;
        transform: none;
    }
    
    /* ===== MESSAGES ===== */
    .error-msg {
        background: rgba(255, 107, 107, 0.2);
        color: #ffb6c1;
        font-size: 13px;
        padding: 10px;
        border-radius: 8px;
        margin-bottom: 20px;
        text-align: center;
        border: 1px solid rgba(255, 107, 107, 0.3);
    }

    .success-msg {
        background: rgba(46, 204, 113, 0.2);
        color: #2ecc71;
        font-size: 13px;
        padding: 10px;
        border-radius: 8px;
        margin-bottom: 20px;
        text-align: center;
        border: 1px solid rgba(46, 204, 113, 0.3);
    }
    
    /* ===== FOOTER ===== */
    .footer {
        text-align: center;
        margin-top: 24px;
        font-size: 12px;
        color: rgba(255, 255, 255, 0.3);
    }
    .footer p { margin: 0; }
</style>
