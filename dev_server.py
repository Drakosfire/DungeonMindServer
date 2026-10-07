#!/usr/bin/env python3
"""
Development server script for DungeonMindServer.
This script sets the environment to development and enables hot reloading.
"""

import os
import sys
import uvicorn
from pathlib import Path

# Set environment to development
os.environ['ENVIRONMENT'] = 'development'

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Main function for running the development server."""
    raw_port = os.environ.get("DUNGEONMIND_SERVER_PORT", "7860")
    try:
        port = int(raw_port)
    except ValueError:
        raise SystemExit("DUNGEONMIND_SERVER_PORT must be an integer between 1 and 65535") from None
    if not 1 <= port <= 65535:
        raise SystemExit("DUNGEONMIND_SERVER_PORT must be an integer between 1 and 65535")

    print("🚀 Starting DungeonMindServer in development mode with hot reload...")
    print("📁 Watching directories for changes:")
    print("   - routers/")
    print("   - cardgenerator/")
    print("   - cloudflare/")
    print("   - cloudflareR2/")
    print("   - firestore/")
    print("   - ruleslawyer/")
    print("   - storegenerator/")
    print("   - sms/")
    print("   - mapgenerator/")
    print("")
    print(f"🌐 Server will be available at: http://localhost:{port}")
    print(f"📊 Health check: http://localhost:{port}/health")
    print("")
    print("Press Ctrl+C to stop the server")
    print("=" * 50)
    
    # Use uvicorn.run with import string for proper reload functionality
    uvicorn.run(
        "app:app",  # Import string format required for reload
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_dirs=[
            "routers",
            "cardgenerator", 
            "cloudflare",
            "cloudflareR2",
            "firestore",
            "ruleslawyer",
            "storegenerator",
            "sms",
            "mapgenerator"
        ],
        log_level="info"
    )

if __name__ == "__main__":
    main() 