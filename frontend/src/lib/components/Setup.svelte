<script>
    import { fade, fly } from 'svelte/transition';
    import { cubicOut } from 'svelte/easing';
    import { onMount } from 'svelte';
    import { backendStatus } from '$lib/stores/chat.js';
    
    // BACKEND_URL logic
    const BACKEND_URL = "http://localhost:3210"; 
    
    // Configuration State (V18.3 Unified)
    let config = {
        GROQ_API_KEY: "",
        TAVILY_API_KEY: "",
        OPENROUTER_API_KEY: "",
        OPENAI_API_KEY: "",
        GOOGLE_API_KEY: "",
        DEEPSEEK_API_KEY: "",
        DEEPSEEK_BASE_URL: "https://api.deepseek.com",
        SPOTIFY_CLIENT_ID: "",
        SPOTIFY_CLIENT_SECRET: "",
        SPOTIFY_DEVICE_NAME: "",
        MICROPHONE_INDEX: "",
        
        // User Profile
        USER_NAME: "",
        USER_LOCATION: "",
        USER_BIO: "",
        
        // Sakura Personalization (NEW FIX-C)
        SAKURA_NAME: "Sakura",
        RESPONSE_STYLE: "balanced",
        SYSTEM_PROMPT_OVERRIDE: ""
        ,
        ROUTER_PROVIDER: "auto",
        PLANNER_PROVIDER: "auto",
        RESPONDER_PROVIDER: "auto",
        VERIFIER_PROVIDER: "auto",
        ROUTER_MODEL: "llama-3.1-8b-instant",
        PLANNER_MODEL: "",
        RESPONDER_MODEL: "openai/gpt-oss-20b",
        VERIFIER_MODEL: "llama-3.1-8b-instant"
    };

    // UI Props
    export let isUpdateMode = false;
    export let onClose = () => {};

    // Internal State
    let originalConfig = {};
    let dirtyFields = new Set();
    
    let isSubmitting = false;
    let isLoading = false;
    let error = "";
    let success = "";
    let showAdvanced = false;
    
    // Tab State
    let currentTab = 'general';
    
    // V19: Provider gating
    $: isProviderDisabled = (provider) => {
        if (!provider || provider === 'auto') return false;
        if (provider === 'groq' && !config.GROQ_API_KEY) return true;
        if (provider === 'google' && !config.GOOGLE_API_KEY) return true;
        if (provider === 'openai' && !config.OPENAI_API_KEY) return true;
        if (provider === 'openrouter' && !config.OPENROUTER_API_KEY) return true;
        if (provider === 'deepseek' && !config.DEEPSEEK_API_KEY) return true;
        return false;
    };

    $: deepseekWarning = config.PLANNER_PROVIDER === 'deepseek' && !config.PLANNER_MODEL;
    $: providerKeyWarning = (stage) => {
        const p = config[`${stage}_PROVIDER`];
        return p !== 'auto' && isProviderDisabled(p);
    };
    const tabs = [
        { id: 'general', label: 'General', icon: '⚙️' },
        { id: 'personalization', label: 'Personalization', icon: '🌸' },
        { id: 'tools', label: 'Tools', icon: '🔧' },
        { id: 'about', label: 'About', icon: 'ℹ️' }
    ];

    // Reset Confirmation State
    let showResetConfirm = false;

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
                        OPENAI_API_KEY: data.OPENAI_API_KEY || "",
                        GOOGLE_API_KEY: data.GOOGLE_API_KEY || "",
                        DEEPSEEK_API_KEY: data.DEEPSEEK_API_KEY || "",
                        DEEPSEEK_BASE_URL: data.DEEPSEEK_BASE_URL || "https://api.deepseek.com",
                        SPOTIFY_CLIENT_ID: data.SPOTIFY_CLIENT_ID || "",
                        SPOTIFY_CLIENT_SECRET: "", 
                        SPOTIFY_DEVICE_NAME: data.SPOTIFY_DEVICE_NAME || "",
                        MICROPHONE_INDEX: "",
                        
                        USER_NAME: data.USER_NAME || "",
                        USER_LOCATION: data.USER_LOCATION || "",
                        USER_BIO: data.USER_BIO || "",
                        
                        // FIX-C: New Personalization Fields
                        SAKURA_NAME: data.SAKURA_NAME || "Sakura",
                        RESPONSE_STYLE: data.RESPONSE_STYLE || "balanced",
                        SYSTEM_PROMPT_OVERRIDE: data.SYSTEM_PROMPT_OVERRIDE || "",
                        ROUTER_PROVIDER: data.ROUTER_PROVIDER || "auto",
                        PLANNER_PROVIDER: data.PLANNER_PROVIDER || "auto",
                        RESPONDER_PROVIDER: data.RESPONDER_PROVIDER || "auto",
                        VERIFIER_PROVIDER: data.VERIFIER_PROVIDER || "auto",
                        ROUTER_MODEL: data.ROUTER_MODEL || "llama-3.1-8b-instant",
                        PLANNER_MODEL: data.PLANNER_MODEL || "",
                        RESPONDER_MODEL: data.RESPONDER_MODEL || "openai/gpt-oss-20b",
                        VERIFIER_MODEL: data.VERIFIER_MODEL || "llama-3.1-8b-instant"
                    };
                    
                    // Clone for comparison
                    originalConfig = JSON.parse(JSON.stringify(config));
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
        
        if (JSON.stringify(value) !== JSON.stringify(originalConfig[field])) {
            dirtyFields.add(field);
        } else {
            dirtyFields.delete(field);
        }
        dirtyFields = dirtyFields; 
    }

    // Save Changes (PATCH)
    async function handleSubmit() {
        if (dirtyFields.size === 0) return;
        
        isSubmitting = true;
        error = "";
        success = "";
        
        try {
            const payload = {};
            dirtyFields.forEach(field => {
                payload[field] = typeof config[field] === 'string' ? config[field].trim() : config[field];
            });

            const res = await fetch(`${BACKEND_URL}/settings`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            
            const data = await res.json();
            
            if (data.success) {
                success = "Saved ✓";
                
                // Reset state to new baseline
                originalConfig = JSON.parse(JSON.stringify(config));
                dirtyFields.clear();
                dirtyFields = dirtyFields;
                
                setTimeout(() => success = "", 2000);
            } else {
                error = data.message || "Update failed.";
            }
        } catch (e) {
            error = "Connection failed: " + e.message;
        } finally {
            isSubmitting = false;
        }
    }

    async function handleReset() {
        config.SYSTEM_PROMPT_OVERRIDE = "";
        config.RESPONSE_STYLE = "balanced";
        config.SAKURA_NAME = "Sakura";
        
        // Mark as dirty
        dirtyFields.add("SYSTEM_PROMPT_OVERRIDE");
        dirtyFields.add("RESPONSE_STYLE");
        dirtyFields.add("SAKURA_NAME");
        dirtyFields = dirtyFields;
        
        showResetConfirm = false;
        handleSubmit(); // Auto-save on reset
    }
</script>

<div class="setup-container" in:fade out:fade>
    <!-- FULL SCREEN REDESIGN (FIX-C1) -->
    <div class="setup-layout" in:fly={{ y: 30, duration: 300, easing: cubicOut }}>
        
        <!-- SIDEBAR (FIX-C2) -->
        <aside class="sidebar">
            <div class="sidebar-header">
                <span class="logo">🌸</span>
                <h3>Sakura Settings</h3>
                <p>System v18.3</p>
            </div>
            
            <nav class="sidebar-nav">
                {#each tabs as tab}
                    <button 
                        class="nav-item" 
                        class:active={currentTab === tab.id}
                        on:click={() => currentTab = tab.id}
                    >
                        <span class="icon">{tab.icon}</span>
                        <span class="label">{tab.label}</span>
                    </button>
                {/each}
            </nav>
            
            <div class="sidebar-footer">
                <button 
                    class="save-btn" 
                    disabled={dirtyFields.size === 0 || isSubmitting}
                    on:click={handleSubmit}
                >
                    {isSubmitting ? "Saving..." : (success || "Save Changes")}
                </button>
                <button class="close-btn" on:click={onClose}>Close Panel</button>
            </div>
        </aside>

        <!-- CONTENT AREA -->
        <main class="content-area">
            {#if isLoading}
                <div class="loader">Loading configuration...</div>
            {:else}
                <div class="tab-content" in:fade={{ duration: 200 }}>
                    
                    <!-- GENERAL TAB -->
                    {#if currentTab === 'general'}
                        <section>
                            <h2>General Configuration</h2>
                            <p class="section-desc">Basic profile and identity settings.</p>

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
                                <textarea id="user-bio" value={config.USER_BIO} on:input={(e) => handleInput('USER_BIO', e.target.value)} placeholder="Tell Sakura about yourself..."></textarea>
                            </div>
                        </section>

                    <!-- PERSONALIZATION TAB (NEW FIX-C3) -->
                    {:else if currentTab === 'personalization'}
                        <section>
                            <h2>Personalization</h2>
                            <p class="section-desc">Customize how Sakura behaves and responds.</p>

                            <div class="form-group">
                                <label for="sakura-name">Sakura's Name</label>
                                <input id="sakura-name" type="text" value={config.SAKURA_NAME} on:input={(e) => handleInput('SAKURA_NAME', e.target.value)} placeholder="Sakura" />
                                <small>The name Sakura calls herself.</small>
                            </div>

                            <div class="form-group">
                                <label>Response Style (Auto-Constraint)</label>
                                <div class="style-selector">
                                    {#each ['concise', 'balanced', 'detailed'] as style}
                                        <label class="style-option" class:selected={config.RESPONSE_STYLE === style}>
                                            <input 
                                                type="radio" 
                                                name="style" 
                                                value={style} 
                                                checked={config.RESPONSE_STYLE === style}
                                                on:change={() => handleInput('RESPONSE_STYLE', style)}
                                            />
                                            {style.charAt(0).toUpperCase() + style.slice(1)}
                                        </label>
                                    {/each}
                                </div>
                            </div>

                            <div class="form-group">
                                <label for="prompt-override">System Prompt Editor</label>
                                <textarea 
                                    id="prompt-override" 
                                    class="code-editor"
                                    value={config.SYSTEM_PROMPT_OVERRIDE} 
                                    on:input={(e) => handleInput('SYSTEM_PROMPT_OVERRIDE', e.target.value)}
                                    placeholder="Add instructions like 'Respond like a pirate' or 'Use lots of emojis'..."
                                    rows="10"
                                ></textarea>
                                <small>This overrides Sakura's base personality instructions. Keep it descriptive.</small>
                            </div>

                            <div class="danger-zone">
                                {#if showResetConfirm}
                                    <div class="confirm-box" in:fly={{ y: 5 }}>
                                        <span>Reset custom personality?</span>
                                        <button class="confirm-btn" on:click={handleReset}>Yes, Reset</button>
                                        <button class="cancel-link" on:click={() => showResetConfirm = false}>Cancel</button>
                                    </div>
                                {:else}
                                    <button class="reset-btn" on:click={() => showResetConfirm = true}>
                                        🗑️ Reset to Defaults
                                    </button>
                                {/if}
                            </div>
                        </section>

                    <!-- TOOLS TAB -->
                    {:else if currentTab === 'tools'}
                        <section>
                            <h2>Tools & Integration</h2>
                            <p class="section-desc">Manage API keys and external service access.</p>

                            <div class="form-grid">
                                <div class="form-group">
                                    <label for="groq">Groq API Key</label>
                                    <input id="groq" type="password" value={config.GROQ_API_KEY} on:input={(e) => handleInput('GROQ_API_KEY', e.target.value)} placeholder="gsk_••••" />
                                </div>
                                <div class="form-group">
                                    <label for="tavily">Tavily Search Key</label>
                                    <input id="tavily" type="password" value={config.TAVILY_API_KEY} on:input={(e) => handleInput('TAVILY_API_KEY', e.target.value)} placeholder="tvly-••••" />
                                </div>
                                <div class="form-group">
                                    <label for="google">Google API (Gemini)</label>
                                    <input id="google" type="password" value={config.GOOGLE_API_KEY} on:input={(e) => handleInput('GOOGLE_API_KEY', e.target.value)} placeholder="AIza••••" />
                                </div>
                                <div class="form-group">
                                    <label for="openrouter">OpenRouter Key</label>
                                    <input id="openrouter" type="password" value={config.OPENROUTER_API_KEY} on:input={(e) => handleInput('OPENROUTER_API_KEY', e.target.value)} placeholder="sk-or-••••" />
                                </div>
                                <div class="form-group">
                                    <label for="openai">OpenAI Key</label>
                                    <input id="openai" type="password" value={config.OPENAI_API_KEY} on:input={(e) => handleInput('OPENAI_API_KEY', e.target.value)} placeholder="sk-••••" />
                                </div>
                                <div class="form-group">
                                    <label for="deepseek">DeepSeek API Key</label>
                                    <input id="deepseek" type="password" value={config.DEEPSEEK_API_KEY} on:input={(e) => handleInput('DEEPSEEK_API_KEY', e.target.value)} placeholder="sk-••••" />
                                </div>
                                <div class="form-group">
                                    <label for="deepseek-base-url">DeepSeek Base URL</label>
                                    <input id="deepseek-base-url" type="text" value={config.DEEPSEEK_BASE_URL} on:input={(e) => handleInput('DEEPSEEK_BASE_URL', e.target.value)} placeholder="https://api.deepseek.com" />
                                </div>
                            </div>
                            
                            <div class="tool-section">
                                <h3>Spotify Device</h3>
                                <div class="form-group">
                                    <input type="text" value={config.SPOTIFY_DEVICE_NAME} on:input={(e) => handleInput('SPOTIFY_DEVICE_NAME', e.target.value)} placeholder="e.g. My PC" />
                                </div>
                            </div>
                            <div class="tool-section">
                                <h3>Model Stage Configuration</h3>
                                <div class="form-grid">
                                    <div class="form-group">
                                        <label>Router Provider</label>
                                        <select value={config.ROUTER_PROVIDER} on:change={(e) => handleInput('ROUTER_PROVIDER', e.target.value)} class:warning={providerKeyWarning('ROUTER')}>
                                            <option value="auto">Auto (Smart)</option>
                                            <option value="groq" disabled={isProviderDisabled('groq')}>Groq {!config.GROQ_API_KEY ? '(No Key)' : ''}</option>
                                            <option value="google" disabled={isProviderDisabled('google')}>Google Gemini {!config.GOOGLE_API_KEY ? '(No Key)' : ''}</option>
                                            <option value="openai" disabled={isProviderDisabled('openai')}>OpenAI {!config.OPENAI_API_KEY ? '(No Key)' : ''}</option>
                                            <option value="openrouter" disabled={isProviderDisabled('openrouter')}>OpenRouter {!config.OPENROUTER_API_KEY ? '(No Key)' : ''}</option>
                                            <option value="deepseek" disabled={isProviderDisabled('deepseek')}>DeepSeek {!config.DEEPSEEK_API_KEY ? '(No Key)' : ''}</option>
                                        </select>
                                        {#if providerKeyWarning('ROUTER')}
                                            <small class="error-text">API key missing for selected provider!</small>
                                        {/if}
                                    </div>
                                    <div class="form-group">
                                        <label>Router Model</label>
                                        <input type="text" value={config.ROUTER_MODEL} on:input={(e) => handleInput('ROUTER_MODEL', e.target.value)} placeholder="e.g. llama-3.1-8b-instant" />
                                    </div>
                                    <div class="form-group">
                                        <label>Planner Provider</label>
                                        <select value={config.PLANNER_PROVIDER} on:change={(e) => handleInput('PLANNER_PROVIDER', e.target.value)} class:warning={providerKeyWarning('PLANNER')}>
                                            <option value="auto">Auto (Smart)</option>
                                            <option value="deepseek" disabled={isProviderDisabled('deepseek')}>DeepSeek (Recommended) {!config.DEEPSEEK_API_KEY ? '(No Key)' : ''}</option>
                                            <option value="openai" disabled={isProviderDisabled('openai')}>OpenAI {!config.OPENAI_API_KEY ? '(No Key)' : ''}</option>
                                            <option value="google" disabled={isProviderDisabled('google')}>Google Gemini {!config.GOOGLE_API_KEY ? '(No Key)' : ''}</option>
                                            <option value="groq" disabled={isProviderDisabled('groq')}>Groq {!config.GROQ_API_KEY ? '(No Key)' : ''}</option>
                                            <option value="openrouter" disabled={isProviderDisabled('openrouter')}>OpenRouter {!config.OPENROUTER_API_KEY ? '(No Key)' : ''}</option>
                                        </select>
                                        {#if providerKeyWarning('PLANNER')}
                                            <small class="error-text">API key missing for selected provider!</small>
                                        {/if}
                                    </div>
                                    <div class="form-group">
                                        <label>Planner Model</label>
                                        <input type="text" value={config.PLANNER_MODEL} on:input={(e) => handleInput('PLANNER_MODEL', e.target.value)} placeholder="Required for DeepSeek (e.g. deepseek-v4-flash)" class:error={deepseekWarning} />
                                        {#if deepseekWarning}
                                            <small class="error-text">DeepSeek requires an explicit Model ID!</small>
                                        {:else}
                                            <small class="hint">DeepSeek V4 Flash is recommended for PLAN. Ensure exact model ID.</small>
                                        {/if}
                                    </div>
                                    <div class="form-group">
                                        <label>Responder Provider</label>
                                        <select value={config.RESPONDER_PROVIDER} on:change={(e) => handleInput('RESPONDER_PROVIDER', e.target.value)} class:warning={providerKeyWarning('RESPONDER')}>
                                            <option value="auto">Auto (Smart)</option>
                                            <option value="openai" disabled={isProviderDisabled('openai')}>OpenAI {!config.OPENAI_API_KEY ? '(No Key)' : ''}</option>
                                            <option value="google" disabled={isProviderDisabled('google')}>Google Gemini {!config.GOOGLE_API_KEY ? '(No Key)' : ''}</option>
                                            <option value="groq" disabled={isProviderDisabled('groq')}>Groq {!config.GROQ_API_KEY ? '(No Key)' : ''}</option>
                                            <option value="deepseek" disabled={isProviderDisabled('deepseek')}>DeepSeek {!config.DEEPSEEK_API_KEY ? '(No Key)' : ''}</option>
                                            <option value="openrouter" disabled={isProviderDisabled('openrouter')}>OpenRouter {!config.OPENROUTER_API_KEY ? '(No Key)' : ''}</option>
                                        </select>
                                        {#if providerKeyWarning('RESPONDER')}
                                            <small class="error-text">API key missing for selected provider!</small>
                                        {/if}
                                    </div>
                                    <div class="form-group">
                                        <label>Responder Model</label>
                                        <input type="text" value={config.RESPONDER_MODEL} on:input={(e) => handleInput('RESPONDER_MODEL', e.target.value)} />
                                    </div>
                                    <div class="form-group">
                                        <label>Verifier Provider</label>
                                        <select value={config.VERIFIER_PROVIDER} on:change={(e) => handleInput('VERIFIER_PROVIDER', e.target.value)}>
                                            <option value="auto">Auto (Smart)</option>
                                            <option value="groq">Groq</option>
                                            <option value="google">Google Gemini</option>
                                            <option value="openai">OpenAI</option>
                                            <option value="deepseek">DeepSeek</option>
                                        </select>
                                    </div>
                                    <div class="form-group">
                                        <label>Verifier Model</label>
                                        <input type="text" value={config.VERIFIER_MODEL} on:input={(e) => handleInput('VERIFIER_MODEL', e.target.value)} />
                                    </div>
                                </div>
                            </div>
                        </section>

                    <!-- ABOUT TAB -->
                    {:else if currentTab === 'about'}
                        <section class="about-section">
                            <div class="about-header">
                                <span class="big-logo">🌸</span>
                                <h2>Sakura Assistant</h2>
                                <p>Version 18.3.0 (Flight 2026.03)</p>
                            </div>
                            <div class="stats">
                                <div class="stat-card">
                                    <label>Memory Mode</label>
                                    <span>FAISS (Persistent)</span>
                                </div>
                                <div class="stat-card">
                                    <label>Vision Engine</label>
                                    <span>Active (MSS + LLaVA)</span>
                                </div>
                                <div class="stat-card">
                                    <label>Architecture</label>
                                    <span>V17 Iterative</span>
                                </div>
                            </div>
                            <p class="about-text">
                                Sakura is a state-of-the-art agentic coding and personal assistant.
                                This build includes FIX-A (Routing) and FIX-B (Vision Stability).
                            </p>
                        </section>
                    {/if}
                </div>
            {/if}
            
            {#if error}
                <div class="error-toast" in:fly={{ y: 20 }}>{error}</div>
            {/if}
        </main>
    </div>
</div>

<style>
    .setup-container {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(8px);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 9999;
        font-family: 'Inter', system-ui, sans-serif;
        color: #e0e0e0;
    }

    .setup-layout {
        display: flex;
        width: 90vw;
        height: 85vh;
        max-width: 1100px;
        background: #121212;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 24px;
        box-shadow: 0 30px 60px rgba(0, 0, 0, 0.8);
        overflow: hidden;
    }

    /* SIDEBAR */
    .sidebar {
        width: 240px;
        background: #1a1a1a;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
        display: flex;
        flex-direction: column;
        padding: 30px 0;
    }

    .sidebar-header {
        padding: 0 25px;
        margin-bottom: 40px;
    }
    .sidebar-header .logo { font-size: 32px; }
    .sidebar-header h3 { margin: 10px 0 2px 0; font-size: 18px; color: #ffb6c1; }
    .sidebar-header p { font-size: 11px; color: #666; margin: 0; }

    .sidebar-nav {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 4px;
        padding: 0 12px;
    }

    .nav-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 16px;
        background: none;
        border: none;
        border-radius: 12px;
        color: #aaa;
        cursor: pointer;
        transition: all 0.2s;
        text-align: left;
    }
    .nav-item:hover { background: rgba(255, 182, 193, 0.05); color: #fff; }
    .nav-item.active { 
        background: rgba(255, 182, 193, 0.1); 
        color: #ffb6c1; 
        font-weight: 600;
    }
    .nav-item .icon { font-size: 18px; }

    .sidebar-footer {
        padding: 20px;
        display: flex;
        flex-direction: column;
        gap: 10px;
    }

    .save-btn {
        width: 100%;
        padding: 12px;
        background: #ffb6c1;
        color: #000;
        border: none;
        border-radius: 12px;
        font-weight: 600;
        cursor: pointer;
        transition: transform 0.2s;
    }
    .save-btn:disabled { background: #333; color: #666; cursor: not-allowed; }
    .save-btn:not(:disabled):hover { transform: translateY(-2px); }

    .close-btn {
        background: none;
        border: 1px solid #333;
        color: #888;
        padding: 10px;
        border-radius: 10px;
        cursor: pointer;
        font-size: 13px;
    }
    .close-btn:hover { background: #222; color: #fff; }

    /* CONTENT AREA */
    .content-area {
        flex: 1;
        background: #121212;
        padding: 50px;
        overflow-y: auto;
    }

    h2 { font-size: 24px; margin-bottom: 8px; }
    .section-desc { color: #666; margin-bottom: 40px; font-size: 14px; }

    .form-group {
        margin-bottom: 25px;
        display: flex;
        flex-direction: column;
        gap: 8px;
    }
    label { font-size: 13px; font-weight: 600; color: #888; }
    input, textarea {
        background: #1a1a1a;
        border: 1px solid #333;
        padding: 12px 16px;
        border-radius: 12px;
        color: #fff;
        outline: none;
        transition: border 0.2s;
    }
    input:focus, textarea:focus { border-color: #ffb6c1; }
    textarea { height: 80px; resize: vertical; }

    .code-editor {
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        background: #000 !important;
        line-height: 1.5;
        font-size: 13px;
        border: 1px solid #222;
    }

    .style-selector {
        display: flex;
        gap: 10px;
        margin-top: 5px;
    }
    .style-option {
        flex: 1;
        padding: 15px;
        background: #1a1a1a;
        border: 1px solid #333;
        border-radius: 12px;
        text-align: center;
        cursor: pointer;
        transition: all 0.2s;
        font-size: 13px;
    }
    .style-option.selected {
        background: rgba(255, 182, 193, 0.1);
        border-color: #ffb6c1;
        color: #ffb6c1;
    }
    .style-option input { display: none; }

    select {
        background: #1a1a1a;
        border: 1px solid #333;
        padding: 12px 16px;
        border-radius: 12px;
        color: #fff;
        outline: none;
        cursor: pointer;
        transition: border 0.2s;
        appearance: none;
        background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
        background-repeat: no-repeat;
        background-position: right 1rem center;
        background-size: 1em;
    }
    select:focus { border-color: #ffb6c1; }

    .hint { font-size: 11px; color: #666; margin-top: -4px; }
    .warning { border-color: #f1c40f !important; }
    .error { border-color: #ff6b6b !important; }
    .error-text { color: #ff6b6b; font-size: 11px; margin-top: -4px; }

    .danger-zone { margin-top: 50px; padding-top: 20px; border-top: 1px solid #222; }
    .reset-btn { background: none; border: none; color: #666; font-size: 13px; cursor: pointer; }
    .reset-btn:hover { color: #ff6b6b; }

    .confirm-box { 
        background: rgba(255, 107, 107, 0.1); 
        padding: 15px; 
        border-radius: 12px; 
        border: 1px solid #ff6b6b;
        display: flex;
        align-items: center;
        gap: 15px;
        font-size: 13px;
    }
    .confirm-btn { background: #ff6b6b; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; }
    .cancel-link { color: #888; background: none; border: none; cursor: pointer; }

    .stat-card {
        background: #1a1a1a;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #222;
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 5px;
    }
    .stat-card label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; }
    .about-section { text-align: center; }
    .big-logo { font-size: 64px; margin-bottom: 20px; display: block; }

    .error-toast {
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: #ff6b6b;
        color: #fff;
        padding: 12px 24px;
        border-radius: 12px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    }
</style>
