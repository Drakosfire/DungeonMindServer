"""Isolated FastAPI app factory for focused v1 tests.

Tests must import from this module (or construct an equivalent app) rather than
importing the production ``app`` module.

Focused lane (import-isolated via ``--confcutdir`` and dependency-isolated via
``uv run --isolated --no-project`` — does not use ``.venv`` or sync the full
server environment):

    ./scripts/run_statblocks_v1_tests.sh

Equivalent:

    PYTHONPATH=. uv run --isolated --no-project \\
      --with 'pytest>=8.3.5' --with 'fastapi>=0.115.4' \\
      --with 'pydantic==2.7.4' --with 'httpx>=0.27.0' \\
      pytest --confcutdir=tests/statblocks_v1 tests/statblocks_v1 -q
"""

from __future__ import annotations

from fastapi import FastAPI

from statblocks_v1.api.http_errors import register_error_handlers
from statblocks_v1.api.router import router


def create_contract_app() -> FastAPI:
    """Return the authoritative, isolated v1 contract application."""
    app = FastAPI(
        title="DungeonBuddy Statblocks v1",
        version="1.0.0",
        description="DungeonMindServer-owned DungeonBuddy statblock contract.",
    )
    register_error_handlers(app)
    app.include_router(router)
    return app


def create_test_app() -> FastAPI:
    """Return an isolated v1 app for focused tests."""
    return create_contract_app()
