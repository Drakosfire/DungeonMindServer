"""Isolated FastAPI app factory for focused v1 tests.

Tests must import from this module (or construct an equivalent app) rather than
importing the production ``app`` module.
"""

from __future__ import annotations

from fastapi import FastAPI

from statblocks_v1.api.router import router


def create_test_app() -> FastAPI:
    """Return a FastAPI app that mounts only the statblock v1 router."""
    app = FastAPI(title="statblocks_v1-test")
    app.include_router(router)
    return app
