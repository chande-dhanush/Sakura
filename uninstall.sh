#!/bin/bash
echo "🗑️  Uninstalling Sakura V10 Artifacts..."

rm -rf PA
rm -rf frontend/node_modules
rm -rf frontend/src-tauri/target
rm -rf backend/data

echo "⚠️  .env file preserved. Delete manually if needed."
echo "✅ Cleaned."
