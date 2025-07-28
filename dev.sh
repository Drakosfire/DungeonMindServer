#!/bin/bash

# Development server startup script for DungeonMindServer

echo "🐍 Activating virtual environment..."
source .venv/bin/activate

echo "🚀 Starting DungeonMindServer in development mode..."
echo "📁 Hot reload enabled - server will restart when files change"
echo ""

# Run the development server
python dev_server.py 