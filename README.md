# 🌸 Sakura V10.4

> A production-grade personal AI assistant with voice, vision, and 46 tools.

![Version](https://img.shields.io/badge/version-10.4-pink?style=for-the-badge)
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
- 🎙️ Respond to voice commands ("Hey Sakura")
- 🖼️ Analyze images and screenshots
- 🧠 Remember context across conversations

**Free to run** — Uses Groq (Llama 3.3 70B) and Google Gemini free tiers.

---

## 🚀 Quick Start (5 Minutes)

### Prerequisites

| Requirement | How to Install |
|-------------|----------------|
| Python 3.11+ | [python.org/downloads](https://www.python.org/downloads/) |
| Node.js 18+ | [nodejs.org](https://nodejs.org/) |
| Rust | [rustup.rs](https://rustup.rs/) |
| Groq API Key | [console.groq.com](https://console.groq.com) (Free) |

### Windows Setup

```powershell
# 1. Clone the repo
git clone https://github.com/chande-dhanush/Sakura_V_9.1.git
cd Sakura_V_9.1

# 2. Run automated setup (as Administrator)
.\setup.ps1

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
git clone https://github.com/chande-dhanush/Sakura_V_9.1.git
cd Sakura_V_9.1

# 2. Run automated setup
chmod +x setup.sh
./setup.sh

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
Sakura_V_9.1/
├── frontend/           # Tauri + Svelte UI
│   ├── src/            # Svelte components
│   └── src-tauri/      # Rust window manager
├── backend/            # FastAPI + LangChain
│   ├── server.py       # Main API server
│   ├── sakura_assistant/
│   │   ├── core/       # Router, Executor, Planner
│   │   ├── tools/      # 46 tool implementations
│   │   └── utils/      # Flight recorder, metrics
│   └── data/           # World graph, templates
└── docs/               # Documentation
```

---

## 🏗️ Building for Production

```bash
cd frontend
npm run tauri build
```

**Output:** `frontend/src-tauri/target/release/bundle/nsis/Sakura_10.4.0_x64-setup.exe`

This creates a single installer that bundles:
- Compiled Python backend (PyInstaller)
- Tauri desktop shell
- All dependencies

---

## 🆕 What's New in V10.4

| Feature | Description |
|---------|-------------|
| **Flight Recorder** | JSONL tracing for debugging latency |
| **Few-Shot Router** | 15 examples for 90%+ routing accuracy |
| **Async LLM** | Native ainvoke() for parallel tool execution |
| **Rate Limiter** | Token bucket backpressure (no 429 crashes) |
| **Audit Suite** | Behavioral verification scripts |

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| "No module named..." | Activate venv: `.\PA\Scripts\activate` |
| Wake word not working | Run `python first_setup.py` |
| Gmail/Calendar errors | Check `credentials.json` placement |
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

## 📝 License

MIT License - See [LICENSE](LICENSE)

---

<p align="center">
  Built with ❤️ by <a href="https://github.com/chande-dhanush">Dhanush</a>
</p>
