#!/usr/bin/env bash
# Project-independent focused lane for statblocks_v1.
#
# Uses an ephemeral env (``--isolated --no-project``) so the project ``.venv``
# and full server graph (OpenAI, Firebase, Firestore, Fal, sentence-transformers,
# generationengine) are never required.
#
# Usage (from repository root):
#   ./scripts/run_statblocks_v1_tests.sh
#   ./scripts/run_statblocks_v1_tests.sh -k health
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

exec uv run --isolated --no-project \
  --with 'pytest>=8.3.5' \
  --with 'fastapi>=0.115.4' \
  --with 'pydantic>=2.0' \
  --with 'httpx>=0.27.0' \
  pytest --confcutdir=tests/statblocks_v1 tests/statblocks_v1 -q "$@"
