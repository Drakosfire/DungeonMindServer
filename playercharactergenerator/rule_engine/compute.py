from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from playercharactergenerator.models.pcg_models import (
    AbilityScores,
    DerivedStats,
    GenerationConstraints,
    GenerationInput,
    ValidationChoices,
)


SkillName = str
AbilityKey = str  # "strength" | "dexterity" | ...


SKILL_TO_ABILITY: Dict[SkillName, AbilityKey] = {
    "Acrobatics": "dexterity",
    "Animal Handling": "wisdom",
    "Arcana": "intelligence",
    "Athletics": "strength",
    "Deception": "charisma",
    "History": "intelligence",
    "Insight": "wisdom",
    "Intimidation": "charisma",
    "Investigation": "intelligence",
    "Medicine": "wisdom",
    "Nature": "intelligence",
    "Perception": "wisdom",
    "Performance": "charisma",
    "Persuasion": "charisma",
    "Religion": "intelligence",
    "Sleight of Hand": "dexterity",
    "Stealth": "dexterity",
    "Survival": "wisdom",
}


# SRD-ish saving throw proficiencies (per class) — enough for our current catalog classes.
CLASS_SAVE_PROFICIENCIES: Dict[str, List[AbilityKey]] = {
    "fighter": ["strength", "constitution"],
    "rogue": ["dexterity", "intelligence"],
    "wizard": ["intelligence", "wisdom"],
    "cleric": ["wisdom", "charisma"],
    "bard": ["dexterity", "charisma"],
}


ARMOR_RULES: Dict[str, Dict[str, Any]] = {
    # Light
    "leather-armor": {"kind": "light", "base_ac": 11, "dex_cap": None},
    # Medium
    "scale-mail": {"kind": "medium", "base_ac": 14, "dex_cap": 2},
    # Heavy
    "chain-mail": {"kind": "heavy", "base_ac": 16, "dex_cap": 0},
    # Shield (separate bonus)
    "shield": {"kind": "shield", "ac_bonus": 2},
}


def _ability_scores_to_dict(scores: AbilityScores) -> Dict[str, int]:
    return scores.model_dump()


def _ability_mod(score: int) -> int:
    # D&D 5e: floor((score - 10) / 2). Python // floors for negatives too.
    return (int(score) - 10) // 2


def _proficiency_bonus(level: int) -> int:
    # 5e: levels 1–4 are +2 (PCG scope is 1–3).
    return 2


def _average_hit_die_gain(hit_die: int) -> int:
    # PHB "average" (rounded up): d6->4, d8->5, d10->6, d12->7
    return (int(hit_die) // 2) + 1


def _compute_hp(*, level: int, hit_die: int, con_mod: int) -> int:
    if level <= 0:
        return 0
    # Level 1: max hit die
    hp = int(hit_die) + con_mod
    # Levels 2+: average gain
    if level > 1:
        hp += (level - 1) * (_average_hit_die_gain(hit_die) + con_mod)
    return max(1, hp)


def _extract_equipment_items(
    *, constraints: GenerationConstraints, equipment_package_id: str
) -> Tuple[List[str], List[str]]:
    """
    Returns (items, issues). Items are item IDs from the chosen equipment package.
    """
    issues: List[str] = []
    packages = constraints.equipment.get("packages", []) or []
    pkg = next((p for p in packages if p.id == equipment_package_id), None)
    if not pkg:
        issues.append(f"Equipment package not found in constraints: {equipment_package_id}")
        return [], issues
    return list(pkg.items or []), issues


def _compute_ac(
    *,
    dex_mod: int,
    equipment_items: List[str],
    fighting_style_id: Optional[str],
) -> Tuple[int, Dict[str, Any]]:
    """
    Very small AC compute for E3:
    - pick first recognized armor item in equipment list (if any)
    - apply shield bonus if present
    - apply Fighter Defense (+1) if wearing armor
    """
    details: Dict[str, Any] = {
        "armorItemId": None,
        "armorKind": None,
        "baseAc": None,
        "dexModApplied": 0,
        "shieldBonus": 0,
        "fightingStyleDefenseBonus": 0,
    }

    armor_item: Optional[str] = None
    armor_rule: Optional[Dict[str, Any]] = None
    for item in equipment_items:
        rule = ARMOR_RULES.get(item)
        if rule and rule.get("kind") in ("light", "medium", "heavy"):
            armor_item = item
            armor_rule = rule
            break

    shield_bonus = 0
    if "shield" in equipment_items:
        shield_bonus = int(ARMOR_RULES["shield"]["ac_bonus"])

    if armor_rule:
        kind = armor_rule["kind"]
        base_ac = int(armor_rule["base_ac"])
        dex_cap = armor_rule.get("dex_cap")
        dex_applied = 0
        if kind == "light":
            dex_applied = dex_mod
        elif kind == "medium":
            dex_applied = min(dex_mod, int(dex_cap if dex_cap is not None else 2))
        elif kind == "heavy":
            dex_applied = 0

        ac = base_ac + dex_applied + shield_bonus

        defense_bonus = 0
        if fighting_style_id == "defense":
            # PHB: +1 AC while wearing armor.
            defense_bonus = 1
            ac += defense_bonus

        details.update(
            {
                "armorItemId": armor_item,
                "armorKind": kind,
                "baseAc": base_ac,
                "dexModApplied": dex_applied,
                "shieldBonus": shield_bonus,
                "fightingStyleDefenseBonus": defense_bonus,
            }
        )
        return ac, details

    # No armor found: 10 + DEX, still allow shield if present (rare but ok for now).
    ac = 10 + dex_mod + shield_bonus
    details.update(
        {
            "armorItemId": None,
            "armorKind": "unarmored",
            "baseAc": 10,
            "dexModApplied": dex_mod,
            "shieldBonus": shield_bonus,
        }
    )
    return ac, details


def compute_derived_stats(
    *,
    input_data: GenerationInput,
    constraints: GenerationConstraints,
    choices: ValidationChoices,
) -> Tuple[bool, List[str], DerivedStats | None, Dict[str, Any]]:
    """
    Computes derived stats for the given choices.
    Returns (success, issues, derived_stats, sections).
    """
    issues: List[str] = []
    sections: Dict[str, Any] = {}

    level = int(input_data.level)
    pb = _proficiency_bonus(level)

    scores = _ability_scores_to_dict(choices.ability_scores)
    mods = {k: _ability_mod(v) for k, v in scores.items()}

    # HP
    hit_die = int(constraints.class_info.hit_die)
    con_mod = int(mods.get("constitution", 0))
    hp_max = _compute_hp(level=level, hit_die=hit_die, con_mod=con_mod)

    # Saves
    save_profs = CLASS_SAVE_PROFICIENCIES.get(input_data.class_id, [])
    saving_throws = {a: int(mods[a]) + (pb if a in save_profs else 0) for a in mods.keys()}

    # Skills (treat selected_skills as proficient list)
    selected_set = set(choices.selected_skills or [])
    skill_modifiers: Dict[str, int] = {}
    for skill, ability in SKILL_TO_ABILITY.items():
        base = int(mods.get(ability, 0))
        prof = pb if skill in selected_set else 0
        skill_modifiers[skill] = base + prof

    passive_perception = 10 + int(skill_modifiers.get("Perception", int(mods.get("wisdom", 0))))

    # Equipment -> AC
    equipment_items, eq_issues = _extract_equipment_items(
        constraints=constraints, equipment_package_id=choices.equipment_package_id
    )
    issues.extend(eq_issues)

    fighting_style_id = choices.feature_choices.get("fighter-fighting-style") if choices.feature_choices else None
    ac, ac_details = _compute_ac(
        dex_mod=int(mods.get("dexterity", 0)),
        equipment_items=equipment_items,
        fighting_style_id=fighting_style_id,
    )

    initiative = int(mods.get("dexterity", 0))

    sections["compute"] = {
        "success": len(issues) == 0,
        "issues": list(issues),
        "details": {
            "level": level,
            "hitDie": hit_die,
            "equipmentItems": equipment_items,
            "acDetails": ac_details,
            "saveProficiencies": save_profs,
        },
    }

    if issues:
        return False, issues, None, sections

    derived = DerivedStats(
        abilityModifiers=mods,
        proficiencyBonus=pb,
        hitPointsMax=hp_max,
        armorClass=ac,
        initiative=initiative,
        savingThrows=saving_throws,
        skillModifiers=skill_modifiers,
        passivePerception=passive_perception,
    )
    return True, [], derived, sections


