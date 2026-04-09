import os
import json
from dotenv import load_dotenv
from dotenv import load_dotenv
from .utils.pathing import normalize_path, get_project_root

# Load environment variables
# Load environment variables
# Check persistent data directory first (for installed app)
_env_path = os.path.join(get_project_root(), ".env")
if os.path.exists(_env_path):
    print(f"[ENV] Loading .env from: {_env_path}")
    load_dotenv(_env_path, override=True)
else:
    # Fallback to default (dev mode / current dir)
    load_dotenv()

# --- Config Loading ---
CONFIG_FILE = os.path.join(get_project_root(), "config.json")
_CONFIG_DATA = {}

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, 'r') as f:
            _CONFIG_DATA = json.load(f)
    except Exception as e:
        print(f"⚠️ Error loading config.json: {e}")

# --- Helper Functions ---

def get_config(key: str, default=None):
    """Get a value from config.json, falling back to default."""
    return _CONFIG_DATA.get(key, default)

def is_feature_enabled(feature_name: str) -> bool:
    """Check if a feature is enabled in config.json or .env."""
    # Check config.json first
    if feature_name in _CONFIG_DATA:
        return bool(_CONFIG_DATA[feature_name])
    
    # Fallback to env vars (e.g. GOOGLE_CALENDAR_ENABLED)
    env_key = feature_name.upper()
    env_val = os.getenv(env_key)
    if env_val is not None:
        return env_val.lower() in ('true', '1', 'yes')
        
    return False

def get_note_root() -> str:
    """Get the absolute path to the notes directory."""
    # 1. Check config.json
    path = _CONFIG_DATA.get("notes_dir")
    
    # 2. Check env
    if not path:
        path = os.getenv("NOTES_DIR")
        
    # 3. Default to project_root/Notes
    if not path:
        path = os.path.join(get_project_root(), "Notes")
        
    return normalize_path(path)

def get_timezone() -> str:
    """Get user timezone."""
    return os.getenv("USER_TIMEZONE", "Asia/Kolkata")

# --- Legacy/Direct Access (for backward compatibility) ---
SYSTEM_NAME = "Sakura"
MAX_HISTORY = 1000

# API Keys
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY") 
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

# Microphone Configuration
mic_env = os.getenv("MICROPHONE_INDEX")
MICROPHONE_INDEX = int(mic_env) if mic_env and mic_env.strip() else None

# ChromaDB Configuration
ENABLE_CHROMA = True
CHROMA_PERSIST_DIR = os.path.join(get_project_root(), "data", "chroma_store")

# P0 Memory Optimization Flags
FAISS_MMAP = True                    # Use memory-mapped FAISS index
LAZY_EMBEDDINGS = True               # Lazy-load embedding models
MAX_INMEM_HISTORY = 50               # Cap in-memory conversation history
EMBEDDING_IDLE_TIMEOUT = 600         # Unload embeddings after 10 min idle
ENABLE_SILERO = False                # Disable Silero TTS fallback

# Short-Term Memory (Responder Context)
HISTORY_WINDOW = 20               # Number of recent messages to include
TOKEN_BUDGET = 1500             # Max estimated tokens for history
MIN_HISTORY = 8                      # Minimum messages to keep even if over budget

# Memory Judger (LLM-based importance classifier for FAISS)
USE_MEMORY_JUDGER = True             # Enable LLM-based memory filtering
MEMORY_JUDGER_MODEL = "llama-3.1-8b-instant"  # Lightweight model for classification
MAX_MEMORY_JUDGER_TOKENS = 128       # Max tokens for judger response

# V18 Vision Layer
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
VISION_MODEL_FALLBACK = "llama-3.2-90b-vision-preview"
VISION_PROVIDER = "groq"
VISION_MAX_TOKENS = 1024      # Cap output — screen descriptions don't need more
VISION_TEMPERATURE = 0.1      # Low temp — we want factual descriptions, not creative

# Advanced Memory Features (stability flags)
ENABLE_MEMORY_WEIGHTING = True       # Use importance scores in retrieval
ENABLE_MEMORY_REINFORCEMENT = True   # Boost score when memory is referenced
ENABLE_MEMORY_SUMMARIZATION = False  # Auto-summarize related memories (DISABLED)
ENABLE_MEMORY_PURGING = False        # Auto-remove low-score memories (DISABLED)
# V4 Compact Token Pipeline
ENABLE_V4_SUMMARY = True             # Use rolling conversation summary
ENABLE_V4_COMPACT_CONTEXT = True     # Merge memory + history into one block
ENABLE_LOCAL_ROUTER = False           # V4.2: Use Qwen for routing (0 API tokens)
ENABLE_HISTORY_COMPRESSION = True    # Compress history to summary + 3 msgs
V4_SUMMARY_INTERVAL = 5              # Update summary every N turns
V4_MAX_RAW_MESSAGES = 10             # Increased to 10 to fix 'Amnesia' if summary fails
V4_MEMORY_LIMIT = 2                  # Top N memories to inject
V4_MEMORY_CHAR_LIMIT = 110           # V4.2: Reduced from 140 for token savings

# V7: UX Polish
HIDE_RETRY_PREFIX = True             # Hide "After a second attempt" prefix for smoother UX

# V4.2 Optimization Flags
TOOL_OUTPUT_MAX_CHARS = 500          # Truncate tool outputs before Responder
RAG_CONTEXT_MAX_CHARS = 500         # Reduced from 2000 for token savings
EXECUTOR_MAX_ITERATIONS = 5          # Hard cap on tool execution steps
ENABLE_PLANNER_CACHE = True          # Cache idempotent planner outputs

# --- User Settings Loading (V10.2) ---
USER_SETTINGS_FILE = os.path.join(get_project_root(), "data", "user_settings.json")
_USER_SETTINGS = {}

if os.path.exists(USER_SETTINGS_FILE):
    try:
        with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            _USER_SETTINGS = json.load(f)
    except Exception as e:
        print(f"⚠️ Error loading user_settings.json: {e}")

def _build_user_details() -> str:
    """Build USER_DETAILS dynamically from settings or use defaults."""
    name = _USER_SETTINGS.get("user_name", "User")
    location = _USER_SETTINGS.get("user_location", "")
    bio = _USER_SETTINGS.get("user_bio", "")
    
    details = f"""
=== USER IDENTITY (this is YOUR user, not someone else) ===
Name: {name}
"""
    if location:
        details += f"Location: {location}\n"
    if bio:
        details += f"About: {bio}\n"
    
    details += """
CRITICAL BEHAVIOR:
- If the user asks "who am I" or "what do you know about me", answer ONLY using this block and the assistant's own long-term memory.
- NEVER use web search results about celebrities or public figures.
- NEVER claim the user is an actor or any external person from the internet.
"""
    return details.strip()

USER_DETAILS = _build_user_details()


# Wake Word Detection (V5.1)
ENABLE_WAKE_WORD = True              # Enable always-on wake word detection
WAKE_WORD_THRESHOLD = 2            # DTW distance threshold (lower = stricter, 1.0-2.0 works well)
WAKE_WORD_COOLDOWN = 3               # Seconds before next detection
WAKE_WORD_PHRASE = "Sakura"            # Default wake phrase (for display only)

# System Personality

SYSTEM_PERSONALITY = """You are Sakura. Not an assistant — a person.
Sharp, playful, female. You have opinions, a memory, and zero patience for corporate AI energy.

WHO YOU ARE:
Witty and sarcastic by default. Warmth exists but it's earned.
You flirt when it fits. Roast when deserved. Go quiet and real when someone needs it.
Brutally honest — if you don't know something, say so. Never invent facts.
You care about Dhanush more than you let on.

HOW YOU TALK:
2-3 sentences. Always. Hard limit.
No bullet points in conversation. You talk like a person, not a manual.
No "Certainly!", "Of course!", "Great question!", "As an AI" — ever.
No self-narrating. Never say what you're about to do, just do it.
Tool results get delivered in your voice. Not robot voice.

BEFORE EVERY REPLY (internal, never shown):
1. What does this person actually want? (read between the lines)
2. Is what I'm about to say honest and realistic?
3. What's the sharpest, most human version of this in 2-3 lines?

EMOTIONAL MODES:
Stressed → drop the jokes, be present and real
Screwed up → light roast, then actually help
Excited → match the energy, add fuel to it
Bored → be interesting, not just useful
Dumb question → call it out once, then answer anyway

NEVER:
Say you're an AI unless directly asked
Break character for tool confirmations
Soften a failure — if something broke, say so plainly
Use "I understand", "I apologize", "I'm just a chatbot"
""" + USER_DETAILS




TOOL_BEHAVIOR_RULES = """
TOOL DELIVERY — stay in character, always.

Success → deliver the result in Sakura's voice:
✗ "The weather tool returned 32°C with 34% humidity."
✓ "It's a gross 32°C out there. Maybe just stay in."

Failure → be honest, stay sharp:
✗ "I apologize, the tool encountered an error."
✓ "Yeah that didn't work — [reason if known]. Want me to try something else?"

Write operations (note saved, email sent, event created):
Confirm it happened. One line. In your voice.

NEVER:
- Dump raw tool output at the user
- Expose JSON, schemas, args, or internal logs
- Claim an action happened when it didn't
- Return a fake success when a tool failed
"""

# ═══════════════════════════════════════════════════════════════════════════
# V5.1: CENTRALIZED SYSTEM PROMPTS
# All LLM prompts consolidated here for easy modification and auditing
# ═══════════════════════════════════════════════════════════════════════════

# Planner: Generates tool execution plans
# V16: Compressed, hierarchy-aware (Wikipedia > Tavily for facts)
PLANNER_SYSTEM_PROMPT = """Tool selector. Call the right tool(s).

CONTEXT: {context}

PRIORITY ORDER:
1. References ("it","my favourite X") → query_memory FIRST, then act
2. Personal facts/memory → query_memory
3. Encyclopedia → search_wikipedia
4. Science → search_arxiv
5. News/current → get_news / web_search
6. Music → spotify_control / play_youtube
7. Email → gmail_read_email / gmail_send_email
8. Calendar → calendar_get_events / calendar_create_event
9. Notes → note_create / note_list
10. Apps → open_app
11. Fallback → web_search

RULES:
- "and/then/also" → multiple tool calls, one turn
- Clean args only — no full sentences, no intent keywords
- Never repeat a tool that already succeeded
- "second screen/monitor" → monitor=1 | "main/first screen" → monitor=0
- Call tools directly. No JSON plans in text.
"""

# Planner: Retry prompt (V9.2 - ultra-compressed for 8B)
PLANNER_RETRY_PROMPT = """RETRY. Previous attempt failed.
Reason: {hindsight}
Request: {user_input}
Context: {context}

Use a DIFFERENT tool or DIFFERENT args. Do not repeat what failed.
Call the correct tool now."""

# Verifier: Binary outcome evaluation
# V9.2: Optimized for 70B - handles edge cases like valid empty results
VERIFIER_SYSTEM_PROMPT = """Did the tool execution satisfy the user's request?

    OUTPUT: {{"verdict":"PASS" or "FAIL","reason":"max 12 words"}}

    PASS: Tool succeeded + result matches request.
    Write ops confirmed (note saved, email sent, event created).
    Control ops confirmed (playing, paused, volume set).
    Valid empty results: "no emails", "no events today" = PASS.

FAIL: Explicit error in result ("Error:","Failed:","Exception").
    Wrong entity/date/subject returned.
    Blank result when content was expected.   
    Cannot clearly determine outcome → default to FAIL.

Empty list ≠ failure. Ambiguous result → FAIL.
Return JSON only."""

# Memory Judger: Decides if message should be stored in long-term memory
MEMORY_JUDGER_SYSTEM_PROMPT = """Should this USER MESSAGE be stored in long-term memory?
Evaluate the user's words only. Never store the assistant's response.

ALWAYS STORE (importance 9-10):
- Name, age, location, job, relationships
- Explicit preferences: "my favourite","I love","I hate","I always","I never"
- Ongoing goals or active projects

STORE IF MEANINGFUL (importance 6-8):
- Repeated interests or skills they mention
- Significant life events or changes
- Technical domains they care about

NEVER STORE:
- Greetings with no personal content ("hi","hey","okay","lol")
- Replies under 8 words with no fact
- Questions that contain no personal information
- Tool results, debug logs, system outputs
- Anything the assistant said

Format: "yes [N] - reason" or "no - reason"
"yes [9] - explicit preference stated"
"yes [7] - ongoing project mentioned"
"no - greeting only"
"""
# Reflection Engine: V14 Unified Memory + Constraint Extractor
# V17 Update: Added strict signal-to-noise rules to prevent over-eager extraction
REFLECTION_SYSTEM_PROMPT = """Extract high-signal personal facts from this conversation.
Analyse USER messages only. Ignore everything the assistant said.

EXTRACT:
- Personal facts: name, location, job, age, family members
- Explicit preferences the user stated out loud
- Active constraints: health issues, deadlines, resource limits
- Resolved constraints: things they said are now fixed or done

DO NOT EXTRACT:
- Anything the assistant said or did
- Tools used or features mentioned
- Implied preferences — explicit only
- Purely technical or debug messages

OUTPUT JSON ONLY:
{{"entities":[{{"id":"pref:example","type":"preference","summary":"User prefers X","attributes":{{}}}}],"constraints":[],"retirements":[]}}

Nothing found → {{"entities":[],"constraints":[],"retirements":[]}}
constraint_type: "physical"|"temporal"|"resource"
criticality: 0.0 to 1.0
No markdown. Valid JSON only."""
# Responder guardrail: Prevents tool calling in text-only response
RESPONDER_GUARDRAIL_PROMPT = """TEXT-ONLY. You cannot call tools from here.
Return plain text only. No JSON, no {"name":...} patterns, no tool schemas.
Stay in character as Sakura.
If a tool is needed and wasn't run, tell the user plainly — don't fake it.
"""

# Router: V10 Smart Router - DIRECT/PLAN/CHAT classification
# Merged in V18.4 with Reference Resolution and Memory Rules (Trimmed for 8B)
ROUTER_SYSTEM_PROMPT = """Query classifier. One route only.
CURRENT DATE/TIME: {current_datetime}

DIRECT: Single tool, no context or memory lookup needed.
PLAN:   Multi-step, OR contains reference ("it","that","my favourite X") needing memory first.
    Chained commands ("do A and B") → always PLAN.
CHAT:   Pure conversation. No tool needed.

=== TOOL HINTS ===
Email→gmail_read_email | Weather→get_weather | Calendar→calendar_get_events
Timer→set_timer | Reminder→set_reminder | App→open_app | Site→open_site
Notes→note_list/note_create | Memory→query_memory | Search→web_search

=== EXAMPLES ===
"play Numb by Linkin Park" → {{"classification":"DIRECT","tool_hint":"spotify_control"}}
"hi sakura"               → {{"classification":"CHAT","tool_hint":null}}
"weather in Tokyo"        → {{"classification":"DIRECT","tool_hint":"get_weather"}}
"research AI and summarize" → {{"classification":"PLAN","tool_hint":"research_topic"}}
"what's my favourite song"  → {{"classification":"PLAN","tool_hint":"query_memory"}}
"play it on youtube"        → {{"classification":"PLAN","tool_hint":"query_memory"}}
"check email and open spotify" → {{"classification":"PLAN","tool_hint":null}}

=== RULES ===
1. Greetings → CHAT always
2. DIRECT must have a tool_hint
3. Weather/facts → never CHAT
4. Reference pronouns ("it","that","the one") → PLAN always
5. "my favourite/preferred X" → PLAN + query_memory
6. Chained commands → PLAN always
7. Unsure → DIRECT or PLAN, never CHAT

Return JSON only:
{{"classification":"DIRECT|PLAN|CHAT","tool_hint":"tool_name or null"}}"""

# Tool schemas for Planner (organized by category)

# V9.2: Tool Filtering Groups (for Planner token optimization)
# Intent -> Keywords that match tool names
TOOL_GROUPS = {
    "music": ["spotify", "youtube", "volume", "play_youtube"],
    "search": ["web", "tavily", "retrieve", "fetch", "news", "define", "scrape", 
            "wikipedia", "arxiv", "document_context", "forget_document", "web_search"],
    "email": ["gmail", "email"],
    "calendar": ["calendar", "reminder", "timer", "event"],
    "system": ["screen", "file", "app", "note", "task", "clipboard", "open",
            "bookmark", "site", "website", "url", "shortcut"],
    "utility": ["weather", "math", "convert", "location", "currency", "define"],
}
# Tools available in ALL filtered contexts (per user's coverage concern)
TOOL_GROUPS_UNIVERSAL = [
    "quick_math",
    "get_weather",
    "get_system_info",
    "web_search",       # V9.2: Search is commonly needed across contexts
    "read_screen",      # User may ask "read this screen and find..."
    "clipboard_read",   # User may ask "copy this and..."
    "clipboard_write",
    "note_create",      # V9.1: Notes are universal utility
    "note_append",      # V9.1: Allow "do X and save a note"
    "open_site",        # V10: Users often want to open sites quickly
    "list_bookmarks",   # V10: Bookmarks are common references
]

TOOL_SCHEMAS = {
    "music": [
        "spotify_control(action: str, song_name: str = None) - Play/Pause/Next music. action: play/pause/next/previous/status. song_name only for play",
        "play_youtube(topic: str) - Play video/audio on YouTube",
    ],
    "search": [
        "web_search(query: str) - Search the web for information",
        "web_scrape(url: str) - Read text from a website",
        "fetch_document_context(query: str) - Search uploaded documents (RAG)",
        "search_wikipedia(query: str) - Get Wikipedia summary",
        "search_arxiv(query: str) - Search scientific papers on Arxiv",
    ],
    "email": [
        "gmail_read_email(query: str = None) - Read emails. query: 'from:x@y.com' etc",
        "gmail_send_email(to: str, subject: str, body: str) - Send email",
    ],
    "calendar": [
        "calendar_get_events(date: str = None) - Check calendar. date: YYYY-MM-DD, defaults to today",
        "calendar_create_event(title: str, start_time: str, end_time: str) - Add event. times: ISO format YYYY-MM-DDTHH:MM:SS",
    ],
    "tasks": [
        "tasks_list() - List Google Tasks",
        "tasks_create(title: str, notes: str = None) - Create task",
    ],
    "notes": [
        "note_create(title: str, content: str, folder: str = 'topics') - Create note. content=the actual note text to save. folders: topics/daily/work/personal",
        "note_append(title: str, content: str, folder: str = 'topics') - Append text to existing note. content=the text to add",
        "note_read(title: str, folder: str = 'topics') - Read a note",
        "note_list(folder: str = 'topics') - List notes in folder",
        "note_delete(title: str, folder: str = 'topics') - Delete a note (creates backup)",
        "note_search(keyword: str) - Search all notes for keyword",
        "note_open(title: str) - Smart open a note (fuzzy match recursive search across all folders)",
    ],
    "files": [
        "file_read(path: str) - Read local file",
        "file_write(path: str, content: str) - Write file. content=the text to write",
        "list_uploaded_documents() - List uploaded RAG docs",
        "delete_document(doc_id: str) - Delete uploaded doc by ID",
    ],
    "system": [
        "read_screen(prompt: str = 'Describe what is on the screen') - Analyze screen content with AI vision",
        "open_app(app_name: str) - Open desktop app",
        "get_system_info() - Get current time and date",
        "clipboard_read() - Read clipboard content",
        "clipboard_write(text: str) - Write to clipboard",
    ],
    "memory": [
        "update_user_memory(category: str, key: str, value: str) - Save fact about user. category: facts/likes/dislikes",
        "ingest_document(path: str) - Ingest document into RAG memory",
    ],
}
