#!/bin/bash
source PA/bin/activate
nohup python backend/server.py > backend/server.log 2>&1 &
echo "🚀 Sakura Backend running in background (PID $!)"
echo "📜 Logs: backend/server.log"
