#!/usr/bin/env python3
"""
Download BAAI/bge-m3 model to the expected location for Docker volume mounting.

Usage:
    python3 download_model.py

This will download the model to: DungeonMindServer/models--BAAI--bge-m3/
"""

import os
from pathlib import Path
from huggingface_hub import snapshot_download

def main():
    # Get the directory where this script is located (DungeonMindServer/)
    script_dir = Path(__file__).parent
    model_dir = script_dir / "models--BAAI--bge-m3"
    
    print(f"📥 Downloading BAAI/bge-m3 model...")
    print(f"📍 Target directory: {model_dir}")
    print(f"⏳ This may take several minutes (model is ~2.3GB)...")
    
    try:
        snapshot_download(
            repo_id="BAAI/bge-m3",
            local_dir=str(model_dir),
            local_dir_use_symlinks=False,  # Use actual files, not symlinks
            resume_download=True  # Resume if interrupted
        )
        print(f"✅ Model downloaded successfully to: {model_dir}")
        print(f"📊 Directory size: {get_dir_size(model_dir) / (1024**3):.2f} GB")
    except Exception as e:
        print(f"❌ Error downloading model: {e}")
        return 1
    
    return 0

def get_dir_size(path):
    """Calculate total size of directory in bytes"""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total += os.path.getsize(filepath)
    return total

if __name__ == "__main__":
    exit(main())

