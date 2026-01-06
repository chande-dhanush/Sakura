/**
 * Sakura V10 SSE Store
 * Handles streaming chat responses and state management
 */
import { writable, derived, get } from 'svelte/store';

const BACKEND_URL = 'http://localhost:8000';

// Stores
export const messages = writable([]);
export const isStreaming = writable(false);
export const mood = writable('neutral');
export const currentTools = writable([]);
export const focusEntity = writable(null);
export const connectionError = writable(null);

// Backend status: 'starting' | 'ready' | 'error'
export const backendStatus = writable('starting');

// Voice status
export const voiceStatus = writable({
    enabled: false,
    wakeWordConfigured: false,
    templateCount: 0,
    requiredTemplates: 3
});

// Derived store for mood-based colors
export const moodColors = derived(mood, ($mood) => {
    const colors = {
        frustrated: { primary: '#ff4444', bg: 'rgba(26, 0, 0, 0.95)', glow: 'rgba(255, 68, 68, 0.3)' },
        urgent: { primary: '#ff8800', bg: 'rgba(26, 15, 0, 0.95)', glow: 'rgba(255, 136, 0, 0.3)' },
        playful: { primary: '#44ff88', bg: 'rgba(0, 26, 10, 0.95)', glow: 'rgba(68, 255, 136, 0.3)' },
        curious: { primary: '#4488ff', bg: 'rgba(0, 10, 26, 0.95)', glow: 'rgba(68, 136, 255, 0.3)' },
        neutral: { primary: '#8888ff', bg: 'rgba(10, 10, 15, 0.97)', glow: 'rgba(136, 136, 255, 0.2)' },
    };
    return colors[$mood] || colors.neutral;
});

/**
 * Send a message and stream the response
 */
export async function sendMessage(query, options = {}) {
    if (!query.trim()) return;

    isStreaming.set(true);
    connectionError.set(null);
    currentTools.set([]);

    // Add user message
    messages.update(m => [...m, { role: 'user', content: query, id: Date.now() }]);

    try {
        const response = await fetch(`${BACKEND_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query,
                tts_enabled: options.tts_enabled || false
            }),
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let assistantContent = '';
        let tools = [];
        let mode = '';
        const assistantId = Date.now() + 1;

        while (reader) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;

                try {
                    const data = JSON.parse(line.slice(6));

                    switch (data.type) {
                        case 'thinking':
                            messages.update(m => [...m, {
                                role: 'assistant',
                                content: '...',
                                tools: [],
                                id: assistantId
                            }]);
                            break;

                        case 'tool_used':
                            tools.push({ tool: data.tool, args: {}, status: 'success' });
                            currentTools.set(tools);
                            messages.update(m => {
                                const idx = m.findIndex(msg => msg.id === assistantId);
                                if (idx >= 0) {
                                    m[idx].tools = [...tools];
                                    return [...m];
                                }
                                return m;
                            });
                            break;

                        case 'token':
                            assistantContent = data.content;
                            messages.update(m => {
                                const idx = m.findIndex(msg => msg.id === assistantId);
                                if (idx >= 0) {
                                    m[idx].content = assistantContent;
                                    m[idx].tools = tools;
                                    return [...m];
                                }
                                return [...m, { role: 'assistant', content: assistantContent, tools, id: assistantId }];
                            });
                            break;

                        case 'done':
                            mode = data.mode || '';
                            messages.update(m => {
                                const idx = m.findIndex(msg => msg.id === assistantId);
                                if (idx >= 0) {
                                    m[idx].mode = mode;
                                    return [...m];
                                }
                                return m;
                            });
                            break;

                        case 'error':
                            // Show user-friendly error, not raw stack traces
                            const friendlyError = formatError(data.message);
                            connectionError.set(friendlyError);
                            break;
                    }
                } catch (e) {
                    // Ignore parse errors
                }
            }
        }

        await refreshState();

    } catch (error) {
        // Friendly error messages instead of raw errors
        const friendlyError = formatError(error.message);

        // Update the thinking message to show error gracefully
        messages.update(m => {
            const lastMsg = m[m.length - 1];
            if (lastMsg && lastMsg.role === 'assistant' && lastMsg.content === '...') {
                lastMsg.content = `⚠️ ${friendlyError}. Please try again.`;
                return [...m];
            }
            return [...m, {
                role: 'assistant',
                content: `⚠️ ${friendlyError}. Please try again.`,
                id: Date.now()
            }];
        });

        connectionError.set(friendlyError);
    } finally {
        isStreaming.set(false);
        currentTools.set([]);
    }
}

/**
 * Format raw errors into user-friendly messages
 */
function formatError(message) {
    if (!message) return 'Something went wrong';

    const msg = message.toLowerCase();

    if (msg.includes('fetch') || msg.includes('network') || msg.includes('failed to fetch')) {
        return 'Cannot connect to Sakura backend. Is it running?';
    }
    if (msg.includes('timeout')) {
        return 'Request timed out. The server is taking too long';
    }
    if (msg.includes('500') || msg.includes('internal server')) {
        return 'Server error. Check the backend logs';
    }
    if (msg.includes('401') || msg.includes('403') || msg.includes('unauthorized')) {
        return 'Authentication required. Please check your credentials';
    }
    if (msg.includes('404')) {
        return 'Resource not found';
    }
    if (msg.includes('rate limit') || msg.includes('429')) {
        return 'Rate limited. Please wait a moment';
    }

    // Truncate long technical errors
    if (message.length > 100) {
        return message.substring(0, 80) + '...';
    }

    return message;
}

/**
 * Stop current generation
 */
export async function stopGeneration() {
    try {
        await fetch(`${BACKEND_URL}/stop`, { method: 'POST' });
    } catch (e) {
        // Ignore
    }
}

/**
 * Refresh World Graph state
 */
export async function refreshState() {
    try {
        const response = await fetch(`${BACKEND_URL}/state`);
        if (response.ok) {
            const state = await response.json();
            mood.set(state.mood || 'neutral');
            focusEntity.set(state.focus_entity);
        }
    } catch (e) {
        // Ignore
    }
}

/**
 * Delete a specific message
 */
export function deleteMessage(id) {
    messages.update(m => m.filter(msg => msg.id !== id));
}

/**
 * Clear all chat history
 */
export async function clearChat() {
    try {
        // Call backend to clear all memory
        const response = await fetch(`${BACKEND_URL}/clear`, {
            method: 'POST'
        });

        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                console.log('[Chat] Backend memory cleared:', data.message);
            } else {
                console.warn('[Chat] Backend clear failed:', data.error);
            }
        }
    } catch (e) {
        console.warn('[Chat] Clear API failed:', e.message);
    }

    // Clear frontend store
    messages.set([]);
    connectionError.set(null);
}

/**
 * Load chat history from backend
 */
export async function loadHistory() {
    // console.log('[Chat] Loading history from backend...');
    try {
        const response = await fetch(`${BACKEND_URL}/history`);
        // console.log('[Chat] History response status:', response.status);

        if (response.ok) {
            const data = await response.json();
            // console.log('[Chat] History data:', data);

            if (data.messages && data.messages.length > 0) {
                // Convert backend format to UI format
                const uiMessages = data.messages.map((msg, i) => ({
                    id: Date.now() - (data.messages.length - i) * 1000,
                    role: msg.role === 'human' ? 'user' : msg.role,
                    content: msg.content,
                    tools: [],
                    mode: ''
                }));

                // Smart Update: Only set if changed to prevent flicker
                const current = get(messages);
                if (JSON.stringify(current.map(m => m.content)) !== JSON.stringify(uiMessages.map(m => m.content))) {
                    messages.set(uiMessages);
                    console.log('[Chat] Synced', uiMessages.length, 'messages');
                }
            } else {
                if (get(messages).length > 0) {
                    // messages.set([]); // Optional: clear if backend is empty?
                }
                // console.log('[Chat] No messages in history');
            }
        } else {
            console.warn('[Chat] History endpoint returned', response.status);
        }
    } catch (e) {
        console.warn('[Chat] History load failed:', e.message);
    }
}

/**
 * Start polling for history updates (Voice/External fix)
 */
export function startPolling(intervalMs = 2000) {
    console.log(`[Chat] Starting history polling (${intervalMs}ms)`);
    // Initial load
    loadHistory();
    // Poll
    setInterval(() => {
        // Only poll if NOT streaming (to avoid conflict)
        if (!get(isStreaming)) {
            loadHistory();
        }
    }, intervalMs);
}

/**
 * Check if backend is ready (poll until ready)
 * @returns {Promise<boolean>}
 */
export async function checkBackendReady() {
    const maxAttempts = 60; // 60 seconds max wait

    for (let i = 0; i < maxAttempts; i++) {
        try {
            const response = await fetch(`${BACKEND_URL}/health/ready`);
            if (response.ok) {
                const data = await response.json();

                // V10: Check for Setup Mode (Missing Keys)
                if (data.status === "setup_required") {
                    backendStatus.set('setup_required');
                    console.log('[Chat] Backend requires setup.');
                    return true;
                }

                if (data.ready) {
                    backendStatus.set('ready');
                    console.log('[Chat] Backend is ready!');
                    return true;
                }
            }
        } catch (e) {
            // Server not yet responding
        }

        // Wait 1 second before retry
        await new Promise(r => setTimeout(r, 1000));
    }

    backendStatus.set('error');
    connectionError.set('Backend failed to start');
    return false;
}

/**
 * Check voice status from backend
 */
export async function checkVoiceStatus() {
    try {
        const response = await fetch(`${BACKEND_URL}/voice/status`);
        if (response.ok) {
            const data = await response.json();
            voiceStatus.set({
                enabled: data.enabled ?? false,
                wakeWordConfigured: data.wake_word_configured ?? false,
                templateCount: data.template_count ?? 0,
                requiredTemplates: data.required_templates ?? 3
            });
        }
    } catch (e) {
        console.warn('[Chat] Voice status check failed');
    }
}
