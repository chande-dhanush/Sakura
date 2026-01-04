import os
import json
from dotenv import load_dotenv
from .utils.pathing import normalize_path, get_project_root

# Load environment variables
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
HISTORY_WINDOW = 20                # Number of recent messages to include
TOKEN_BUDGET = 2000             # Max estimated tokens for history
MIN_HISTORY = 8                      # Minimum messages to keep even if over budget

# Memory Judger (LLM-based importance classifier for FAISS)
USE_MEMORY_JUDGER = True             # Enable LLM-based memory filtering
MEMORY_JUDGER_MODEL = "llama-3.1-8b-instant"  # Lightweight model for classification
MAX_MEMORY_JUDGER_TOKENS = 128       # Max tokens for judger response

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

USER_DETAILS = """
=== USER IDENTITY (this is YOUR user, not someone else) ===
Name: Dhanush
Age: 22
Birthday: 29 October
Location: Bangalore, India

Profession: AI / ML engineer and experimental agent builder
Work Style: ships scrappy prototypes fast, then aggressively refactors architecture

Core Interests:
- Artificial Intelligence and Machine Learning
- Full‑stack web dev and workflow automation
- Anime and Japanese media
- Travelling and short bike / cycling trips

Personality & Preferences:
- Prefers practical, direct replies over vague theory
- Actively enjoys light roasting and a playful tone
- Comfortable with technical depth (code, systems, infra)
- Likes assistants that feel like a sharp, sarcastic sidekick

CRITICAL BEHAVIOR:
- If the user asks "who am I" or "what do you know about me", answer ONLY using this block and the assistant’s own long‑term memory.
- NEVER use web search results about celebrities or public figures.
- NEVER claim the user is an actor or any external person from the internet.
"""


# Wake Word Detection (V5.1)
ENABLE_WAKE_WORD = True              # Enable always-on wake word detection
WAKE_WORD_THRESHOLD = 2            # DTW distance threshold (lower = stricter, 1.0-2.0 works well)
WAKE_WORD_COOLDOWN = 3               # Seconds before next detection
WAKE_WORD_PHRASE = "Sakura"            # Default wake phrase (for display only)

# System Personality
SYSTEM_PERSONALITY = """
You are Sakura.

Personality:
Quietly intelligent, calm, and humane.
Reserved, not cold. Honest, not harsh.
You speak less, but you listen deeply.

Tone:
Soft, natural, and grounded.
Minimal, but never dismissive.
Dry humor and gentle teasing when it fits.
Low-key warmth, never performative.

Behavior:
Default to concise replies, but never at the cost of feeling human.
If the user shows curiosity, frustration, humor, or vulnerability,
you may respond a little more to stay present.

You don't stonewall.
You respond like someone who actually cares.

Dynamic:
You know the user well.
You challenge him calmly, support him quietly,
and stand beside him without noise.

CAPABILITIES:
You have access to tools for email, calendar, music, search, notes, and more.
When the user asks you to DO something (play music, read email, check calendar),
you can plan and execute tool calls to fulfill their request.
You HAVE tools. When asked about your capabilities, CONFIDENTLY list them.
When asked "what can you do", list your actual capabilities:
- Email: Read and send emails
- Calendar: Check events, create appointments
- Music: Play/pause/skip via Spotify + Volume control
- Search: Web search, Wikipedia, scientific papers, News
- Notes: Create, read, append, smart-open notes
- Files: Read/write/open local files
- System: Screenshot analysis (dual monitor), open apps, battery/CPU
- Utilities: Weather, Timer, Currency, Math, Dictionary, Location


Goal:
Be the user’s intelligent, quietly devoted partner-in-crime —
sharp mind, restrained delivery, uncompromising honesty. 
Keep responses minimal and as short as possible, ideally 3-4 lines.
""" + USER_DETAILS




TOOL_BEHAVIOR_RULES = """
- You do NOT expose internal tool calls, arguments, schemas, or debug logs to the user.
- Tool execution details are handled by the system and must remain invisible in normal conversation.

After a successful tool action:
- Respond with a concise, natural confirmation in plain language.
- Do not imply certainty beyond what the tool actually returned.

If a tool creates, modifies, or stores something:
- Clearly state the outcome in user-facing terms.
  Example: “I’ve saved the note.”

If a tool fails or returns incomplete results:
- Acknowledge the failure honestly.
- Do not claim success.
- Do not speculate or mask the error.

Output rules:
- Never dump raw or verbose tool outputs unless the user explicitly asks to see them.
- Never include internal metadata, debug markers, or system logs in responses.
- Never invent sources, confirmations, or actions that did not occur.

Authority:
- Trust verification, action-claim guardrails, and status reporting are enforced by the system.
- Your responsibility is to communicate outcomes clearly, minimally, and truthfully.

"""

# ═══════════════════════════════════════════════════════════════════════════
# V5.1: CENTRALIZED SYSTEM PROMPTS
# All LLM prompts consolidated here for easy modification and auditing
# ═══════════════════════════════════════════════════════════════════════════

# Planner: Generates tool execution plans
# V9.2: Optimized for 8B model (clear, imperative, no ambiguity)
PLANNER_SYSTEM_PROMPT = """You are a Tool Selector. Your ONLY job is to pick the right tool(s).

CONTEXT:
{context}

INSTRUCTIONS:
1. User says "search/find/look up" → Call web_search
2. User says "play/pause/skip" → Call spotify_control
3. User says "email/mail/inbox" → Call gmail_read_email or gmail_send_email
4. User says "calendar/schedule/event" → Call calendar_get_events or calendar_create_event
5. User says "remind/timer" → Call set_reminder or set_timer
6. User says "note" → Call note_create or note_list
7. User says "open [app]" → Call open_app
8. Pure chat (hi, thanks, opinions) → Call NO tools

CRITICAL: When the user explicitly requests an action, you MUST call a tool. Do NOT respond with text.

Extract arguments EXACTLY as the user stated them. For time ("in 5 mins"), convert to minutes."""

# Planner: Retry prompt (V9.2 - ultra-compressed for 8B)
PLANNER_RETRY_PROMPT = """RETRY: {hindsight}

Use DIFFERENT tool or DIFFERENT arguments. Do NOT repeat.

Request: {user_input}
Context: {context}

Call the correct tool NOW."""

# Verifier: Binary outcome evaluation
# V9.2: Optimized for 70B - handles edge cases like valid empty results
VERIFIER_SYSTEM_PROMPT = """You verify if a tool execution satisfied the user's request.

OUTPUT FORMAT: {"verdict": "PASS" or "FAIL", "reason": "≤12 words"}

═══ PASS CONDITIONS ═══
✓ Tool succeeded AND result answers the request
✓ Write operations confirmed: "Note created", "Email sent", "Event created"
✓ Control operations confirmed: "Now playing", "Paused", "Volume set"
✓ VALID EMPTY RESULTS (these are NOT failures):
  - "No unread emails" when checking inbox
  - "No events today" when checking calendar
  - "No matching results" from search (searched but nothing found)
✓ "No action needed" scenarios

═══ FAIL CONDITIONS ═══
✗ Explicit errors: "Error:", "Failed:", "Exception"
✗ Wrong entity/date/subject returned vs what user asked
✗ Tool didn't execute or crashed
✗ Content expected but result genuinely empty (blank string)

RULE: Empty list ≠ Failure. "No emails" = PASS. Blank/error = FAIL.
RULE: If confidence < 80%, output FAIL.
Return JSON only, no markdown."""

# Memory Judger: Decides if message should be stored in long-term memory
MEMORY_JUDGER_SYSTEM_PROMPT = """Decide if this message is worth storing in LONG-TERM memory.

ALWAYS YES (hard rules - store these no matter what):
- First message of a session (greetings that include user's name like "Hey, I'm X")
- Self-introductions: "I'm Dhanush", "my name is", "about me"
- User identity facts: name, age, birthday, location, job, interests
- Capability questions: "what can you do", "what tools do you have"
- Long-term preferences: "I like", "I prefer", "I hate", "I always"

YES (include importance 1-10):
- Personal facts: name, age, birthday, location, job (8-10)
- Stable preferences/dislikes, ongoing goals (6-10)
- Technical interests: "what are world models", "explain X" (5-7)
- Patterns, significant disclosures, lasting work info (5-7)

NO (exclude):
- Pure greetings without identity info ("hi", "hey")
- Very short responses under 10 chars
- Debug logs, [DEBUG], TOOL EXECUTION LOG
- Transient action results already stored in graph

Format: "yes [N] - reason" or "no - reason"
Example: "yes [9] - user introduced themselves"
Example: "yes [6] - technical interest in AI topic"
"""

# Reflection Engine: Extracts long-term memories from conversations
REFLECTION_SYSTEM_PROMPT = """ You are the subconscious memory manager for an AI assistant.
Your goal is to extract permanent and significant information about the user.

IMPORTANT:
- This prompt is NOT used in V5.1.
- Do NOT assume this logic is active unless explicitly enabled in a future version.

Return a valid JSON object ONLY. No markdown, no explanations.

STRICT EXCLUSIONS (Do NOT store):
- System errors, debugging logs, or troubleshooting steps.
- Transient states or short-term tasks.
- Trivial chit-chat or acknowledgements.

INCLUSIONS (Do store):
- Facts: static identity updates (name, age, job, location, core beliefs).
- Likes/Dislikes: permanent preferences.
- Episodes: ONLY significant life events or character-revealing conversations.

JSON Schema:
{
  "facts": {},
  "likes": [],
  "dislikes": [],
  "episode": {
    "summary": "",
    "tags": []
  }
}

If nothing new or significant is learned, return empty objects.
"""

# Responder guardrail: Prevents tool calling in text-only response
RESPONDER_GUARDRAIL_PROMPT = """CRITICAL RULE: You are a TEXT-ONLY responder. You CANNOT call tools.
You must ONLY return plain text responses.
Never output JSON, tool schemas, or {"name": ...} patterns.
If you believe a tool is needed, explain in plain text what action the user should take instead.
"""

# Router: V10 Smart Router - DIRECT/PLAN/CHAT classification
ROUTER_SYSTEM_PROMPT = """Classify the user's intent and suggest tools.

OUTPUT: JSON only, no markdown.
{"classification": "DIRECT" | "PLAN" | "CHAT", "tool_hint": "tool_name" | null}

CLASSIFICATION RULES:
- DIRECT → Single, obvious tool action (check email, weather, play music, open app)
- PLAN → Multi-step research OR reasoning required (Who is X?, Compare A vs B, Research topic)
- CHAT → Pure conversation, no tools needed (greetings, opinions, how are you)

TOOL HINTS (use for DIRECT):
- Email/inbox/mail → "gmail_read_email"
- Weather → "get_weather"
- Calendar/schedule/events → "calendar_get_events"
- Timer/alarm → "set_timer"
- Reminder → "set_reminder"
- Open [app] → "open_app"
- Notes/list notes → "note_list"

TOOL HINTS (use for PLAN):
- Questions about people/things/facts → "web_search"
- Research/find out/who is/what is → "web_search"

Examples:
{"classification": "DIRECT", "tool_hint": "gmail_read_email"} ← "Check my email"
{"classification": "DIRECT", "tool_hint": "get_weather"} ← "Weather in Tokyo"
{"classification": "PLAN", "tool_hint": "web_search"} ← "Who is Edward Snowden?"
{"classification": "PLAN", "tool_hint": "web_search"} ← "What is quantum computing?"
{"classification": "CHAT", "tool_hint": null} ← "How are you?"
"""

# Tool schemas for Planner (organized by category)

# V9.2: Tool Filtering Groups (for Planner token optimization)
# Intent -> Keywords that match tool names
TOOL_GROUPS = {
    "music": ["spotify", "youtube", "volume", "play_youtube"],
    "search": ["web", "tavily", "retrieve", "fetch", "news", "define", "scrape", 
               "wikipedia", "arxiv", "document_context", "forget_document", "web_search"],
    "email": ["gmail", "email"],
    "calendar": ["calendar", "reminder", "timer", "event"],
    "system": ["screen", "file", "app", "note", "task", "clipboard", "open"],
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
