# 🌸 Sakura V10

> An intelligent AI assistant with voice, vision, and tool-use capabilities.

![Sakura V10](https://img.shields.io/badge/version-10.0-pink?style=for-the-badge)
![Tauri](https://img.shields.io/badge/Tauri-2.x-blue?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11+-green?style=for-the-badge)

## ✨ Features

- **💬 Smart Chat** - Powered by Groq LLMs with tiered architecture
- **🔧 Tool Use** - 47+ tools (Spotify, Gmail, Calendar, Web Search, Notes, etc.)
- **🎙️ Voice** - Wake word detection + TTS with Kokoro
- **🖼️ Vision** - Image analysis via OpenRouter
- **🌐 Quick Search** - `Alt+S` for instant omnibox-style search
- **📍 Bubble Widget** - Always-on floating widget

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

### Manual Setup (All Platforms)
```bash
# 1. Clone repo
git clone https://github.com/your-username/sakura-v10.git
cd sakura-v10

# 2. Create Python venv
python -m venv PA
.\PA\Scripts\activate   # Windows
source PA/bin/activate  # Mac/Linux

# 3. Install dependencies
cd backend
pip install -r requirements.txt
cd ../frontend
npm install
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

### Google OAuth Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create OAuth 2.0 Client ID (Desktop App)
3. Download JSON → rename to `credentials.json`
4. Place in `backend/` folder
5. Run `python first_setup.py`

### Wake Word Setup
The setup wizard will guide you to record 3-5 voice samples saying "Sakura".
Templates are saved to `backend/data/wake_templates/`.

---

## 🔐 API Keys

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

```bash
cd frontend
npm run tauri build
```

Output: `frontend/src-tauri/target/release/bundle/nsis/Sakura_10.0.0_x64-setup.exe`

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| "No module named..." | Activate venv: `.\PA\Scripts\activate` |
| Wake word not working | Run `python first_setup.py` to record templates |
| Gmail/Calendar errors | Run `python first_setup.py` for OAuth |
| Bubble not visible | Press `Alt+M` to unhide |

---

## 📝 License

MIT License - See [LICENSE](LICENSE)

---

Built with ❤️ by Dhanush
