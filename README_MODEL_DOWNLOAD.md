# Downloading BAAI/bge-m3 Model

The RulesLawyer service requires the `BAAI/bge-m3` embedding model. This model is **not** stored in the repository but must be downloaded separately.

## Quick Download (Recommended)

### Option 1: Python Script (Easiest)

```bash
cd DungeonMindServer
python3 download_model.py
```

This will download the model (~2.3GB) to `DungeonMindServer/models--BAAI--bge-m3/`

### Option 2: Using huggingface-cli

If you have `huggingface-cli` installed:

```bash
cd DungeonMindServer
huggingface-cli download BAAI/bge-m3 --local-dir models--BAAI--bge-m3
```

### Option 3: Python One-Liner

```bash
cd DungeonMindServer
python3 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='BAAI/bge-m3', local_dir='models--BAAI--bge-m3', local_dir_use_symlinks=False)"
```

## Expected Location

The model should be downloaded to:
```
DungeonMindServer/models--BAAI--bge-m3/
```

This directory is mounted into the Docker container at `/home/user/.cache/huggingface` (see `docker-compose.yml` line 21).

## Verification

After downloading, verify the model exists:

```bash
ls -lh DungeonMindServer/models--BAAI--bge-m3/
# Should show model files (config.json, pytorch_model.bin, etc.)
```

## Docker Usage

Once downloaded, the model will be available in the container via the volume mount:
- Host: `./DungeonMindServer/models--BAAI--bge-m3/`
- Container: `/home/user/.cache/huggingface`

The container's `TRANSFORMERS_CACHE` environment variable points to this location.

## Fixing Permissions (IMPORTANT)

After downloading, you **must** fix permissions so the Docker container (running as user 1000:1000) can access the files:

```bash
cd DungeonMindServer
sudo chown -R 1000:1000 models--BAAI--bge-m3/
sudo chmod -R 755 models--BAAI--bge-m3/
```

**Why?** The Docker container runs as user `1000:1000` (see `docker-compose.yml` line 6). If the model files are owned by a different user, the container won't be able to read/write them, causing permission errors.

## Troubleshooting

**Permission Error (PermissionError at /home/user/.cache/huggingface):**
```bash
# Fix ownership to match container user
sudo chown -R 1000:1000 DungeonMindServer/models--BAAI--bge-m3/
sudo chmod -R 755 DungeonMindServer/models--BAAI--bge-m3/

# Remove any lock files if download was interrupted
find DungeonMindServer/models--BAAI--bge-m3/ -name "*.lock" -delete

# Restart container
docker compose restart api-server
```

**If download fails:**
- Check internet connection
- Ensure you have ~3GB free disk space
- Try with `resume_download=True` if interrupted

**If model not found in container:**
- Verify the volume mount in `docker-compose.yml`
- Check that `TRANSFORMERS_CACHE=/home/user/.cache/huggingface` is set
- Verify permissions (see above)
- Restart the container after downloading

