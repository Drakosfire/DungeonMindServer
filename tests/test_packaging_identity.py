"""Regression guard for E1A distribution identity."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_distribution_name_is_dungeonmind_web_api() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "dungeonmind-web-api"' in pyproject
    assert 'name = "dungeonmind"' not in pyproject


def test_editable_install_exposes_dungeonmind_web_api_distribution() -> None:
    metadata = importlib.metadata.metadata("dungeonmind-web-api")
    assert metadata["Name"] == "dungeonmind-web-api"
    assert metadata["Version"] == "0.2.0"
