#!/bin/bash
# Sakura V13 - Linux/Mac Setup Script
# Run from project root: ./scripts/setup.sh

set -e

# Get project root (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo -e "\033[35m🌸 Sakura V13 Setup Script\033[0m"
echo -e "\033[35m==========================\033[0m"
echo -e "\033[36mProject Root: $PROJECT_ROOT\033[0m"

# 1. Check OS
OS="$(uname -s)"
echo -e "\n\033[36m💻 Detected OS: $OS\033[0m"

# 2. Install System Deps
echo -e "\n\033[36m📦 Checking System Dependencies...\033[0m"
if [ "$OS" = "Linux" ]; then
    if command -v apt-get &> /dev/null; then
        echo "   Installing libs via apt-get (requires sudo)..."
        sudo apt-get update
        sudo apt-get install -y python3 python3-venv python3-pip nodejs npm \
                              build-essential libportaudio2 libsndfile1 flac ffmpeg tesseract-ocr curl
    else
        echo "   ⚠️  Not Debian/Ubuntu. Please manually install: python3, nodejs, portaudio, tesseract, ffmpeg"
    fi
elif [ "$OS" = "Darwin" ]; then
    if command -v brew &> /dev/null; then
        echo "   Installing libs via Homebrew..."
        brew install python node portaudio libsndfile flac ffmpeg tesseract
    else
        echo "   ❌ Homebrew not found. Please install dependencies manually."
        exit 1
    fi
fi

# 3. Create Venv
echo -e "\n\033[36m🐍 Setting up Python virtual environment...\033[0m"
if [ ! -d "$PROJECT_ROOT/PA" ]; then
    python3 -m venv "$PROJECT_ROOT/PA"
    echo -e "   ✅ Created venv at $PROJECT_ROOT/PA"
else
    echo -e "   ✅ Venv already exists"
fi

# 4. Install Python Deps
echo -e "\n\033[36m📥 Installing Python dependencies...\033[0m"
source "$PROJECT_ROOT/PA/bin/activate"
pip install --upgrade pip
pip install -r "$PROJECT_ROOT/backend/requirements.txt"

# 5. Frontend Deps
echo -e "\n\033[36m📥 Installing Frontend dependencies...\033[0m"
cd "$PROJECT_ROOT/frontend"
npm install
cd "$PROJECT_ROOT"

# 6. Env File
echo -e "\n\033[36m🔐 Checking .env file...\033[0m"
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    echo -e "   ⚠️  Created .env from template. Please add your API keys!"
else
    echo -e "   ✅ .env exists"
fi

echo -e "\n\033[32m🎉 Setup Complete!\033[0m"
echo -e "\033[32m==================\033[0m"
echo -e "\033[36mTo run Sakura:\033[0m"
echo "  cd frontend"
echo "  npm run tauri dev"
