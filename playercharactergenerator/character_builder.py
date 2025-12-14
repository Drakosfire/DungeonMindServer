"""
PCG Character Builder (Phase 5.1)

Builds a frontend-compatible `Character` wrapper (LandingPage types/character.types.ts)
containing a `dnd5eData` payload (types/dnd5e/character.types.ts).

This module intentionally uses the limited v0 backend catalogs/constraints and
fills missing SRD-rich fields with safe defaults so the frontend can hydrate/render.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from playercharactergenerator.models.pcg_models import AiPreferences, DerivedStats, GenerationConstraints, GenerationInput, ValidationChoices


def _iso_now() -> str:
    return datetime.now().isoformat()


def _ability_mod(score: int) -> int:
    return (int(score) - 10) // 2


def _race_defaults(race_id: str) -> Tuple[int, str, str]:
    """
    Returns (walk_speed, size, base_race_guess).

    Backend v0 catalog does not yet contain full SRD race data.
    """
    rid = (race_id or "").lower().strip()
    if rid in {"dwarf", "hill-dwarf", "mountain-dwarf", "halfling", "lightfoot-halfling", "stout-halfling"}:
        return 25, "medium" if "dwarf" in rid else "small", "dwarf" if "dwarf" in rid else "halfling"
    if rid in {"gnome"}:
        return 25, "small", "gnome"
    return 30, "medium", rid


def _race_ability_bonuses_list(ability_bonuses: Dict[str, int]) -> List[Dict[str, Any]]:
    bonuses: List[Dict[str, Any]] = []
    for ability, bonus in (ability_bonuses or {}).items():
        if not bonus:
            continue
        bonuses.append({"ability": ability, "bonus": int(bonus)})
    return bonuses


_WEAPON_CATALOG: Dict[str, Dict[str, Any]] = {
    # Martial melee
    "longsword": {
        "id": "longsword",
        "name": "Longsword",
        "type": "weapon",
        "weaponCategory": "martial",
        "weaponType": "melee",
        "damage": "1d8",
        "damageType": "slashing",
        "properties": ["versatile"],
    },
    "rapier": {
        "id": "rapier",
        "name": "Rapier",
        "type": "weapon",
        "weaponCategory": "martial",
        "weaponType": "melee",
        "damage": "1d8",
        "damageType": "piercing",
        "properties": ["finesse"],
    },
    "shortsword": {
        "id": "shortsword",
        "name": "Shortsword",
        "type": "weapon",
        "weaponCategory": "martial",
        "weaponType": "melee",
        "damage": "1d6",
        "damageType": "piercing",
        "properties": ["finesse", "light"],
    },
    # Simple melee
    "dagger": {
        "id": "dagger",
        "name": "Dagger",
        "type": "weapon",
        "weaponCategory": "simple",
        "weaponType": "melee",
        "damage": "1d4",
        "damageType": "piercing",
        "properties": ["finesse", "light", "thrown"],
        "range": {"normal": 20, "long": 60},
    },
    "quarterstaff": {
        "id": "quarterstaff",
        "name": "Quarterstaff",
        "type": "weapon",
        "weaponCategory": "simple",
        "weaponType": "melee",
        "damage": "1d6",
        "damageType": "bludgeoning",
        "properties": ["versatile"],
    },
    "mace": {
        "id": "mace",
        "name": "Mace",
        "type": "weapon",
        "weaponCategory": "simple",
        "weaponType": "melee",
        "damage": "1d6",
        "damageType": "bludgeoning",
        "properties": [],
    },
    # Ranged
    "longbow": {
        "id": "longbow",
        "name": "Longbow",
        "type": "weapon",
        "weaponCategory": "martial",
        "weaponType": "ranged",
        "damage": "1d8",
        "damageType": "piercing",
        "properties": ["ammunition", "heavy", "two-handed"],
        "range": {"normal": 150, "long": 600},
    },
    "shortbow": {
        "id": "shortbow",
        "name": "Shortbow",
        "type": "weapon",
        "weaponCategory": "simple",
        "weaponType": "ranged",
        "damage": "1d6",
        "damageType": "piercing",
        "properties": ["ammunition", "two-handed"],
        "range": {"normal": 80, "long": 320},
    },
    "light-crossbow": {
        "id": "light-crossbow",
        "name": "Light Crossbow",
        "type": "weapon",
        "weaponCategory": "simple",
        "weaponType": "ranged",
        "damage": "1d8",
        "damageType": "piercing",
        "properties": ["ammunition", "loading", "two-handed"],
        "range": {"normal": 80, "long": 320},
    },
}

_EQUIPMENT_CATALOG: Dict[str, Dict[str, Any]] = {
    "component-pouch": {"id": "component-pouch", "name": "Component Pouch", "type": "adventuring gear"},
    "arcane-focus": {"id": "arcane-focus", "name": "Arcane Focus", "type": "adventuring gear"},
    "explorers-pack": {"id": "explorers-pack", "name": "Explorer's Pack", "type": "adventuring gear"},
    "scholars-pack": {"id": "scholars-pack", "name": "Scholar's Pack", "type": "adventuring gear"},
    "burglars-pack": {"id": "burglars-pack", "name": "Burglar's Pack", "type": "adventuring gear"},
    "entertainers-pack": {"id": "entertainers-pack", "name": "Entertainer's Pack", "type": "adventuring gear"},
    "diplomats-pack": {"id": "diplomats-pack", "name": "Diplomat's Pack", "type": "adventuring gear"},
    "thieves-tools": {"id": "thieves-tools", "name": "Thieves' Tools", "type": "tool"},
    "lute": {"id": "lute", "name": "Lute", "type": "musical instrument"},
    "flute": {"id": "flute", "name": "Flute", "type": "musical instrument"},
}


def _default_weapon_for_choice(*, class_id: str, choice_id: str) -> str:
    """
    Resolve placeholder equipment item IDs into an actual weapon ID.
    """
    cid = (class_id or "").lower().strip()
    if choice_id == "martial-weapon-choice":
        # Reasonable defaults per fantasy archetype
        if cid in {"rogue", "bard"}:
            return "rapier"
        return "longsword"
    if choice_id == "simple-weapon-choice":
        if cid in {"wizard"}:
            return "quarterstaff"
        return "mace"
    # Unknown choice placeholder; fall back to dagger
    return "dagger"


def _build_equipment_payload(
    *,
    input_data: GenerationInput,
    constraints: GenerationConstraints,
    choices: ValidationChoices,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Optional[Dict[str, Any]], bool]:
    """
    Returns (equipment_items, weapon_items, feature_list, armor, shield).
    - equipment_items: DnD5eEquipmentItem dicts (non-weapons, non-armor)
    - weapon_items: DnD5eWeapon dicts
    - feature_list: DnD5eFeature dicts related to equipment choices (currently empty; reserved)
    """
    armor: Optional[Dict[str, Any]] = None
    shield = False

    packages = (constraints.equipment or {}).get("packages", []) or []
    pkg = next((p for p in packages if p.id == choices.equipment_package_id), None)
    raw_items = list(getattr(pkg, "items", []) or []) if pkg else []

    # Expand choice placeholders
    expanded_items: List[str] = []
    for item_id in raw_items:
        if item_id in {"martial-weapon-choice", "simple-weapon-choice"}:
            expanded_items.append(_default_weapon_for_choice(class_id=input_data.class_id, choice_id=item_id))
        else:
            expanded_items.append(item_id)

    if "shield" in expanded_items:
        shield = True

    # Armor inference (kept consistent with compute rules)
    if "chain-mail" in expanded_items:
        armor = {
            "id": "chain-mail",
            "name": "Chain Mail",
            "type": "armor",
            "quantity": 1,
            "armorCategory": "heavy",
            "armorClass": 16,
            "addDexMod": False,
            "maxDexBonus": 0,
            "stealthDisadvantage": True,
        }
    elif "scale-mail" in expanded_items:
        armor = {
            "id": "scale-mail",
            "name": "Scale Mail",
            "type": "armor",
            "quantity": 1,
            "armorCategory": "medium",
            "armorClass": 14,
            "addDexMod": True,
            "maxDexBonus": 2,
            "stealthDisadvantage": True,
        }
    elif "leather-armor" in expanded_items:
        armor = {
            "id": "leather-armor",
            "name": "Leather Armor",
            "type": "armor",
            "quantity": 1,
            "armorCategory": "light",
            "armorClass": 11,
            "addDexMod": True,
        }

    weapons: List[Dict[str, Any]] = []
    equipment: List[Dict[str, Any]] = []

    def _add_equipment(item: Dict[str, Any], qty: int = 1) -> None:
        merged = dict(item)
        merged["quantity"] = int(qty)
        equipment.append(merged)

    def _add_weapon(item: Dict[str, Any], qty: int = 1) -> None:
        merged = dict(item)
        merged["quantity"] = int(qty)
        weapons.append(merged)

    for item_id in expanded_items:
        if item_id in {"chain-mail", "scale-mail", "leather-armor", "shield"}:
            # Already captured by armor/shield flags; keep shield as boolean for now.
            continue

        # Ammo stack items
        if item_id == "arrows-20":
            _add_equipment({"id": "arrows", "name": "Arrows", "type": "consumable"}, qty=20)
            continue
        if item_id == "bolts-20":
            _add_equipment({"id": "crossbow-bolts", "name": "Crossbow Bolts", "type": "consumable"}, qty=20)
            continue

        weapon_def = _WEAPON_CATALOG.get(item_id)
        if weapon_def:
            _add_weapon(weapon_def, qty=1)
            continue

        eq_def = _EQUIPMENT_CATALOG.get(item_id)
        if eq_def:
            _add_equipment(eq_def, qty=1)
            continue

        # Unknown item: keep it visible to the user rather than dropping it.
        _add_equipment(
            {
                "id": item_id,
                "name": item_id.replace("-", " ").title(),
                "type": "other",
            },
            qty=1,
        )

    return equipment, weapons, [], armor, shield


def _basic_feature_list(
    *,
    input_data: GenerationInput,
    constraints: GenerationConstraints,
    choices: ValidationChoices,
    spellcasting_payload: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Minimal but useful features list for sheet rendering.

    IMPORTANT: This is intentionally "v0" — not full SRD fidelity yet.
    """
    features: List[Dict[str, Any]] = []
    level = int(input_data.level)
    class_id = (input_data.class_id or "").lower().strip()
    class_name = constraints.class_info.name

    def _add_feature(
        *,
        fid: str,
        name: str,
        description: str,
        source: str = "class",
        source_details: Optional[str] = None,
        limited_use: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "id": fid,
            "name": name,
            "description": description,
            "source": source,
        }
        if source_details:
            payload["sourceDetails"] = source_details
        if limited_use:
            payload["limitedUse"] = limited_use
        features.append(payload)

    # Surface any explicit feature choices (with option description if available)
    for choice_key, option_id in (choices.feature_choices or {}).items():
        # Find matching feature choice in constraints
        matched = None
        for fc in (constraints.feature_choices or []):
            if getattr(fc, "feature_id", None) == choice_key:
                matched = fc
                break
            # Some keys are stored as the featureId in the catalog, so compare that too.
            if getattr(fc, "feature_id", None) and str(getattr(fc, "feature_id")) == choice_key:
                matched = fc
                break

        option_desc = "Chosen feature option (generated)."
        option_name = option_id.replace("-", " ").title()
        if matched:
            for opt in (matched.options or []):
                if getattr(opt, "id", None) == option_id:
                    option_name = getattr(opt, "name", option_name)
                    option_desc = getattr(opt, "description", option_desc)
                    break

        _add_feature(
            fid=f"{choice_key}:{option_id}",
            name=option_name,
            description=option_desc,
            source="class",
            source_details=f"{class_name} Level {level}",
        )

    # Class baseline features (tiny curated set)
    if class_id == "fighter":
        if level >= 1:
            _add_feature(
                fid="fighter:second-wind",
                name="Second Wind",
                description="You have a limited well of stamina that you can draw on to protect yourself from harm.",
                source_details="Fighter Level 1",
                limited_use={"maxUses": 1, "currentUses": 1, "resetOn": "short"},
            )
        if level >= 2:
            _add_feature(
                fid="fighter:action-surge",
                name="Action Surge",
                description="You can push yourself beyond your normal limits for a moment, taking one additional action on your turn.",
                source_details="Fighter Level 2",
                limited_use={"maxUses": 1, "currentUses": 1, "resetOn": "short"},
            )
    elif class_id == "rogue":
        if level >= 1:
            _add_feature(
                fid="rogue:sneak-attack",
                name="Sneak Attack",
                description="You know how to strike subtly and exploit a foe's distraction for extra damage once per turn.",
                source_details="Rogue Level 1",
            )
            _add_feature(
                fid="rogue:expertise",
                name="Expertise",
                description="Choose two of your skill proficiencies (or one skill and thieves' tools). Your proficiency bonus is doubled for any ability check you make that uses either of the chosen proficiencies.",
                source_details="Rogue Level 1",
            )
        if level >= 2:
            _add_feature(
                fid="rogue:cunning-action",
                name="Cunning Action",
                description="You can take a bonus action on each of your turns in combat to Dash, Disengage, or Hide.",
                source_details="Rogue Level 2",
            )
    elif class_id == "wizard":
        if spellcasting_payload:
            _add_feature(
                fid="wizard:spellcasting",
                name="Spellcasting",
                description="You have learned to draw on the subtle weave of magic through spells.",
                source_details="Wizard Level 1",
            )
        if level >= 1:
            _add_feature(
                fid="wizard:arcane-recovery",
                name="Arcane Recovery",
                description="Once per day when you finish a short rest, you can recover some of your expended spell slots.",
                source_details="Wizard Level 1",
                limited_use={"maxUses": 1, "currentUses": 1, "resetOn": "long"},
            )
    elif class_id == "cleric":
        if spellcasting_payload:
            _add_feature(
                fid="cleric:spellcasting",
                name="Spellcasting",
                description="You can cast cleric spells, drawing on divine magic through prayer and devotion.",
                source_details="Cleric Level 1",
            )
        if level >= 2:
            _add_feature(
                fid="cleric:channel-divinity",
                name="Channel Divinity",
                description="You can channel divine energy directly from your deity, using that energy to fuel magical effects.",
                source_details="Cleric Level 2",
                limited_use={"maxUses": 1, "currentUses": 1, "resetOn": "short"},
            )
    elif class_id == "bard":
        if spellcasting_payload:
            _add_feature(
                fid="bard:spellcasting",
                name="Spellcasting",
                description="You have learned to untangle and reshape the fabric of reality in harmony with your wishes and music.",
                source_details="Bard Level 1",
            )
        if level >= 1:
            _add_feature(
                fid="bard:bardic-inspiration",
                name="Bardic Inspiration",
                description="You can inspire others through stirring words or music. A creature can add the inspiration die to one ability check, attack roll, or saving throw.",
                source_details="Bard Level 1",
                limited_use={"maxUses": 3, "currentUses": 3, "resetOn": "long"},
            )
        if level >= 2:
            _add_feature(
                fid="bard:jack-of-all-trades",
                name="Jack of All Trades",
                description="You can add half your proficiency bonus, rounded down, to any ability check you make that doesn't already include your proficiency bonus.",
                source_details="Bard Level 2",
            )

    return features


def _basic_race_object(constraints: GenerationConstraints) -> Dict[str, Any]:
    walk_speed, size, base_race = _race_defaults(constraints.race.id)
    return {
        "id": constraints.race.id,
        "name": constraints.race.name,
        "baseRace": base_race if base_race and base_race != constraints.race.id else None,
        "size": size,
        "speed": {"walk": walk_speed},
        "abilityBonuses": _race_ability_bonuses_list(constraints.race.ability_bonuses),
        "traits": [],
        "languages": ["Common"],
        "description": "",
        "source": "PCG-v0",
    }


def _basic_background_object(constraints: GenerationConstraints) -> Dict[str, Any]:
    return {
        "id": constraints.background.id,
        "name": constraints.background.name,
        "skillProficiencies": list(constraints.background.granted_skills or []),
        "toolProficiencies": [],
        "languages": [],
        "equipment": [],
        "feature": None,
        "description": "",
        "source": "PCG-v0",
    }


def _class_level_object(
    *,
    input_data: GenerationInput,
    constraints: GenerationConstraints,
    feature_choices: Dict[str, str],
) -> Dict[str, Any]:
    cls_name = constraints.class_info.name
    level = int(input_data.level)
    subclass: Optional[str] = None
    # If subclass is a selectable feature at this level, surface it in class entry.
    for k, v in (feature_choices or {}).items():
        if "subclass" in k:
            subclass = v
            break

    class_features: List[Dict[str, Any]] = []
    # Minimal: promote fighting style choice to a class feature for visibility.
    fs = feature_choices.get("fighter-fighting-style") if feature_choices else None
    if fs:
        class_features.append(
            {
                "id": f"fighting-style-{fs}",
                "name": f"Fighting Style: {fs.replace('-', ' ').title()}",
                "description": "Chosen fighting style (generated).",
                "source": "class",
                "sourceDetails": f"{cls_name} Level {level}",
            }
        )

    return {
        "name": cls_name,
        "level": level,
        "subclass": subclass,
        "hitDie": int(constraints.class_info.hit_die),
        "features": class_features,
    }


def _derive_spellcasting_payload(
    *,
    input_data: GenerationInput,
    constraints: GenerationConstraints,
    choices: ValidationChoices,
) -> Optional[Dict[str, Any]]:
    sc = constraints.spellcasting
    if not sc:
        return None

    scores = choices.ability_scores.model_dump()
    ability_key = str(sc.ability.value if hasattr(sc.ability, "value") else sc.ability)
    ability_mod = _ability_mod(int(scores.get(ability_key, 10)))
    pb = 2  # PCG supports L1-3 only

    # Map selected IDs → spell dict objects using constraint-provided entries.
    cantrip_by_id = {c.get("id"): c for c in (sc.available_cantrips or []) if isinstance(c, dict) and c.get("id")}
    spell_by_id = {s.get("id"): s for s in (sc.available_spells or []) if isinstance(s, dict) and s.get("id")}

    cantrip_objs = []
    for cid in (choices.selected_cantrips or []):
        src = cantrip_by_id.get(cid)
        if src:
            cantrip_objs.append(
                {
                    "id": src.get("id"),
                    "name": src.get("name"),
                    "level": 0,
                    "school": src.get("school", ""),
                    "description": src.get("description", ""),
                }
            )

    spell_objs = []
    for sid in (choices.selected_spells or []):
        src = spell_by_id.get(sid)
        if src:
            spell_objs.append(
                {
                    "id": src.get("id"),
                    "name": src.get("name"),
                    "level": int(src.get("level", 1) or 1),
                    "school": src.get("school", ""),
                    "description": src.get("description", ""),
                }
            )

    # Spell slots: minimal, with Pact Magic support surfaced from constraints.
    spell_slots: Dict[int, Dict[str, int]] = {}
    if sc.pact_slots is not None and sc.pact_slot_level is not None:
        spell_slots = {int(sc.pact_slot_level): {"total": int(sc.pact_slots), "used": 0}}
    else:
        # v0 slot math for levels 1-3 (enough to drive UI slot tracker).
        # Full caster (bard/cleric/wizard): L1 2x1st, L2 3x1st, L3 4x1st + 2x2nd
        # Half caster (paladin/ranger): starts at L2 (2x1st), L3 (3x1st)
        class_id = (input_data.class_id or "").lower().strip()
        level = int(input_data.level)

        full_table: Dict[int, Dict[int, int]] = {
            1: {1: 2},
            2: {1: 3},
            3: {1: 4, 2: 2},
        }
        half_table: Dict[int, Dict[int, int]] = {
            2: {1: 2},
            3: {1: 3},
        }

        table = half_table if class_id in {"paladin", "ranger"} else full_table
        slots_for_level = table.get(level, {})
        spell_slots = {int(k): {"total": int(v), "used": 0} for k, v in slots_for_level.items()}

    payload: Dict[str, Any] = {
        "class": constraints.class_info.name,
        "ability": ability_key,
        "spellSaveDC": 8 + pb + ability_mod,
        "spellAttackBonus": pb + ability_mod,
        "cantrips": cantrip_objs,
        "spellsKnown": spell_objs,
        "spellSlots": spell_slots,
    }

    # Prepared caster hint: also set spellsPrepared as IDs for UX
    if str(sc.caster_type or "").lower().strip() == "prepared":
        payload["spellsPrepared"] = list(choices.selected_spells or [])

    return payload


_CLASS_SAVE_PROFICIENCIES: Dict[str, List[str]] = {
    "fighter": ["strength", "constitution"],
    "rogue": ["dexterity", "intelligence"],
    "wizard": ["intelligence", "wisdom"],
    "cleric": ["wisdom", "charisma"],
    "bard": ["dexterity", "charisma"],
    "warlock": ["wisdom", "charisma"],
    "paladin": ["wisdom", "charisma"],
    "ranger": ["strength", "dexterity"],
}

_CLASS_ARMOR_PROFICIENCIES: Dict[str, List[str]] = {
    "fighter": ["light armor", "medium armor", "heavy armor", "shields"],
    "rogue": ["light armor"],
    "wizard": [],
    "cleric": ["light armor", "medium armor", "shields"],
    "bard": ["light armor"],
    "warlock": ["light armor"],
    "paladin": ["light armor", "medium armor", "heavy armor", "shields"],
    "ranger": ["light armor", "medium armor", "shields"],
}

_CLASS_WEAPON_PROFICIENCIES: Dict[str, List[str]] = {
    # Keep a mix of broad + specific strings; frontend attack proficiency checks by substring on weapon.name.
    "fighter": ["simple weapons", "martial weapons", "all"],
    "rogue": ["simple weapons", "hand crossbow", "longsword", "rapier", "shortsword"],
    "wizard": ["dagger", "dart", "sling", "quarterstaff", "light crossbow"],
    "cleric": ["simple weapons"],
    "bard": ["simple weapons", "hand crossbow", "longsword", "rapier", "shortsword"],
    "warlock": ["simple weapons"],
    "paladin": ["simple weapons", "martial weapons"],
    "ranger": ["simple weapons", "martial weapons"],
}


def _infer_tool_proficiencies(equipment_items: List[Dict[str, Any]]) -> List[str]:
    tools: List[str] = []
    for item in equipment_items or []:
        try:
            t = str(item.get("type") or "").lower()
            if t in {"tool", "musical instrument"}:
                name = str(item.get("name") or "").strip()
                if name and name.lower() not in {x.lower() for x in tools}:
                    tools.append(name)
        except Exception:
            continue
    return tools


def build_character_object(
    *,
    input_data: GenerationInput,
    constraints: GenerationConstraints,
    preferences: AiPreferences,
    choices: ValidationChoices,
    derived_stats: DerivedStats,
) -> Dict[str, Any]:
    """
    Build a frontend-compatible Character wrapper object.
    """
    now = _iso_now()

    # Speed defaults (v0 catalog does not include full race movement)
    walk_speed, _size, _base = _race_defaults(constraints.race.id)

    # Passive skills (frontend expects these fields)
    skill_mods = dict(derived_stats.skill_modifiers or {})
    passive_investigation = 10 + int(skill_mods.get("Investigation", 0))
    passive_insight = 10 + int(skill_mods.get("Insight", 0))

    dnd5e_derived = {
        "armorClass": int(derived_stats.armor_class),
        "initiative": int(derived_stats.initiative),
        "proficiencyBonus": int(derived_stats.proficiency_bonus),
        "speed": {"walk": int(walk_speed)},
        "maxHp": int(derived_stats.hit_points_max),
        "currentHp": int(derived_stats.hit_points_max),
        "hitDice": {
            "total": int(input_data.level),
            "current": int(input_data.level),
            "size": int(constraints.class_info.hit_die),
        },
        "deathSaves": {"successes": 0, "failures": 0},
        "hasInspiration": False,
        "passivePerception": int(derived_stats.passive_perception),
        "passiveInvestigation": int(passive_investigation),
        "passiveInsight": int(passive_insight),
    }

    equipment_items, weapon_items, _equipment_features, armor, shield = _build_equipment_payload(
        input_data=input_data,
        constraints=constraints,
        choices=choices,
    )

    spellcasting_payload = _derive_spellcasting_payload(input_data=input_data, constraints=constraints, choices=choices)
    features = _basic_feature_list(
        input_data=input_data,
        constraints=constraints,
        choices=choices,
        spellcasting_payload=spellcasting_payload,
    )

    class_id = (input_data.class_id or "").lower().strip()
    saving_throws = _CLASS_SAVE_PROFICIENCIES.get(class_id, [])
    armor_profs = _CLASS_ARMOR_PROFICIENCIES.get(class_id, [])
    weapon_profs = _CLASS_WEAPON_PROFICIENCIES.get(class_id, [])
    tool_profs = _infer_tool_proficiencies(equipment_items)

    dnd5e_data: Dict[str, Any] = {
        "abilityScores": choices.ability_scores.model_dump(),
        "race": _basic_race_object(constraints),
        "classes": [
            _class_level_object(
                input_data=input_data,
                constraints=constraints,
                feature_choices=choices.feature_choices or {},
            )
        ],
        "background": _basic_background_object(constraints),
        "derivedStats": dnd5e_derived,
        "proficiencies": {
            "skills": list(choices.selected_skills or []),
            # Backend compute/validator are authoritative; frontend rule engine can refine later.
            "savingThrows": saving_throws,
            "armor": armor_profs,
            "weapons": weapon_profs,
            "tools": tool_profs,
            "languages": ["Common"],
        },
        "equipment": equipment_items,
        "weapons": weapon_items,
        "armor": armor,
        "shield": shield,
        "features": features,
        "spellcasting": spellcasting_payload,
        "personality": {
            "traits": list(preferences.character.personality.traits or []),
            "ideals": list(preferences.character.personality.ideals or []),
            "bonds": list(preferences.character.personality.bonds or []),
            "flaws": list(preferences.character.personality.flaws or []),
        },
        "appearance": preferences.character.appearance,
        "age": preferences.character.age,
        "backstoryConcept": input_data.concept,
        "currency": {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0},
    }

    # Character wrapper (system-agnostic)
    character: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "name": preferences.character.name,
        "level": int(input_data.level),
        "system": "dnd5e",
        "dnd5eData": dnd5e_data,
        "description": input_data.concept,
        "backstory": preferences.character.backstory,
        "playerName": "",
        "xp": 0,
        "createdAt": now,
        "updatedAt": now,
        "version": 1,
    }
    return character


