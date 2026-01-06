# 🌸 Sakura V10

> An intelligent AI assistant with voice, vision, and tool-use capabilities.

![Sakura V10](https://img.shields.io/badge/version-10.0-pink?style=for-the-badge)
![Tauri](https://img.shields.io/badge/Tauri-2.x-blue?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11+-green?style=for-the-badge)

## ✨ Features

- **💬 Smart Chat** - Powered by Groq LLMs with tiered architecture
- **🔧 Tool Use** - 47+ tools (Spotify, Gmail, Calendar, Web Search, Notes, etc.)
- **🛡️ Enterprise Security** - Simple Auth, Path Sandboxing, Safe Math Parsing
- **🎙️ Voice** - Wake word detection + TTS with Kokoro + Real-time UI Sync
- **🧠 Emotional Intelligence** - World Graph memory with mood/intent tracking
- **🖼️ Vision** - Image analysis via OpenRouter
- **📊 Observability** - Structured logging & Prometheus metrics
- **🌐 Quick Search** - `Alt+S` for instant omnibox-style search
- **📍 Bubble Widget** - Always-on floating widget
- **📎 File Upload** - Attach PDFs, docs, images for RAG ingestion (V10.1)

### 🆕 V10.1 Updates (January 2026)
- **Terminal Action Deduplication** - Prevents LLM from calling same tool 5x
- **Window Auto-Show** - Main window now shows automatically after backend ready
- **Settings UI Fix** - Save button now visible with proper scrolling
- **Layout Stability** - Fixed app window expanding with message content

---

## 🚀 Installation

### Prerequisites
- **Python 3.11+** - [Download](https://www.python.org/downloads/)
- **Node.js 18+** - [Download](https://nodejs.org/)
- **Rust** - [Install via rustup](https://rustup.rs/)

### Quick Start (Windows)
```powershell
# 1. Clone and enter directory
git clone https://github.com/your-username/sakura-v10.git
cd sakura-v10

# 2. Run automated setup (as Administrator)
.\setup.ps1

# 3. Configure API keys
notepad .env

# 4. First-time setup (Google Auth + Voice)
cd backend
..\PA\Scripts\python first_setup.py

# 5. Launch the app
cd ..\frontend
npm run tauri dev
```

### 👤 Customization
You can make Sakura your own! To change the user profile (Name, Role, Interests) or the Assistant's Personality:

1.  Open `backend/sakura_assistant/config.py`.
2.  Edit the `USER_DETAILS` block to reflect **YOU**.
3.  Edit the `SYSTEM_PERSONALITY` block to change how Sakura talks.
4.  Restart the backend server for changes to take effect.

### Manual Setup (All Platforms)
```bash
# 1. Clone repo
git clone https://github.com/your-username/sakura-v10.git
cd sakura-v10

# 2. Create Python venv
python -m venv PA
.\PA\Scripts\activate   # Windows
source PA/bin/activate  ### ⚡ Automated Setup

**Windows**:
```powershell
.\setup.ps1
```

**Linux / macOS**:
```bash
chmod +x setup.sh
./setup.sh
```

This script will:
1.  Install Python & Node.js (if missing).
2.  Install System Audio/OCR libraries (ffmpeg, portaudio, tesseract).
3.  Create a virtual environment (`PA/`).
4.  Install all dependencies.
cd ..

# 4. Configure API keys
cp .env.example .env
# Edit .env with your keys

# 5. First-time setup (Google Auth + Voice)
cd backend
python first_setup.py

# 6. Run
cd ../frontend
npm run tauri dev
```

---

## 🔧 First-Time Setup (Important!)

After installation, run the setup wizard:
```bash
cd backend
python first_setup.py
```

This configures:
1. **Google OAuth** - For Gmail/Calendar access
2. **Wake Word Templates** - Records your voice for "Sakura" activation

### Google OAuth Setup (Optional)
> **Note:** Google integration (Gmail, Calendar, Tasks) is **optional**. The app works perfectly without it.

To enable Gmail/Calendar/Tasks:
1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new project (or use existing)
3. Enable these APIs: `Gmail API`, `Google Calendar API`, `Tasks API`
4. Go to **OAuth consent screen** → Configure as "External" → Add your email as test user
5. Go to **Credentials** → Create **OAuth 2.0 Client ID** → Select "Desktop App"
6. Download the JSON file → Rename to `credentials.json`
7. Place it in `backend/` folder (or `%APPDATA%/SakuraV10/` for installed version)
8. Run the app → First Gmail/Calendar request will open browser for authorization
9. After authentication, `token.json` is created and you're set!

**Troubleshooting:**
- "Access blocked" → Add your Google account as a test user in OAuth consent screen
- "credentials.json not found" → Make sure the file is in the correct directory

### Wake Word Setup
The setup wizard guides you to record 3-5 voice samples saying "Sakura".
Templates are saved to `data/wake_templates/` in your app data folder.

---

## 🔐 API Keys & Security

### Authentication
Sakura V10 now enforces simple authentication for the API.
1. Open `backend/server.py` and set your credentials (default: `sakura / sakura123`).
2. The frontend automatically handles headers.

### Environment Variables
Create `.env` in the project root:

```env
# REQUIRED
GROQ_API_KEY=gsk_your_key_here        # https://console.groq.com

# OPTIONAL
OPENROUTER_API_KEY=sk-or-your_key     # Vision (https://openrouter.ai)
TAVILY_API_KEY=tvly-your_key          # Web search (https://tavily.com)
SPOTIFY_CLIENT_ID=your_client_id      # Spotify
SPOTIFY_CLIENT_SECRET=your_secret     # Spotify
```

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Alt+S` | Toggle Quick Search |
| `Alt+F` | Force Full Window Mode |
| `Alt+M` | Hide Mode (for movies) |
| `Escape` | Stop AI generation |

---

## 📦 Optional Dependencies

| Feature | Install |
|---------|---------|
| Screen Reading | `winget install UB-Mannheim.TesseractOCR` |
| Voice Input | ✅ Included |
| Voice Output | ✅ Included |

---

## 🛠️ Building for Production

### One Command Build (Frontend + Backend)
```bash
cd frontend
npm run tauri build
```

This **automatically**:
1. Compiles the Python backend with PyInstaller
2. Bundles it as a Tauri sidecar
3. Builds the complete installer

**Output:** `frontend/src-tauri/target/release/bundle/nsis/Sakura_10.0.0_x64-setup.exe`

### Development Mode
```bash
cd frontend
npm run tauri dev
```
Uses your local Python + venv (no PyInstaller needed).

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| "No module named..." | Activate venv: `.\PA\Scripts\activate` |
| Wake word not working | Run `python first_setup.py` to record templates |
| Gmail/Calendar errors | Run `python first_setup.py` for OAuth |
| Bubble not visible | Press `Alt+M` to unhide |

---

## 👻 Run in Background
- **Windows**: Double-click `run_background.vbs`. (Hidden window)
- **Linux/Mac**: `./run_background.sh`

## 🗑️ Uninstall
Removes all data, virtual environments, and dependencies.
- **Windows**: `.\uninstall.ps1`
- **Linux/Mac**: `./uninstall.sh`

## ⚙️ Startup Manager
Want to change your mind about autostart later?
- **Windows**: `.\toggle_startup.ps1`
- **Linux/Mac**: `./toggle_startup.sh`

## 📝 License

MIT License - See [LICENSE](LICENSE)

---

Built with ❤️ by Dhanush
