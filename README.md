# 🌸 Sakura V13

> A production-grade personal AI assistant with voice, vision, code execution, and 54 tools.

![Version](https://img.shields.io/badge/version-13.0-pink?style=for-the-badge)
![Tauri](https://img.shields.io/badge/Tauri-2.x-blue?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11+-green?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-gray?style=for-the-badge)

<p align="center">
  <img src="docs/sakura_demo.gif" alt="Sakura Demo" width="600"/>
</p>

---

## ✨ What is Sakura?

Sakura is a **desktop AI assistant** that can:
- 🎵 Control Spotify, YouTube, and system media
- 📧 Read/send Gmail, manage Calendar & Tasks
- 🔍 Search the web, scrape websites, take notes
- 🎹 **Execute Python code** in a secure Docker sandbox (V13)
- 🎧 **Transcribe & summarize audio** files (V13)
- 🎙️ Respond to voice commands ("Hey Sakura")
- 🖼️ Analyze images and screenshots
- 🧠 Remember context with **temporal decay** (V13)

**Free to run** — Uses Groq (Llama 3.3 70B) and Google Gemini free tiers.

---

## 🚀 Quick Start (5 Minutes)

### Prerequisites

| Requirement | How to Install |
|-------------|----------------|
| Python 3.11+ | [python.org/downloads](https://www.python.org/downloads/) |
| Node.js 18+ | [nodejs.org](https://nodejs.org/) |
| Rust | [rustup.rs](https://rustup.rs/) |
| Docker Desktop | [docker.com](https://www.docker.com/products/docker-desktop/) (for Code Interpreter) |
| ffmpeg | `winget install FFmpeg` (for Audio Tools) |
| Groq API Key | [console.groq.com](https://console.groq.com) (Free) |

### Windows Setup

```powershell
# 1. Clone the repo
git clone https://github.com/chande-dhanush/Sakura.git
cd Sakura

# 2. Run automated setup (as Administrator)
.\scripts\setup.ps1

# 3. Create .env file with your API key
Copy-Item .env.example .env
notepad .env   # Add your GROQ_API_KEY

# 4. First-time setup (Google OAuth + Voice templates)
cd backend
..\PA\Scripts\python first_setup.py

# 5. Launch!
cd ..\frontend
npm run tauri dev
```

### Linux / macOS Setup

```bash
# 1. Clone the repo
git clone https://github.com/chande-dhanush/Sakura.git
cd Sakura

# 2. Run automated setup
chmod +x scripts/setup.sh
./scripts/setup.sh

# 3. Create .env file
cp .env.example .env
nano .env   # Add your GROQ_API_KEY

# 4. First-time setup
cd backend
source ../PA/bin/activate
python first_setup.py

# 5. Launch!
cd ../frontend
npm run tauri dev
```

---

## 🔑 API Keys

Create a `.env` file in the project root:

```env
# REQUIRED (Free)
GROQ_API_KEY=gsk_your_key_here        # https://console.groq.com

# OPTIONAL (Enhances features)
OPENROUTER_API_KEY=sk-or-your_key     # Vision - https://openrouter.ai
TAVILY_API_KEY=tvly-your_key          # Web search - https://tavily.com

# OPTIONAL (Spotify integration)
SPOTIFY_CLIENT_ID=your_id
SPOTIFY_CLIENT_SECRET=your_secret
```

| Service | Free Tier | What It Enables |
|---------|-----------|-----------------|
| Groq | 30 RPM | Core LLM (Llama 3.3 70B) |
| Tavily | 1000/mo | Web search tool |
| OpenRouter | $5 free | Vision analysis |
| Spotify | Unlimited | Music control |

---

## 📱 Google Integration (Optional)

Gmail, Calendar, and Tasks require Google OAuth:

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a project → Enable `Gmail API`, `Calendar API`, `Tasks API`
3. OAuth consent screen → Add your email as test user
4. Credentials → Create OAuth 2.0 Client ID → Desktop App
5. Download JSON → Rename to `credentials.json` → Place in `backend/`
6. Run `python first_setup.py` → Authorize in browser

> **Tip:** Google integration is optional. Sakura works fine without it!

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Alt+S` | Toggle Quick Search (Omnibox) |
| `Alt+F` | Toggle Full Window |
| `Alt+M` | Hide Mode (for movies) |
| `Escape` | Stop AI generation |
| Say "Sakura" | Voice activation |

---

## 🛠️ Project Structure

```
Sakura/
├── frontend/               # Tauri + Svelte UI
│   ├── src/                # Svelte components
│   └── src-tauri/          # Rust window manager
├── backend/                # FastAPI + LangChain
│   ├── server.py           # Main API server
│   ├── sakura_assistant/
│   │   ├── core/           # Router, Executor, Planner
│   │   └── tools_libs/     # 54 tool implementations
│   ├── tests/              # All test suites
│   └── data/               # World graph, templates
├── scripts/                # Setup & build scripts
│   ├── setup.ps1           # Windows setup
│   ├── setup.sh            # Linux/Mac setup
│   ├── build_bundle.ps1    # Production build
│   └── toggle_startup.*    # Autostart config
├── docs/                   # Documentation
│   ├── DOCUMENTATION.md    # Full API docs
│   ├── V13_AUDIT_REPORT.md # Test coverage report
│   └── V13_WALKTHROUGH.md  # Feature walkthrough
├── audit/                  # Audit scripts
├── .env                    # Your API keys
└── README.md               # This file
```

---

## 🏗️ Building for Production

```powershell
# Option 1: Full automated build
.\scripts\build_bundle.ps1

# Option 2: Manual build
cd frontend
npm run tauri build
```

**Output:** `frontend/src-tauri/target/release/bundle/nsis/Sakura_13.0.0_x64-setup.exe`

This creates a single installer that bundles:
- Compiled Python backend (PyInstaller)
- Tauri desktop shell
- All dependencies

---

## 🆕 What's New in V13

| Feature | Description |
|---------|-------------|
| **Code Interpreter** | Execute Python in Docker sandbox (pandas, numpy, matplotlib) |
| **Audio Tools** | Transcribe & summarize audio files (Google STT) |
| **Temporal Decay** | Memory confidence decays over time (30-day half-life) |
| **Adaptive Routing** | Urgency detection for faster responses |
| **54 Tools** | 8 new tools added |
| **Pre-compiled Regex** | 30% faster routing performance |

### Previous Versions

<details>
<summary>V12 Features</summary>

- Real-time Thought Streams (WebSocket)
- Smart Search Cache
- Context Valve overflow protection
</details>

<details>
<summary>V10.4 Features</summary>

- Flight Recorder (JSONL tracing)
- Few-Shot Router (15 examples)
- Async LLM (parallel tool execution)
- Token Bucket Rate Limiter
</details>

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| "No module named..." | Activate venv: `.\PA\Scripts\activate` |
| Wake word not working | Run `python first_setup.py` |
| Gmail/Calendar errors | Check `credentials.json` placement |
| Code Interpreter fails | Start Docker Desktop first |
| Audio tools fail | Install ffmpeg: `winget install FFmpeg` |
| App won't start | Check `backend/data/flight_recorder.jsonl` for errors |
| Rate limited | Wait 1-2 minutes (free tier limits) |

---

## 👤 Customization

Edit `backend/sakura_assistant/config.py`:

```python
USER_DETAILS = """
Name: Your Name
Role: Your Role
Interests: Your interests
"""

SYSTEM_PERSONALITY = """
You are Sakura, a helpful AI assistant...
"""
```

---

## � Documentation

For those who want to dive deeper:

| Document | Description |
|----------|-------------|
| [DOCUMENTATION.md](docs/DOCUMENTATION.md) | Full API documentation & architecture |
| [V13_AUDIT_REPORT.md](docs/V13_AUDIT_REPORT.md) | Test coverage & certification report |
| [V13_WALKTHROUGH.md](docs/V13_WALKTHROUGH.md) | Feature walkthrough with code examples |
| [TEST_AUDIT.md](docs/TEST_AUDIT.md) | Test suite analysis & benchmarks |

---

## �📝 License

MIT License - See [LICENSE](LICENSE)

---

<p align="center">
  Built with ❤️ by <a href="https://github.com/chande-dhanush">Dhanush</a>
</p>
