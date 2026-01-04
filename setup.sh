#!/bin/bash
# Sakura V10 - Linux/Mac Setup Script
# Usage: ./setup.sh

set -e

echo -e "\033[35m🌸 Sakura V10 Setup Script\033[0m"
echo -e "\033[35m=========================\033[0m"

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
if [ ! -d "PA" ]; then
    python3 -m venv PA
    echo -e "   ✅ Created venv at ./PA"
else
    echo -e "   ✅ Venv already exists"
fi

# 4. Install Python Deps
echo -e "\n\033[36m📥 Installing Python dependencies...\033[0m"
source PA/bin/activate
pip install --upgrade pip
# Use the cross-platform requirements file
pip install -r backend/requirements.txt

# 5. Frontend Deps
echo -e "\n\033[36m📥 Installing Frontend dependencies...\033[0m"
cd frontend
npm install
cd ..

# 6. Env File
echo -e "\n\033[36m🔐 Checking .env file...\033[0m"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "   ⚠️  Created .env from template. Please add your API keys!"
else
    echo -e "   ✅ .env exists"
fi

echo -e "\n\033[32m🎉 Setup Complete!\033[0m"
echo -e "\033[32m==================\033[0m"
echo -e "\033[36mTo run Sakura:\033[0m"
echo "  cd frontend"
echo "  npm run tauri dev"

# 7. Startup Prompt
echo -e "\n\033[36m⚙️  Configuration\033[0m"
if [ -f "toggle_startup.sh" ]; then
    chmod +x toggle_startup.sh
    ./toggle_startup.sh
fi

