"""Legacy RuleElement.explains remains loadable for sealed revisions."""

from __future__ import annotations

from statblocks_v1.domain.rule_elements import ExplainsEdge, RuleElement


def test_rule_element_accepts_legacy_empty_explains() -> None:
    element = RuleElement.model_validate(
        {
            "key": "amphibious",
            "name": "Amphibious",
            "section": "trait",
            "rules_text": "Can breathe air and water.",
            "activation": {"kind": "passive"},
            "usage": {"kind": "at_will"},
            "mechanic": {"kind": "passive"},
            "automation_support": "full",
            "explains": [],
        }
    )
    assert element.explains == []


def test_rule_element_accepts_omitted_explains() -> None:
    element = RuleElement.model_validate(
        {
            "key": "amphibious",
            "name": "Amphibious",
            "section": "trait",
            "rules_text": "Can breathe air and water.",
            "activation": {"kind": "passive"},
            "usage": {"kind": "at_will"},
            "mechanic": {"kind": "passive"},
            "automation_support": "full",
        }
    )
    assert element.explains is None


def test_explains_edge_round_trip() -> None:
    edge = ExplainsEdge.model_validate(
        {"element_key": "bite", "note": "flavor only"}
    )
    assert edge.element_key == "bite"
    assert edge.note == "flavor only"
