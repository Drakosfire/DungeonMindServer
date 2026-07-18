"""Isolated FastAPI app factory for focused v1 tests.

Tests must import from this module (or construct an equivalent app) rather than
importing the production ``app`` module.

Focused lane (does not load ``tests/conftest.py``, which imports production ``app``):

    uv run pytest --confcutdir=tests/statblocks_v1 tests/statblocks_v1 -q
"""

from __future__ import annotations

from fastapi import FastAPI

from statblocks_v1.api.http_errors import register_error_handlers
from statblocks_v1.api.router import router


def create_test_app() -> FastAPI:
    """Return a FastAPI app that mounts only the statblock v1 router."""
    app = FastAPI(title="statblocks_v1-test")
    register_error_handlers(app)
    app.include_router(router)
    return app
