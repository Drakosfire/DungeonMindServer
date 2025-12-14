"""
Backend Rule Engine for the Player Character Generator (PCG).

This is an intentionally small, PCG-local engine that:
- loads a "middle layer" catalog (JSON)
- produces GenerationConstraints for levels 1–3

Longer term: this becomes the learning path toward a shared DungeonMindEngine
driven by JSON rule configs.
"""

from .pcg_rule_engine import PCGRuleEngine


