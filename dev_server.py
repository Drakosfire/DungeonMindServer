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
    print("")
    print("🌐 Server will be available at: http://localhost:7860")
    print("📊 Health check: http://localhost:7860/health")
    print("")
    print("Press Ctrl+C to stop the server")
    print("=" * 50)
    
    # Use uvicorn.run with import string for proper reload functionality
    uvicorn.run(
        "app:app",  # Import string format required for reload
        host="0.0.0.0",
        port=7860,
        reload=True,
        reload_dirs=[
            "routers",
            "cardgenerator", 
            "cloudflare",
            "cloudflareR2",
            "firestore",
            "ruleslawyer",
            "storegenerator",
            "sms"
        ],
        log_level="info"
    )

if __name__ == "__main__":
    main() 