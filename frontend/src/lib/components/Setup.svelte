<script>
    import { fade, fly } from 'svelte/transition';
    import { onMount } from 'svelte';
    import { backendStatus } from '$lib/stores/chat.js';
    
    // BACKEND_URL logic
    const BACKEND_URL = "http://localhost:3210"; 
    
    // Configuration State
    let config = {
        GROQ_API_KEY: "",
        TAVILY_API_KEY: "",
        OPENROUTER_API_KEY: "",
        GOOGLE_API_KEY: "",
        SPOTIFY_CLIENT_ID: "",
        SPOTIFY_CLIENT_SECRET: "",
        SPOTIFY_DEVICE_NAME: "",
        MICROPHONE_INDEX: "",
        USER_NAME: "",
        USER_LOCATION: "",
        USER_BIO: ""
    };

    // UI Props
    export let isUpdateMode = false;
    export let onClose = () => {};

    // Internal State
    let originalConfig = {};
    let dirtyFields = new Set(); // Senior pattern: O(1) lookups
    
    let isSubmitting = false;
    let isLoading = false;
    let error = "";
    let success = "";
    let showAdvanced = false;

    // Load Settings
    onMount(async () => {
        if (isUpdateMode) {
            isLoading = true;
            try {
                const res = await fetch(`${BACKEND_URL}/settings`);
                if (res.ok) {
                    const data = await res.json();
                    
                    // Map backend response to config
                    config = {
                        GROQ_API_KEY: data.GROQ_API_KEY || "",
                        TAVILY_API_KEY: data.TAVILY_API_KEY || "",
                        OPENROUTER_API_KEY: data.OPENROUTER_API_KEY || "",
                        GOOGLE_API_KEY: data.GOOGLE_API_KEY || "",
                        SPOTIFY_CLIENT_ID: data.SPOTIFY_CLIENT_ID || "",
                        SPOTIFY_CLIENT_SECRET: "", // Never return secrets
                        SPOTIFY_DEVICE_NAME: "", // Optional
                        MICROPHONE_INDEX: "",
                        USER_NAME: data.USER_NAME || "",
                        USER_LOCATION: data.USER_LOCATION || "",
                        USER_BIO: data.USER_BIO || ""
                    };
                    
                    // Clone for comparison
                    originalConfig = { ...config };
                    console.log("[Settings] Loaded existing values");
                }
            } catch (e) {
                console.error("[Settings] Failed to load:", e);
                error = "Failed to load settings from brain.";
            } finally {
                isLoading = false;
            }
        }
    });

    // Reactive Input Handler (Dirty Tracking)
    function handleInput(field, value) {
        config[field] = value;
        
        // Classic dirty check: Does current value differ from original?
        if (value !== originalConfig[field]) {
            dirtyFields.add(field);
        } else {
            dirtyFields.delete(field);
        }
        dirtyFields = dirtyFields; // Trigger Svelte reactivity
    }

    // Google Auth File Upload
    async function handleGoogleUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        isSubmitting = true;
        
        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch(`${BACKEND_URL}/settings/google-auth`, {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            
            if (data.success) {
                success = "Credentials uploaded! Auth ready.";
                setTimeout(() => success = "", 3000);
            } else {
                error = data.message || "Upload failed";
            }
        } catch (e) {
            error = "Upload error: " + e.message;
        } finally {
            isSubmitting = false;
        }
    }

    // Save Changes (PATCH)
    async function handleSubmit() {
        if (dirtyFields.size === 0) {
            return; // Nothing to save
        }
        
        isSubmitting = true;
        error = "";
        success = "";
        
        try {
            // Build payload with ONLY dirty fields
            const payload = {};
            dirtyFields.forEach(field => {
                payload[field] = config[field].trim();
            });

            const res = await fetch(`${BACKEND_URL}/settings`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            
            const data = await res.json();
            
            if (data.success) {
                success = "Settings updated successfully!";
                
                // Reset state to new baseline
                originalConfig = { ...config };
                dirtyFields.clear();
                dirtyFields = dirtyFields;
                
                // If not update mode (first setup), reload to start
                if (!isUpdateMode) {
                    setTimeout(() => {
                        backendStatus.set("connected");
                        location.reload();
                    }, 1500);
                }
            } else {
                error = data.message || "Update failed.";
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
            <!-- GROQ -->
            <div class="form-group">
                <label for="groq">Groq API Key <span class="required">(Required)</span></label>
                <div class="input-wrapper">
                    <input 
                        id="groq" 
                        type="password" 
                        value={config.GROQ_API_KEY}
                        on:input={(e) => handleInput('GROQ_API_KEY', e.target.value)}
                        placeholder="gsk_••••••••"
                        class:error={error && !config.GROQ_API_KEY}
                    />
                    {#if dirtyFields.has('GROQ_API_KEY')}
                        <span class="badge-changed" in:fade>Modified</span>
                    {/if}
                </div>
                <small>Get free key at <a href="https://console.groq.com" target="_blank">console.groq.com</a></small>
            </div>

            <!-- TAVILY -->
            <div class="form-group">
                <label for="tavily">Tavily API Key <span class="optional">(Recommended)</span></label>
                <div class="input-wrapper">
                    <input 
                        id="tavily" 
                        type="password"
                        value={config.TAVILY_API_KEY}
                        on:input={(e) => handleInput('TAVILY_API_KEY', e.target.value)}
                        placeholder="tvly-••••••••"
                    />
                    {#if dirtyFields.has('TAVILY_API_KEY')}
                        <span class="badge-changed" in:fade>Modified</span>
                    {/if}
                </div>
            </div>

            <!-- GOOGLE / GMAIL AUTH -->
            <div class="section-title">📧 Gmail & Calendar (Google Auth)</div>
            <div class="form-group">
                <label>Google Credentials (credentials.json)</label>
                <div class="file-upload-row">
                    <input 
                        type="file" 
                        accept=".json" 
                        on:change={handleGoogleUpload} 
                        id="google-upload"
                        class="file-input"
                    />
                    <label for="google-upload" class="file-label">
                        📁 Upload credentials.json
                    </label>
                    <small style="margin-left: 10px; color: #aaa;">Required for Gmail/Calendar tools</small>
                </div>
            </div>
            
            <div class="form-group">
                <label for="google">Google API Key (Gemini Backup)</label>
                <div class="input-wrapper">
                    <input 
                        id="google" 
                        type="password"
                        value={config.GOOGLE_API_KEY}
                        on:input={(e) => handleInput('GOOGLE_API_KEY', e.target.value)}
                        placeholder="AIza••••••••"
                    />
                    {#if dirtyFields.has('GOOGLE_API_KEY')}
                        <span class="badge-changed" in:fade>Modified</span>
                    {/if}
                </div>
            </div>

            <!-- USER PROFILE -->
            <div class="section-title">👤 User Profile</div>
            
            <div class="form-group">
                <label for="user-name">Your Name</label>
                <input id="user-name" type="text" value={config.USER_NAME} on:input={(e) => handleInput('USER_NAME', e.target.value)} placeholder="e.g. Alex" />
            </div>
            <div class="form-group">
                <label for="user-location">Location</label>
                <input id="user-location" type="text" value={config.USER_LOCATION} on:input={(e) => handleInput('USER_LOCATION', e.target.value)} placeholder="e.g. Bangalore" />
            </div>
            <div class="form-group">
                <label for="user-bio">Short Bio</label>
                <input id="user-bio" type="text" value={config.USER_BIO} on:input={(e) => handleInput('USER_BIO', e.target.value)} placeholder="e.g. AI engineer" />
            </div>

            <!-- Advanced Toggle -->
            <button class="toggle-advanced" on:click={() => showAdvanced = !showAdvanced}>
                {showAdvanced ? '▼ Hide Advanced' : '▶ Show Advanced (Spotify, OpenRouter)'}
            </button>

            {#if showAdvanced}
                <div class="advanced-section" transition:fade>
                    <div class="form-group">
                        <label for="openrouter">OpenRouter Key</label>
                        <div class="input-wrapper">
                            <input 
                                id="openrouter" 
                                type="password" 
                                value={config.OPENROUTER_API_KEY}
                                on:input={(e) => handleInput('OPENROUTER_API_KEY', e.target.value)}
                                placeholder="sk-or-••••••••" 
                            />
                            {#if dirtyFields.has('OPENROUTER_API_KEY')}
                                <span class="badge-changed" in:fade>Modified</span>
                            {/if}
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label for="spotify-id">Spotify Client ID</label>
                        <div class="input-wrapper">
                            <input 
                                id="spotify-id" 
                                type="text" 
                                value={config.SPOTIFY_CLIENT_ID}
                                on:input={(e) => handleInput('SPOTIFY_CLIENT_ID', e.target.value)}
                                placeholder="Client ID" 
                            />
                            {#if dirtyFields.has('SPOTIFY_CLIENT_ID')}
                                <span class="badge-changed" in:fade>Modified</span>
                            {/if}
                        </div>
                    </div>

                    <div class="form-group">
                        <label for="spotify-secret">Spotify Client Secret</label>
                        <div class="input-wrapper">
                            <input 
                                id="spotify-secret" 
                                type="password" 
                                value={config.SPOTIFY_CLIENT_SECRET}
                                on:input={(e) => handleInput('SPOTIFY_CLIENT_SECRET', e.target.value)}
                                placeholder="Client Secret (Write-Only)" 
                            />
                            {#if dirtyFields.has('SPOTIFY_CLIENT_SECRET')}
                                <span class="badge-changed" in:fade>Modified</span>
                            {/if}
                        </div>
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
            <button 
                class="submit-btn" 
                on:click={handleSubmit} 
                disabled={isSubmitting || dirtyFields.size === 0}
            >
                {#if isSubmitting}
                    Saving...
                {:else}
                    {isUpdateMode ? (dirtyFields.size > 0 ? 'Save Changes' : 'No Changes') : 'Wake Up Sakura 🌸'}
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
        max-height: 85vh;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
        display: flex;
        flex-direction: column;
        overflow: visible;
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
        flex: 1;
        min-height: 0;
        max-height: 40vh;
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
    
    .section-title {
        font-size: 14px;
        font-weight: 600;
        color: rgba(255, 255, 255, 0.7);
        margin: 20px 0 10px 0;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }
    
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
    
    /* ===== NEW UI ELEMENTS ===== */
    .input-wrapper {
        position: relative;
        width: 100%;
    }
    
    .badge-changed {
        position: absolute;
        right: 12px;
        top: 50%;
        transform: translateY(-50%);
        background: #e67e22;
        color: white;
        font-size: 10px;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: bold;
        pointer-events: none;
    }
    
    .file-upload-row {
        display: flex;
        align-items: center;
        width: 100%;
    }
    
    .file-input {
        display: none;
    }
    
    .file-label {
        background: rgba(255, 255, 255, 0.1);
        border: 1px dashed rgba(255, 255, 255, 0.3);
        padding: 10px 16px;
        border-radius: 12px;
        font-size: 13px;
        color: white;
        cursor: pointer;
        transition: all 0.2s;
        text-align: center;
        flex: 1;
    }
    
    .file-label:hover {
        background: rgba(255, 255, 255, 0.15);
        border-color: #ffb6c1;
    }
</style>
