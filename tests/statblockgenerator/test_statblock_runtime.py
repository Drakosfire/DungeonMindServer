"""Shared StatBlockGenerator factory unit coverage."""

from __future__ import annotations

from statblockgenerator import runtime


def test_get_statblock_generator_returns_singleton(monkeypatch):
    previous = runtime.get_statblock_generator()
    runtime.configure_statblock_generator(None)
    created: list[object] = []

    class FakeGenerator:
        def __init__(self) -> None:
            created.append(self)

    monkeypatch.setattr(
        "statblockgenerator.statblock_generator.StatBlockGenerator",
        FakeGenerator,
    )
    try:
        first = runtime.get_statblock_generator()
        second = runtime.get_statblock_generator()
        assert first is second
        assert len(created) == 1
    finally:
        runtime.configure_statblock_generator(previous)
