<!-- Sakura V10 Omnibox Component -->
<script>
    import { sendMessage, isStreaming, stopGeneration, moodColors } from '$lib/stores/chat.js';
    
    export let isQuickSearch = false;

    let query = '';
    let textarea;
    let fileInput;
    let attachedFile = null;
    let isUploading = false;
    let uploadError = '';
    
    const BACKEND_URL = "http://localhost:8000";
    
    async function handleSubmit() {
        if (!query.trim() || $isStreaming) return;
        const q = query;
        query = '';
        attachedFile = null;
        if (textarea) textarea.style.height = 'auto';
        await sendMessage(q, { tts_enabled: isQuickSearch });
    }
    
    function handleKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
        if (e.key === 'Escape' && $isStreaming) {
            stopGeneration();
        }
    }
    
    function autoGrow() {
        if (!textarea) return;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
    }
    
    async function handleFileSelect(e) {
        const file = e.target.files?.[0];
        if (!file) return;
        
        attachedFile = file;
        uploadError = '';
        isUploading = true;
        
        try {
            const formData = new FormData();
            formData.append('file', file);
            
            const res = await fetch(`${BACKEND_URL}/upload`, {
                method: 'POST',
                body: formData
            });
            
            const data = await res.json();
            
            if (data.success) {
                console.log('✅ File uploaded:', data);
                // File stays attached as visual confirmation
            } else {
                uploadError = data.message || 'Upload failed';
                attachedFile = null;
            }
        } catch (e) {
            uploadError = 'Upload failed: ' + e.message;
            attachedFile = null;
        } finally {
            isUploading = false;
        }
    }
    
    function removeFile() {
        attachedFile = null;
        uploadError = '';
        if (fileInput) fileInput.value = '';
    }

    async function triggerVoice() {
        try {
            await fetch(`${BACKEND_URL}/voice/trigger`, { method: 'POST' });
        } catch (e) {
            console.error("Voice trigger failed", e);
        }
    }
</script>

<form class="omnibox" class:quick-search={isQuickSearch} on:submit|preventDefault={handleSubmit} style="--glow: {$moodColors.glow}; --primary: {$moodColors.primary}">
    <!-- Upload Error -->
    {#if uploadError}
        <div class="upload-error">
            ⚠️ {uploadError}
            <button type="button" on:click={() => uploadError = ''}>×</button>
        </div>
    {/if}
    
    <!-- Attached File Preview -->
    {#if attachedFile}
        <div class="file-preview" class:uploading={isUploading}>
            <span class="file-icon">{isUploading ? '⏳' : '✅'}</span>
            <span class="file-name">{attachedFile.name}</span>
            <button type="button" class="file-remove" on:click={removeFile} disabled={isUploading}>×</button>
        </div>
    {/if}
    
    <div class="input-row">
        <!-- File Upload Button -->
        <input 
            type="file" 
            bind:this={fileInput}
            on:change={handleFileSelect}
            accept=".pdf,.txt,.md,.doc,.docx,.png,.jpg,.jpeg"
            style="display: none"
        />
        <button 
            type="button" 
            class="attach-btn" 
            class:uploading={isUploading}
            on:click={() => fileInput?.click()} 
            title="Attach file for context"
            disabled={isUploading}
        >
            {#if isUploading}
                <span class="spinner">⏳</span>
            {:else}
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" 
                        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            {/if}
        </button>
        
        <!-- Text Input -->
        <div class="input-wrapper">
            <textarea
                bind:this={textarea}
                bind:value={query}
                on:input={autoGrow}
                on:keydown={handleKeydown}
                placeholder="Ask Sakura anything..."
                rows="1"
                disabled={$isStreaming}
            ></textarea>
        </div>
        
        <!-- Actions: Mic, Send, Stop -->
        <div class="actions">
            <!-- Mic Button -->
             <button type="button" class="mic-btn" on:click={triggerVoice} title="Voice Input">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M12 19v4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M8 23h8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </button>

            {#if $isStreaming}
                <button type="button" class="stop-btn" on:click={stopGeneration} title="Stop">
                    ⏹
                </button>
            {:else}
                <button type="submit" class="send-btn" disabled={!query.trim()} title="Send">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                        <path d="M22 2L11 13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                        <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
                    </svg>
                </button>
            {/if}
        </div>
    </div>
</form>

<style>
    .omnibox {
        flex: 1; /* Fix for capping */
        width: 100%; /* Fix for capping */
        display: flex;
        flex-direction: column;
        gap: 8px;
        padding: 12px 14px;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        transition: all 0.2s ease;
    }
    
    .omnibox:focus-within {
        border-color: var(--primary);
        box-shadow: 0 0 20px var(--glow);
        background: rgba(255, 255, 255, 0.05);
    }
    
    .omnibox.quick-search {
        background: transparent;
        border: none;
        padding: 0;
    }
    
    .omnibox.quick-search textarea {
        font-size: 16px; /* V10: Reduced from 24px for cleaner look */
        font-weight: 500;
        line-height: 1.4;
    }
    
    .omnibox.quick-search .input-wrapper {
        align-items: center;
    }
    
    .upload-error {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 6px 10px;
        background: rgba(255, 68, 68, 0.15);
        border: 1px solid rgba(255, 68, 68, 0.3);
        border-radius: 8px;
        font-size: 12px;
        color: #ff8888;
    }
    
    .upload-error button {
        background: none;
        border: none;
        color: #ff8888;
        cursor: pointer;
        font-size: 14px;
        padding: 0 4px;
    }
    
    .file-preview {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 10px;
        background: rgba(46, 204, 113, 0.1);
        border: 1px solid rgba(46, 204, 113, 0.3);
        border-radius: 8px;
        font-size: 12px;
    }
    
    .file-preview.uploading {
        background: rgba(255, 170, 0, 0.1);
        border-color: rgba(255, 170, 0, 0.3);
    }
    
    .file-icon {
        font-size: 14px;
    }
    
    .file-name {
        flex: 1;
        color: rgba(255, 255, 255, 0.7);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    
    .file-remove {
        background: transparent;
        border: none;
        color: rgba(255, 255, 255, 0.5);
        cursor: pointer;
        font-size: 16px;
        padding: 0 4px;
    }
    
    .input-row {
        display: flex;
        align-items: flex-end;
        gap: 10px;
    }
    
    .attach-btn {
        background: transparent;
        border: none;
        color: rgba(255, 255, 255, 0.4);
        cursor: pointer;
        padding: 8px;
        border-radius: 8px;
        transition: all 0.2s;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    .attach-btn:hover:not(:disabled) {
        background: rgba(255, 255, 255, 0.1);
        color: var(--primary);
    }
    
    .attach-btn:disabled, .attach-btn.disabled {
        opacity: 0.3;
        cursor: not-allowed;
    }
    
    .input-wrapper {
        flex: 1;
        display: flex;
    }
    
    textarea {
        flex: 1;
        background: transparent;
        border: none;
        color: #fff;
        font-size: 15px;
        font-family: inherit;
        resize: none;
        outline: none;
        line-height: 1.5;
        max-height: 150px;
    }
    
    textarea::placeholder {
        color: rgba(255, 255, 255, 0.35);
    }
    
    textarea:disabled {
        opacity: 0.5;
    }
    
    .actions {
        display: flex;
        gap: 8px;
        align-items: center;
    }
    
    .send-btn, .stop-btn {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        border: none;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.2s;
    }
    
    .send-btn {
        background: var(--primary);
        color: #000;
    }
    
    .send-btn:hover:not(:disabled) {
        transform: scale(1.05);
        box-shadow: 0 0 15px var(--glow);
    }
    
    .send-btn:disabled {
        opacity: 0.3;
        cursor: not-allowed;
    }
    
    .stop-btn {
        background: rgba(255, 68, 68, 0.2);
        color: #ff6666;
        font-size: 14px;
    }
    
    .stop-btn:hover {
        background: rgba(255, 68, 68, 0.3);
    }

    .mic-btn {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        border: none;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.2s;
        background: transparent;
        color: rgba(255, 255, 255, 0.6);
    }
    
    .mic-btn:hover {
        background: rgba(255, 255, 255, 0.1);
        color: #fff;
    }
</style>
