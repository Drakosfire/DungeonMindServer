from dataclasses import dataclass
from typing import Any, Dict, List

from .catalogs.dnd5e_v0.catalog import BACKGROUNDS, CLASSES, RACES, SPELLS, SPELL_LISTS


@dataclass(frozen=True)
class Dnd5eCatalog:
    classes_by_id: Dict[str, Dict[str, Any]]
    races_by_id: Dict[str, Dict[str, Any]]
    backgrounds_by_id: Dict[str, Dict[str, Any]]
    spells_by_id: Dict[str, Dict[str, Any]]
    spell_lists_by_id: Dict[str, Dict[str, List[str]]]

def load_dnd5e_catalog_v0() -> Dnd5eCatalog:
    # NOTE:
    # DungeonMindServer/.cursorignore blocks *.json, so we keep the "middle-layer"
    # catalog as python data for now. The intended end-state is JSON-driven configs.
    classes_list: List[Dict[str, Any]] = CLASSES
    races_list: List[Dict[str, Any]] = RACES
    backgrounds_list: List[Dict[str, Any]] = BACKGROUNDS
    spells_list: List[Dict[str, Any]] = SPELLS
    spell_lists_by_id: Dict[str, Dict[str, List[str]]] = SPELL_LISTS

    classes_by_id = {c["id"]: c for c in classes_list}
    races_by_id = {r["id"]: r for r in races_list}
    backgrounds_by_id = {b["id"]: b for b in backgrounds_list}
    spells_by_id = {s["id"]: s for s in spells_list}

    return Dnd5eCatalog(
        classes_by_id=classes_by_id,
        races_by_id=races_by_id,
        backgrounds_by_id=backgrounds_by_id,
        spells_by_id=spells_by_id,
        spell_lists_by_id=spell_lists_by_id,
    )


