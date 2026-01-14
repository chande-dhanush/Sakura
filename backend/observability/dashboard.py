"""
Sakura Sight - Observability Dashboard V2
==========================================
Mission Control for Sakura V10 Brain.

Hierarchy:
  📅 Date → 💬 User Query → ⚡ Phase → 🛠️ Details

Run with: streamlit run dashboard.py
"""
import streamlit as st
import json
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Sakura Sight",
    page_icon="🌸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Path Resolution
SCRIPT_DIR = Path(__file__).parent.absolute()
BACKEND_DIR = SCRIPT_DIR.parent
LOCAL_LOG = BACKEND_DIR / "data" / "flight_recorder.jsonl"

def get_appdata_log():
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "SakuraV10" / "data" / "flight_recorder.jsonl"
    return None

APPDATA_LOG = get_appdata_log()

# ═══════════════════════════════════════════════════════════════════════════════
# STYLES
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
    /* Dark Sakura Theme */
    .stApp {
        background: linear-gradient(135deg, #0e1117 0%, #1a1a2e 100%);
    }
    
    /* Headers */
    h1 { 
        background: linear-gradient(90deg, #ff9a9e, #fad0c4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
    }
    h2, h3 { color: #ffb7b2; }
    
    /* Metrics */
    div[data-testid="stMetricValue"] {
        color: #ffd1dc;
        font-size: 1.8rem;
    }
    div[data-testid="stMetricLabel"] {
        color: #888;
    }
    
    /* Cards */
    .query-card {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,183,178,0.2);
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
        transition: all 0.2s ease;
    }
    .query-card:hover {
        border-color: rgba(255,183,178,0.5);
        box-shadow: 0 4px 20px rgba(255,183,178,0.1);
    }
    
    /* Phase Badges */
    .phase-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 2px;
    }
    .phase-router { background: rgba(171,99,250,0.2); color: #AB63FA; }
    .phase-executor { background: rgba(255,161,90,0.2); color: #FFA15A; }
    .phase-responder { background: rgba(25,211,243,0.2); color: #19D3F3; }
    
    /* Timeline */
    .timeline-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 8px;
    }
    
    /* Dividers */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255,183,178,0.3), transparent);
        margin: 24px 0;
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3)
def load_all_traces(log_path: str) -> list:
    """Load all traces from the log file."""
    path = Path(log_path)
    if not path.exists():
        return []
    
    traces = {}
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    tid = entry.get('trace_id')
                    if not tid:
                        continue
                    
                    if tid not in traces:
                        traces[tid] = {
                            'id': tid,
                            'events': [],
                            'timestamp': None,
                            'date': None,
                            'time': None,
                            'query': 'Unknown',
                            'response': '',  # NEW: Store response
                            'total_ms': 0,
                            'success': True
                        }
                    
                    traces[tid]['events'].append(entry)
                    
                    if entry.get('event') == 'trace_start':
                        ts = entry.get('timestamp', '')
                        traces[tid]['timestamp'] = ts
                        traces[tid]['query'] = entry.get('query', 'Unknown')
                        try:
                            dt = datetime.fromisoformat(ts)
                            traces[tid]['date'] = dt.strftime("%Y-%m-%d")
                            traces[tid]['time'] = dt.strftime("%H:%M:%S")
                        except:
                            traces[tid]['date'] = 'Unknown'
                            traces[tid]['time'] = ts[11:19] if len(ts) > 19 else '??:??'
                            
                    elif entry.get('event') == 'trace_end':
                        traces[tid]['total_ms'] = entry.get('total_ms', 0)
                        traces[tid]['success'] = entry.get('success', True)
                        traces[tid]['response'] = entry.get('response_preview', '')  # NEW
                        
                except json.JSONDecodeError:
                    continue
        
        # Sort events within each trace
        result = []
        for tid, trace in traces.items():
            if trace['timestamp']:
                trace['events'].sort(key=lambda x: x.get('elapsed_ms', 0))
                result.append(trace)
        
        # Sort traces by timestamp (newest first)
        result.sort(key=lambda x: x['timestamp'] or '', reverse=True)
        return result
        
    except Exception as e:
        st.error(f"Error loading logs: {e}")
        return []

def group_by_date(traces: list) -> dict:
    """Group traces by date."""
    grouped = defaultdict(list)
    for trace in traces:
        grouped[trace['date']].append(trace)
    return dict(grouped)

def get_phase_events(events: list) -> dict:
    """Group events by phase (Router, Executor, Responder)."""
    phases = defaultdict(list)
    for event in events:
        if event.get('event') in ['trace_start', 'trace_end']:
            continue
        stage = event.get('stage', 'Other')
        phases[stage].append(event)
    return dict(phases)

# ═══════════════════════════════════════════════════════════════════════════════
# COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════

def render_kpis(traces: list):
    """Render top-level KPI cards."""
    if not traces:
        return
    
    total = len(traces)
    success = sum(1 for t in traces if t['success'])
    avg_latency = sum(t['total_ms'] for t in traces) / total if total else 0
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📊 Total Queries", total)
    col2.metric("✅ Success Rate", f"{(success/total)*100:.0f}%")
    col3.metric("⚡ Avg Latency", f"{avg_latency/1000:.2f}s")
    col4.metric("📅 Days Tracked", len(set(t['date'] for t in traces)))

def render_phase_details(phase_name: str, events: list):
    """Render detailed events for a phase."""
    icon = "🔹"
    if phase_name == "Router": icon = "🚥"
    elif phase_name == "Executor": icon = "⚙️"
    elif phase_name == "Responder": icon = "🗣️"
    
    total_duration = sum(e.get('duration_ms', 0) for e in events)
    duration_str = f"({round(total_duration/1000, 2)}s)" if total_duration else ""
    
    with st.expander(f"{icon} **{phase_name}** {duration_str}", expanded=False):
        for event in events:
            elapsed = round(event.get('elapsed_ms', 0) / 1000, 2)
            content = event.get('content', '')
            status = event.get('status', 'INFO')
            
            # Format based on content type
            if "Tool:" in content:
                st.markdown(f"`T+{elapsed}s` :orange[**{content}**]")
            elif "Decision:" in content:
                st.markdown(f"`T+{elapsed}s` :violet[**{content}**]")
            elif status == "ERROR":
                st.error(f"T+{elapsed}s {content}")
            else:
                st.markdown(f"`T+{elapsed}s` {content}")
            
            # Show metadata if present
            metadata = event.get('metadata')
            if metadata:
                st.json(metadata)

def render_query_card(trace: dict):
    """Render a single query card with expandable phases."""
    success_icon = "🟢" if trace['success'] else "🔴"
    latency = round(trace['total_ms'] / 1000, 2)
    
    # Main query expander
    with st.expander(
        f"{success_icon} **{trace['time']}** — {trace['query'][:60]}{'...' if len(trace['query']) > 60 else ''} `{latency}s`",
        expanded=False
    ):
        # ─── Input/Output Section ─────────────────────────────────────
        st.markdown("#### 💬 Conversation")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🧑 User Input:**")
            st.info(trace['query'])
        with col2:
            st.markdown("**🌸 Sakura Response:**")
            response = trace.get('response', 'No response captured')
            if response:
                st.success(response)
            else:
                st.warning("Response not captured in logs")
        
        st.divider()
        
        # ─── Phase Parameters (replaces graph) ────────────────────────
        st.markdown("#### ⚡ Pipeline Performance")
        
        phases = get_phase_events(trace['events'])
        
        # Calculate durations for each phase
        param_cols = st.columns(3)
        phase_order = ['Router', 'Executor', 'Responder']
        phase_icons = {'Router': '🚥', 'Executor': '⚙️', 'Responder': '🗣️'}
        
        for i, phase in enumerate(phase_order):
            if phase in phases:
                duration = sum(e.get('duration_ms', 0) for e in phases[phase])
                with param_cols[i]:
                    st.metric(
                        label=f"{phase_icons.get(phase, '🔹')} {phase}",
                        value=f"{round(duration/1000, 2)}s"
                    )
        
        st.divider()
        
        # ─── Phase Details ────────────────────────────────────────────
        st.markdown("#### 📜 Execution Details")
        
        for phase in phase_order:
            if phase in phases:
                render_phase_details(phase, phases[phase])
        
        # Any other phases
        for phase, events in phases.items():
            if phase not in phase_order:
                render_phase_details(phase, events)

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    # ─── Header ───────────────────────────────────────────────────────────────
    st.title("🌸 Sakura Sight")
    st.caption("Real-time observability for your AI assistant")
    
    # ─── Sidebar: Data Source ─────────────────────────────────────────────────
    st.sidebar.markdown("## 📡 Data Source")
    
    sources = {}
    if LOCAL_LOG.exists():
        sources["🔧 Development"] = str(LOCAL_LOG)
    if APPDATA_LOG and APPDATA_LOG.exists():
        sources["🚀 Production"] = str(APPDATA_LOG)
    
    if not sources:
        sources["🔧 Development"] = str(LOCAL_LOG)
    
    selected_source = st.sidebar.radio(
        "Log Location",
        options=list(sources.keys()),
        index=0,
        label_visibility="collapsed"
    )
    current_log = Path(sources[selected_source])
    
    st.sidebar.caption(f"📂 `{current_log.name}`")
    
    if st.sidebar.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()
    
    # ─── Load Data ────────────────────────────────────────────────────────────
    traces = load_all_traces(str(current_log))
    
    if not traces:
        st.warning("No traces found. Interact with Sakura to generate data.")
        st.info(f"Looking for logs at: `{current_log}`")
        return
    
    # ─── KPI Section ──────────────────────────────────────────────────────────
    render_kpis(traces)
    st.divider()
    
    # ─── Sidebar: Date Filter ─────────────────────────────────────────────────
    grouped = group_by_date(traces)
    dates = list(grouped.keys())
    
    st.sidebar.markdown("## 📅 Filter by Date")
    selected_date = st.sidebar.selectbox(
        "Select Date",
        options=["All Dates"] + dates,
        index=0,
        label_visibility="collapsed"
    )
    
    # Filter traces
    if selected_date == "All Dates":
        filtered_traces = traces
    else:
        filtered_traces = grouped.get(selected_date, [])
    
    st.sidebar.markdown(f"**{len(filtered_traces)}** queries shown")
    
    # ─── Main Content: Date Groups ────────────────────────────────────────────
    if selected_date == "All Dates":
        # Show grouped by date
        for date in dates:
            date_traces = grouped[date]
            
            # Date header
            st.markdown(f"### 📅 {date}")
            st.caption(f"{len(date_traces)} queries")
            
            # Query cards
            for trace in date_traces:
                render_query_card(trace)
            
            st.markdown("---")
    else:
        # Single date view
        st.markdown(f"### 📅 {selected_date}")
        st.caption(f"{len(filtered_traces)} queries")
        
        for trace in filtered_traces:
            render_query_card(trace)
    
    # ─── Footer ───────────────────────────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.caption("🌸 Sakura Sight v2.0")

if __name__ == "__main__":
    main()
