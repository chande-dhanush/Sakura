#!/bin/bash
# Sakura V10 - Startup Manager (Linux)

APP_NAME="sakura_v10"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/$APP_NAME.desktop"
RUN_SCRIPT="$(pwd)/run_background.sh"

echo -e "\033[35m🌸 Sakura V10 - Autostart Configuration\033[0m"

# Ensure dir exists
mkdir -p "$AUTOSTART_DIR"

if [ -f "$DESKTOP_FILE" ]; then
    echo -e "\n\033[32m✅ Status: ENABLED (Starts on Login)\033[0m"
    read -p "Do you want to DISABLE autostart? (y/n): " choice
    if [[ "$choice" == "y" || "$choice" == "Y" ]]; then
        rm "$DESKTOP_FILE"
        echo -e "\033[33m🗑️  Removed from autostart.\033[0m"
    else
        echo "👍 Kept enabled."
    fi
else
    echo -e "\n\033[33m❌ Status: DISABLED (Manual Run Only)\033[0m"
    read -p "Do you want to ENABLE autostart? (y/n): " choice
    if [[ "$choice" == "y" || "$choice" == "Y" ]]; then
        cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Sakura V10
Exec=$RUN_SCRIPT
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Comment=Start Sakura AI Backend
EOF
        chmod +x "$RUN_SCRIPT"
        echo -e "\033[32m🚀 Added to autostart!\033[0m"
    else
        echo "👍 Kept disabled."
    fi
fi
