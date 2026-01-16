<script>
    import { onMount, onDestroy } from 'svelte';
    import { slide } from 'svelte/transition';
    
    const BACKEND_URL = "http://localhost:3210";
    
    let logs = { traces: [], stats: { total_queries: 0, success_rate: 100, avg_latency_s: 0 } };
    let loading = true;
    let error = null;
    let expandedTraces = new Set();
    let expandedPhases = new Set();
    let copiedError = false;
    let autoRefresh = true;
    let refreshInterval;
    
    onMount(() => {
        fetchLogs();
        refreshInterval = setInterval(() => {
            if (autoRefresh) fetchLogs();
        }, 5000);
    });
    
    onDestroy(() => {
        if (refreshInterval) clearInterval(refreshInterval);
    });
    
    async function fetchLogs() {
        try {
            const res = await fetch(`${BACKEND_URL}/api/logs?limit=100`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            logs = await res.json();
            error = null;
        } catch (e) {
            error = e.message;
        } finally {
            loading = false;
        }
    }
    
    function toggleTrace(id) {
        if (expandedTraces.has(id)) expandedTraces.delete(id);
        else expandedTraces.add(id);
        expandedTraces = expandedTraces;
    }
    
    function togglePhase(traceId, phase) {
        const key = `${traceId}-${phase}`;
        if (expandedPhases.has(key)) expandedPhases.delete(key);
        else expandedPhases.add(key);
        expandedPhases = expandedPhases;
    }
    
    function copyError(errorText) {
        navigator.clipboard.writeText(errorText);
        copiedError = true;
        setTimeout(() => copiedError = false, 2000);
    }
    
    $: groupedTraces = logs.traces.reduce((acc, trace) => {
        const date = trace.date || 'Unknown';
        if (!acc[date]) acc[date] = [];
        acc[date].push(trace);
        return acc;
    }, {});
    
    $: dates = Object.keys(groupedTraces).sort().reverse();
    
    function getSparkline(trace) {
        const total = trace.total_ms || 1;
        const phases = trace.phases || {};
        const routerMs = phases.Router?.reduce((sum, e) => sum + ((e.duration_s || 0) * 1000), 0) || 0;
        const executorMs = phases.Executor?.reduce((sum, e) => sum + ((e.duration_s || 0) * 1000), 0) || 0;
        const responderMs = phases.Responder?.reduce((sum, e) => sum + ((e.duration_s || 0) * 1000), 0) || 0;
        return {
            router: Math.min((routerMs / total) * 100, 100),
            executor: Math.min((executorMs / total) * 100, 100),
            responder: Math.min((responderMs / total) * 100, 100)
        };
    }
</script>

<svelte:head>
    <title>Sakura Sight</title>
</svelte:head>

<div class="dashboard">
    <header class="header">
        <div class="title-section">
            <h1>Sakura Sight</h1>
            <span class="subtitle">Real-time observability dashboard</span>
        </div>
        <div class="controls">
            <label class="auto-refresh">
                <input type="checkbox" bind:checked={autoRefresh} />
                Auto-refresh
            </label>
            <button class="refresh-btn" on:click={fetchLogs} disabled={loading}>
                {loading ? 'Loading...' : 'Refresh'}
            </button>
        </div>
    </header>
    
    <div class="stats-grid">
        <div class="stat-card"><div class="stat-icon">📊</div><div class="stat-content"><span class="stat-value">{logs.stats.total_queries}</span><span class="stat-label">Total Queries</span></div></div>
        <div class="stat-card"><div class="stat-icon">✅</div><div class="stat-content"><span class="stat-value">{logs.stats.success_rate}%</span><span class="stat-label">Success Rate</span></div></div>
        <div class="stat-card"><div class="stat-icon">⚡</div><div class="stat-content"><span class="stat-value">{logs.stats.avg_latency_s}s</span><span class="stat-label">Avg Latency</span></div></div>
        <div class="stat-card"><div class="stat-icon">📅</div><div class="stat-content"><span class="stat-value">{dates.length}</span><span class="stat-label">Days Tracked</span></div></div>
    </div>
    
    <main class="content">
        {#if error}
            <div class="error-banner">Failed to load logs: {error}</div>
        {:else if loading && logs.traces.length === 0}
            <div class="loading-state"><div class="spinner"></div><p>Loading traces...</p></div>
        {:else if logs.traces.length === 0}
            <div class="empty-state"><span class="empty-icon">📭</span><h3>No logs yet</h3><p>Chat with Sakura to generate traces</p></div>
        {:else}
            {#each dates as date}
                <section class="date-section">
                    <h2 class="date-header">📅 {date} <span class="trace-count">{groupedTraces[date].length} queries</span></h2>
                    <div class="traces-list">
                        {#each groupedTraces[date] as trace}
                            {@const sparkline = getSparkline(trace)}
                            <div class="trace-card" class:error={!trace.success}>
                                <button class="trace-header" on:click={() => toggleTrace(trace.id)}>
                                    <span class="status">{trace.success ? '🟢' : '🔴'}</span>
                                    <span class="time">{trace.time}</span>
                                    <span class="query">{trace.query.slice(0, 60)}{trace.query.length > 60 ? '...' : ''}</span>
                                    <span class="latency">{(trace.total_ms / 1000).toFixed(2)}s</span>
                                    <span class="chevron">{expandedTraces.has(trace.id) ? '▼' : '▶'}</span>
                                </button>
                                <div class="sparkline">
                                    <div class="spark spark-router" style="width: {sparkline.router}%"></div>
                                    <div class="spark spark-executor" style="width: {sparkline.executor}%"></div>
                                    <div class="spark spark-responder" style="width: {sparkline.responder}%"></div>
                                </div>
                                {#if expandedTraces.has(trace.id)}
                                    <div class="trace-body" transition:slide>
                                        <div class="io-grid">
                                            <div class="io-card input"><div class="io-header">🧑 User Input</div><div class="io-content">{trace.query}</div></div>
                                            <div class="io-card output"><div class="io-header">🌸 Response</div><div class="io-content">{trace.response || 'No response captured'}</div></div>
                                        </div>
                                        {#if trace.error}
                                            <div class="error-box"><span class="error-text">⚠️ {trace.error}</span><button class="copy-btn" on:click={() => copyError(trace.error)}>{copiedError ? 'Copied' : 'Copy'}</button></div>
                                        {/if}
                                        <div class="pipeline-metrics">
                                            <h4>Pipeline Performance</h4>
                                            <div class="metrics-grid">
                                                {#each ['Router', 'Executor', 'Responder'] as phase}
                                                    {@const events = trace.phases[phase] || []}
                                                    {@const duration = events.reduce((sum, e) => sum + (e.duration_s || 0), 0)}
                                                    <div class="metric-card {phase.toLowerCase()}">
                                                        <span class="metric-icon">{phase === 'Router' ? '🚥' : phase === 'Executor' ? '⚙️' : '🗣️'}</span>
                                                        <span class="metric-value">{duration.toFixed(2)}s</span>
                                                        <span class="metric-label">{phase}</span>
                                                    </div>
                                                {/each}
                                            </div>
                                        </div>
                                        <div class="phases">
                                            {#each ['Router', 'Executor', 'Responder'] as phase}
                                                {@const events = trace.phases[phase] || []}
                                                {#if events.length > 0}
                                                    {@const phaseKey = `${trace.id}-${phase}`}
                                                    <div class="phase-section">
                                                        <button class="phase-header {phase.toLowerCase()}" on:click={() => togglePhase(trace.id, phase)}>
                                                            <span class="phase-icon">{phase === 'Router' ? '🚥' : phase === 'Executor' ? '⚙️' : '🗣️'}</span>
                                                            <span class="phase-name">{phase}</span>
                                                            <span class="event-count">{events.length} events</span>
                                                            <span class="chevron">{expandedPhases.has(phaseKey) ? '▼' : '▶'}</span>
                                                        </button>
                                                        {#if expandedPhases.has(phaseKey)}
                                                            <div class="phase-events" transition:slide>
                                                                {#each events as event}
                                                                    <div class="event-row" class:error={event.status === 'ERROR'}>
                                                                        <span class="event-time">T+{event.elapsed_s}s</span>
                                                                        <span class="event-content">{event.content}</span>
                                                                    </div>
                                                                    {#if event.metadata}
                                                                        <pre class="metadata">{JSON.stringify(event.metadata, null, 2)}</pre>
                                                                    {/if}
                                                                {/each}
                                                            </div>
                                                        {/if}
                                                    </div>
                                                {/if}
                                            {/each}
                                        </div>
                                    </div>
                                {/if}
                            </div>
                        {/each}
                    </div>
                </section>
            {/each}
        {/if}
    </main>
</div>

<style>
    /* ═══════════════════════════════════════════════════════════════════
       SAKURA SIGHT - BLUE CYBERPUNK THEME
       Electric blue, cyan, teal accents on deep navy/charcoal
       ═══════════════════════════════════════════════════════════════════ */
    
    :global(body) { 
        margin: 0; 
        padding: 0; 
        background: linear-gradient(135deg, #0a0e14 0%, #0d1520 50%, #0a1628 100%); 
        min-height: 100vh; 
    }
    
    .dashboard { 
        min-height: 100vh; 
        color: #e6edf3; 
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        background: linear-gradient(135deg, #0a0e14 0%, #0d1520 50%, #0a1628 100%);
        overflow-y: auto;
        max-height: 100vh;
    }
    
    /* Header */
    .header { 
        display: flex; 
        justify-content: space-between; 
        align-items: center; 
        padding: 24px 48px; 
        border-bottom: 1px solid rgba(56, 139, 253, 0.15); 
        background: rgba(13, 17, 23, 0.8);
        backdrop-filter: blur(10px);
    }
    
    .title-section h1 { 
        margin: 0; 
        font-size: 2rem; 
        font-weight: 700; 
        background: linear-gradient(90deg, #58a6ff, #79c0ff, #56d4dd); 
        -webkit-background-clip: text; 
        -webkit-text-fill-color: transparent;
        text-shadow: 0 0 30px rgba(88, 166, 255, 0.3);
    }
    
    .subtitle { color: #7d8590; font-size: 0.9rem; }
    
    .controls { display: flex; gap: 16px; align-items: center; }
    
    .auto-refresh { display: flex; align-items: center; gap: 8px; color: #7d8590; cursor: pointer; }
    .auto-refresh input { accent-color: #58a6ff; }
    
    .refresh-btn { 
        padding: 10px 20px; 
        background: rgba(56, 139, 253, 0.1); 
        border: 1px solid rgba(56, 139, 253, 0.4); 
        border-radius: 8px; 
        color: #58a6ff; 
        cursor: pointer; 
        font-size: 0.9rem; 
        transition: all 0.2s;
        text-shadow: 0 0 10px rgba(88, 166, 255, 0.3);
    }
    .refresh-btn:hover { 
        background: rgba(56, 139, 253, 0.2); 
        border-color: #58a6ff;
        box-shadow: 0 0 15px rgba(56, 139, 253, 0.3);
    }
    .refresh-btn:disabled { opacity: 0.5; cursor: wait; }
    
    /* Stats Grid */
    .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px; padding: 32px 48px; }
    
    .stat-card { 
        display: flex; 
        align-items: center; 
        gap: 16px; 
        padding: 24px; 
        background: rgba(22, 27, 34, 0.8); 
        border: 1px solid rgba(56, 139, 253, 0.15); 
        border-radius: 16px; 
        transition: all 0.3s;
        backdrop-filter: blur(5px);
    }
    .stat-card:hover { 
        border-color: rgba(56, 139, 253, 0.5); 
        transform: translateY(-2px); 
        box-shadow: 0 8px 30px rgba(56, 139, 253, 0.15);
    }
    
    .stat-icon { font-size: 2rem; }
    .stat-content { display: flex; flex-direction: column; }
    .stat-value { font-size: 2rem; font-weight: 700; color: #79c0ff; }
    .stat-label { font-size: 0.85rem; color: #7d8590; }
    
    /* Content */
    .content { padding: 0 48px 48px; }
    
    /* Date Section */
    .date-section { margin-bottom: 32px; }
    .date-header { 
        display: flex; 
        align-items: center; 
        gap: 12px; 
        font-size: 1.25rem; 
        color: #8b949e; 
        margin: 0 0 16px 0; 
        padding-bottom: 12px; 
        border-bottom: 1px solid rgba(56, 139, 253, 0.15); 
    }
    .trace-count { font-size: 0.85rem; color: #484f58; font-weight: 400; }
    
    /* Traces */
    .traces-list { display: flex; flex-direction: column; gap: 12px; }
    
    .trace-card { 
        background: rgba(22, 27, 34, 0.6); 
        border: 1px solid rgba(56, 139, 253, 0.1); 
        border-radius: 12px; 
        overflow: hidden; 
        transition: all 0.2s; 
    }
    .trace-card:hover { border-color: rgba(56, 139, 253, 0.3); }
    .trace-card.error { border-color: rgba(248, 81, 73, 0.4); }
    
    .trace-header { 
        width: 100%; 
        display: flex; 
        align-items: center; 
        gap: 16px; 
        padding: 16px 20px; 
        background: transparent; 
        border: none; 
        color: inherit; 
        cursor: pointer; 
        text-align: left; 
        font-size: 0.95rem; 
    }
    .trace-header:hover { background: rgba(56, 139, 253, 0.05); }
    .trace-header .status { font-size: 0.9rem; }
    .trace-header .time { color: #484f58; font-family: 'JetBrains Mono', monospace; min-width: 70px; }
    .trace-header .query { flex: 1; color: #c9d1d9; }
    .trace-header .latency { 
        font-family: 'JetBrains Mono', monospace; 
        color: #56d4dd; 
        background: rgba(86, 212, 221, 0.1); 
        padding: 4px 10px; 
        border-radius: 6px;
        border: 1px solid rgba(86, 212, 221, 0.2);
    }
    .trace-header .chevron { color: #484f58; font-size: 0.8rem; }
    
    /* Sparkline - Electric blue phases */
    .sparkline { display: flex; height: 4px; background: rgba(56, 139, 253, 0.1); }
    .spark { height: 100%; }
    .spark-router { background: linear-gradient(90deg, #a371f7, #bc8cff); }
    .spark-executor { background: linear-gradient(90deg, #f78166, #ffa657); }
    .spark-responder { background: linear-gradient(90deg, #3fb950, #56d364); }
    
    /* Trace Body */
    .trace-body { padding: 24px; background: rgba(13, 17, 23, 0.6); border-top: 1px solid rgba(56, 139, 253, 0.1); }
    
    /* I/O Cards */
    .io-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
    .io-card { padding: 16px; border-radius: 10px; }
    .io-card.input { background: rgba(56, 139, 253, 0.08); border: 1px solid rgba(56, 139, 253, 0.2); }
    .io-card.output { background: rgba(86, 212, 221, 0.08); border: 1px solid rgba(86, 212, 221, 0.2); }
    .io-header { font-weight: 600; margin-bottom: 8px; color: #8b949e; }
    .io-content { color: #c9d1d9; line-height: 1.5; }
    
    /* Error */
    .error-box { 
        display: flex; 
        justify-content: space-between; 
        align-items: center; 
        padding: 14px 18px; 
        background: rgba(248, 81, 73, 0.1); 
        border: 1px solid rgba(248, 81, 73, 0.3); 
        border-radius: 10px; 
        margin-bottom: 24px; 
    }
    .error-text { color: #f85149; }
    .copy-btn { 
        padding: 6px 14px; 
        background: rgba(248, 81, 73, 0.2); 
        border: none; 
        border-radius: 6px; 
        color: #f85149; 
        cursor: pointer; 
        font-size: 0.85rem; 
    }
    
    /* Pipeline Metrics */
    .pipeline-metrics { margin-bottom: 24px; }
    .pipeline-metrics h4 { margin: 0 0 16px 0; color: #8b949e; font-weight: 500; }
    .metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    
    .metric-card { 
        display: flex; 
        flex-direction: column; 
        align-items: center; 
        padding: 16px; 
        background: rgba(22, 27, 34, 0.8); 
        border-radius: 10px; 
        border-left: 3px solid; 
    }
    .metric-card.router { border-color: #a371f7; }
    .metric-card.executor { border-color: #f78166; }
    .metric-card.responder { border-color: #3fb950; }
    
    .metric-icon { font-size: 1.5rem; margin-bottom: 8px; }
    .metric-value { font-size: 1.5rem; font-weight: 700; color: #e6edf3; }
    .metric-label { font-size: 0.8rem; color: #7d8590; }
    
    /* Phases */
    .phases { display: flex; flex-direction: column; gap: 10px; }
    .phase-section { border: 1px solid rgba(56, 139, 253, 0.1); border-radius: 10px; overflow: hidden; }
    
    .phase-header { 
        width: 100%; 
        display: flex; 
        align-items: center; 
        gap: 12px; 
        padding: 14px 18px; 
        background: rgba(22, 27, 34, 0.5); 
        border: none; 
        border-left: 3px solid transparent; 
        color: inherit; 
        cursor: pointer; 
        font-size: 0.9rem; 
    }
    .phase-header.router { border-left-color: #a371f7; }
    .phase-header.executor { border-left-color: #f78166; }
    .phase-header.responder { border-left-color: #3fb950; }
    .phase-header:hover { background: rgba(56, 139, 253, 0.05); }
    
    .phase-name { font-weight: 500; }
    .event-count { color: #484f58; font-size: 0.8rem; margin-left: auto; }
    
    .phase-events { padding: 12px 18px; background: rgba(13, 17, 23, 0.5); }
    .event-row { display: flex; gap: 16px; padding: 8px 0; border-bottom: 1px solid rgba(56, 139, 253, 0.05); font-size: 0.85rem; }
    .event-row.error { color: #f85149; }
    .event-time { font-family: 'JetBrains Mono', monospace; color: #484f58; min-width: 70px; }
    .event-content { color: #8b949e; }
    
    .metadata { 
        background: rgba(13, 17, 23, 0.8); 
        padding: 10px 14px; 
        border-radius: 6px; 
        font-size: 0.75rem; 
        color: #7d8590; 
        overflow-x: auto; 
        margin: 6px 0;
        border: 1px solid rgba(56, 139, 253, 0.1);
    }
    
    /* States */
    .loading-state, .empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 80px 0; color: #484f58; }
    .empty-icon { font-size: 4rem; margin-bottom: 16px; }
    .empty-state h3 { margin: 0; color: #8b949e; }
    .empty-state p { margin: 8px 0 0; }
    
    .spinner { 
        width: 40px; 
        height: 40px; 
        border: 3px solid rgba(56, 139, 253, 0.2); 
        border-top-color: #58a6ff; 
        border-radius: 50%; 
        animation: spin 1s linear infinite; 
        margin-bottom: 16px; 
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    
    .error-banner { 
        padding: 16px 24px; 
        background: rgba(248, 81, 73, 0.1); 
        border: 1px solid rgba(248, 81, 73, 0.3); 
        border-radius: 10px; 
        color: #f85149; 
        text-align: center; 
    }
</style>
