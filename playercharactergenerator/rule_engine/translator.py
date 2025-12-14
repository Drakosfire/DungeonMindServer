"""
PCG Translator (Phase 5.1)

Ports the frontend `generation/preferenceTranslator.ts` concept into the backend.

Key principle:
- AI expresses INTENT (preferences)
- Translator enforces VALIDITY (outputs ValidationChoices)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from playercharactergenerator.models.pcg_models import (
    AbilityName,
    AbilityScores,
    AiPreferences,
    GenerationConstraints,
    SkillConstraints,
    SpellcastingConstraints,
    ValidationChoices,
)

# Keep point buy rules aligned with backend validators.
POINT_BUY_TOTAL = 27
POINT_BUY_MIN_SCORE = 8
POINT_BUY_MAX_SCORE = 15
POINT_BUY_COSTS: Dict[int, int] = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}

ABILITY_ORDER: List[str] = [
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
]


@dataclass(frozen=True)
class AbilityTranslationResult:
    success: bool
    scores_post_racial: Dict[str, int]
    points_spent: int
    issues: List[str]


@dataclass(frozen=True)
class SkillTranslationResult:
    success: bool
    selected: List[str]
    unmatched_themes: List[str]
    issues: List[str]


@dataclass(frozen=True)
class EquipmentTranslationResult:
    success: bool
    package_id: Optional[str]
    issues: List[str]


@dataclass(frozen=True)
class FeatureChoiceTranslationResult:
    success: bool
    choices: Dict[str, str]
    issues: List[str]


@dataclass(frozen=True)
class SpellTranslationResult:
    success: bool
    cantrips: List[str]
    spells: List[str]
    unmatched_themes: List[str]
    issues: List[str]


def _get_point_buy_cost(score: int) -> int:
    return int(POINT_BUY_COSTS.get(int(score), 0))


def _ensure_all_abilities(priorities: Sequence[str | AbilityName]) -> Tuple[List[str], List[str]]:
    issues: List[str] = []
    normalized = [str(p.value if isinstance(p, AbilityName) else p).lower().strip() for p in priorities]
    normalized = [p for p in normalized if p]

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: List[str] = []
    for p in normalized:
        if p not in seen:
            seen.add(p)
            deduped.append(p)

    missing = [a for a in ABILITY_ORDER if a not in seen]
    if len(deduped) != 6:
        issues.append(f"Priorities incomplete/invalid; filled missing abilities: {', '.join(missing)}")
    filled = (deduped + missing)[:6]
    return filled, issues


def translate_ability_priorities(
    priorities: Sequence[str | AbilityName],
    racial_bonuses: Dict[str, int],
) -> AbilityTranslationResult:
    """
    Convert ordered ability priorities into post-racial point-buy scores.

    Strategy (mirrors frontend translator intent):
    - Start all base scores at 8
    - Apply a common optimal distribution by priority: [15,15,13,13,10,8]
    - Spend remaining points greedily on highest priority abilities
    - Apply racial bonuses AFTER point buy
    """
    issues: List[str] = []

    prios, pri_issues = _ensure_all_abilities(priorities)
    issues.extend(pri_issues)

    base: Dict[str, int] = {a: POINT_BUY_MIN_SCORE for a in ABILITY_ORDER}
    points_remaining = POINT_BUY_TOTAL

    target_scores = [15, 15, 13, 13, 10, 8]
    for idx, ability in enumerate(prios):
        target = int(target_scores[idx] if idx < len(target_scores) else POINT_BUY_MIN_SCORE)
        target = min(target, POINT_BUY_MAX_SCORE)
        current = int(base.get(ability, POINT_BUY_MIN_SCORE))
        cost_needed = _get_point_buy_cost(target) - _get_point_buy_cost(current)

        if cost_needed <= 0:
            continue

        if cost_needed <= points_remaining:
            base[ability] = target
            points_remaining -= cost_needed
            continue

        # If we can't reach target, increment as much as possible.
        score = current
        while score < POINT_BUY_MAX_SCORE and points_remaining > 0:
            next_score = score + 1
            next_cost = _get_point_buy_cost(next_score) - _get_point_buy_cost(score)
            if next_cost <= points_remaining:
                score = next_score
                points_remaining -= next_cost
            else:
                break
        base[ability] = score

    # Spend any leftover points on highest priorities that can still increase.
    while points_remaining > 0:
        allocated = False
        for ability in prios:
            if int(base.get(ability, POINT_BUY_MIN_SCORE)) >= POINT_BUY_MAX_SCORE:
                continue
            score = int(base[ability])
            next_score = score + 1
            next_cost = _get_point_buy_cost(next_score) - _get_point_buy_cost(score)
            if next_cost <= points_remaining:
                base[ability] = next_score
                points_remaining -= next_cost
                allocated = True
                break
        if not allocated:
            break

    points_spent = POINT_BUY_TOTAL - points_remaining

    # Apply racial bonuses (post-racial)
    post: Dict[str, int] = dict(base)
    for ability, bonus in (racial_bonuses or {}).items():
        if ability in post and bonus:
            post[ability] = int(post[ability]) + int(bonus)

    success = points_spent <= POINT_BUY_TOTAL
    if not success:
        issues.append(f"Point buy total exceeded: {points_spent}/{POINT_BUY_TOTAL}")

    return AbilityTranslationResult(
        success=success,
        scores_post_racial=post,
        points_spent=points_spent,
        issues=issues,
    )


# Theme → skills mapping (ported from frontend, intentionally heuristic)
SKILL_THEME_MAP: Dict[str, List[str]] = {
    # Physical themes
    "physical": ["Athletics", "Acrobatics"],
    "physical prowess": ["Athletics"],
    "strength": ["Athletics"],
    "agility": ["Acrobatics"],
    "endurance": ["Athletics"],
    # Stealth themes
    "stealth": ["Stealth"],
    "sneaky": ["Stealth", "Sleight of Hand"],
    "thievery": ["Sleight of Hand", "Stealth"],
    "nimble": ["Acrobatics", "Sleight of Hand"],
    # Social
    "social": ["Persuasion", "Deception", "Intimidation"],
    "persuasion": ["Persuasion"],
    "deception": ["Deception"],
    "intimidation": ["Intimidation"],
    "intimidating": ["Intimidation"],
    "charm": ["Persuasion", "Performance"],
    "leadership": ["Persuasion", "Intimidation"],
    # Knowledge
    "knowledge": ["Arcana", "History", "Nature", "Religion"],
    "arcane": ["Arcana"],
    "scholarly": ["History", "Arcana"],
    "nature": ["Nature", "Survival"],
    "religious": ["Religion"],
    "lore": ["History", "Arcana", "Religion"],
    # Awareness
    "awareness": ["Perception", "Insight"],
    "perception": ["Perception"],
    "insight": ["Insight"],
    "observant": ["Perception", "Investigation"],
    "vigilant": ["Perception"],
    "intuition": ["Insight"],
    # Survival
    "survival": ["Survival", "Nature"],
    "wilderness": ["Survival", "Nature", "Animal Handling"],
    "tracking": ["Survival", "Perception"],
    "animals": ["Animal Handling"],
    # Investigation
    "investigation": ["Investigation"],
    "detective": ["Investigation", "Insight", "Perception"],
    "analytical": ["Investigation"],
    # Performance
    "performance": ["Performance"],
    "entertainment": ["Performance"],
    "artistic": ["Performance"],
    # Medical
    "medical": ["Medicine"],
    "healing": ["Medicine"],
    "doctor": ["Medicine"],
}


def translate_skill_themes(themes: Sequence[str], constraints: SkillConstraints) -> SkillTranslationResult:
    issues: List[str] = []
    unmatched: List[str] = []

    granted = list(constraints.granted_by_background or [])
    granted_set = set(granted)

    class_opts = list(constraints.class_options or [])
    # 5e overlap behavior (replace): don't pick a class-option skill already granted.
    available_opts = [s for s in class_opts if s not in granted_set]
    choose_count = int(constraints.choose_count or 0)

    candidate_skills: List[str] = []
    for theme in themes or []:
        t = str(theme).lower().strip()
        if not t:
            continue
        mapped = SKILL_THEME_MAP.get(t)
        if mapped:
            candidate_skills.extend(mapped)
            continue
        # Partial match fallback
        matched = False
        for key, skills in SKILL_THEME_MAP.items():
            if t in key or key in t:
                candidate_skills.extend(skills)
                matched = True
                break
        if not matched:
            unmatched.append(str(theme))

    selected_set: set[str] = set()
    for cand in candidate_skills:
        if len(selected_set) >= choose_count:
            break
        if cand in available_opts and cand not in selected_set:
            selected_set.add(cand)

    # Fill remaining with any available choices to satisfy backend validator.
    for opt in available_opts:
        if len(selected_set) >= choose_count:
            break
        if opt not in selected_set:
            selected_set.add(opt)
            issues.append(f"Auto-selected {opt} to fill remaining skill slot")

    final = list(dict.fromkeys([*granted, *sorted(selected_set)]))  # stable-ish and deduped
    expected_total = len(set(granted)) + choose_count

    if unmatched:
        issues.append(f"Could not match themes: {', '.join(unmatched)}")

    success = (all(s in set(final) for s in granted)) and (len(selected_set) == choose_count) and (len(set(final)) == expected_total)
    if not success:
        issues.append(f"Skill selection invalid: selected={len(set(final))}, expected={expected_total}")

    return SkillTranslationResult(
        success=success,
        selected=list(set(final)),
        unmatched_themes=unmatched,
        issues=issues,
    )


EQUIPMENT_KEYWORDS: Dict[str, List[str]] = {
    "heavy armor": ["chain mail", "heavy", "plate"],
    "light armor": ["leather", "light", "mobile"],
    "medium armor": ["scale", "medium", "breastplate"],
    "no armor": ["unarmored", "cloth"],
    "shield": ["shield"],
    "two-handed": ["two-handed", "greatsword", "greataxe", "maul"],
    "ranged": ["longbow", "shortbow", "crossbow", "ranged"],
    "dual wield": ["two weapons", "dual"],
    "defensive": ["shield", "defense"],
    "aggressive": ["two-handed", "damage"],
    "mobile": ["light", "mobile", "ranged"],
    "balanced": ["versatile", "martial"],
}


def translate_equipment_style(style: str, packages: Sequence[Any]) -> EquipmentTranslationResult:
    issues: List[str] = []
    pkgs = list(packages or [])
    if not pkgs:
        return EquipmentTranslationResult(success=False, package_id=None, issues=["No equipment packages available"])
    if len(pkgs) == 1:
        return EquipmentTranslationResult(success=True, package_id=str(pkgs[0].id), issues=[])

    normalized = str(style or "").lower()
    style_keywords: List[str] = []
    for key, matches in EQUIPMENT_KEYWORDS.items():
        if key in normalized:
            style_keywords.extend(matches)
    style_keywords.extend([w for w in normalized.split() if w])

    best_pkg = pkgs[0]
    best_score = -1
    for pkg in pkgs:
        desc = str(getattr(pkg, "description", "") or "").lower()
        score = 0
        for kw in style_keywords:
            if kw and kw in desc:
                score += 1
        if score > best_score:
            best_score = score
            best_pkg = pkg

    if best_score <= 0:
        issues.append(f'No strong match for style "{style}", defaulting to first package')

    return EquipmentTranslationResult(success=True, package_id=str(best_pkg.id), issues=issues)


def translate_feature_choices(preferences: AiPreferences, feature_choices: Sequence[Any]) -> FeatureChoiceTranslationResult:
    issues: List[str] = []
    choices: Dict[str, str] = {}

    for fc in feature_choices or []:
        feature_id = str(getattr(fc, "feature_id", None) or getattr(fc, "featureId", ""))
        options = list(getattr(fc, "options", []) or [])
        if not feature_id or not options:
            continue

        # Special-case: fighting style preference (common at L1 for fighters/rangers/paladins)
        if "fighting-style" in feature_id and preferences.fighting_style_preference:
            pref_id = str(preferences.fighting_style_preference.id)
            valid = next((o for o in options if str(getattr(o, "id", "")) == pref_id), None)
            if valid:
                choices[feature_id] = pref_id
            else:
                choices[feature_id] = str(getattr(options[0], "id", ""))
                issues.append(f'Invalid fighting style "{pref_id}", defaulting to first option')
            continue

        # Special-case: subclass preference (only if subclasses are a choice at this level)
        if "subclass" in feature_id and preferences.subclass_preference:
            pref_id = str(preferences.subclass_preference.id)
            valid = next((o for o in options if str(getattr(o, "id", "")) == pref_id), None)
            if valid:
                choices[feature_id] = pref_id
            else:
                choices[feature_id] = str(getattr(options[0], "id", ""))
                issues.append(f'Invalid subclass "{pref_id}", defaulting to first option')
            continue

        # Default: first option (deterministic)
        choices[feature_id] = str(getattr(options[0], "id", ""))
        issues.append(f"No preference for {getattr(fc, 'feature_name', getattr(fc, 'featureName', feature_id))}, defaulting to first option")

    return FeatureChoiceTranslationResult(success=True, choices=choices, issues=issues)


SPELL_THEME_MAP: Dict[str, Dict[str, List[str]]] = {
    "damage": {"tags": ["damage", "attack"]},
    "fire": {"tags": ["fire"]},
    "cold": {"tags": ["cold", "ice"]},
    "lightning": {"tags": ["lightning", "thunder"]},
    "healing": {"tags": ["healing", "restoration"]},
    "control": {"schools": ["enchantment", "illusion"], "tags": ["control", "crowd"]},
    "buff": {"schools": ["abjuration", "transmutation"], "tags": ["buff", "enhance"]},
    "utility": {"tags": ["utility", "ritual"]},
    "summoning": {"schools": ["conjuration"], "tags": ["summon"]},
    "divination": {"schools": ["divination"], "tags": ["detection", "knowledge"]},
    "necromancy": {"schools": ["necromancy"]},
    "illusion": {"schools": ["illusion"]},
    "protection": {"schools": ["abjuration"], "tags": ["protection", "defense"]},
}


def _ability_mod(score: int) -> int:
    return (int(score) - 10) // 2


def _select_spells_by_themes(
    *,
    themes: Sequence[str],
    available: Sequence[Dict[str, Any]],
    count: int,
    unmatched: List[str],
) -> List[str]:
    themes_norm = [str(t).lower().strip() for t in (themes or []) if str(t).strip()]

    scored: List[Tuple[int, int, str]] = []  # (score, level, id)
    for s in available or []:
        sid = str(s.get("id") or "")
        if not sid:
            continue
        name = str(s.get("name") or "").lower()
        desc = str(s.get("description") or "").lower()
        school = str(s.get("school") or "").lower()
        lvl = int(s.get("level") or 0)

        score = 0
        for t in themes_norm:
            mapping = SPELL_THEME_MAP.get(t)
            if mapping:
                if school and school in (mapping.get("schools") or []):
                    score += 2
                for tag in mapping.get("tags") or []:
                    if tag in name or tag in desc:
                        score += 1
            else:
                # Direct substring match
                if t and (t in name or t in desc):
                    score += 1

        scored.append((score, lvl, sid))

    scored.sort(key=lambda x: (-x[0], x[1]))

    selected: List[str] = []
    used: set[str] = set()
    for _score, _lvl, sid in scored:
        if len(selected) >= int(count):
            break
        if sid not in used:
            used.add(sid)
            selected.append(sid)

    # Fill remainder with any available (ensures we can meet validator counts even if themes don't match).
    for s in available or []:
        if len(selected) >= int(count):
            break
        sid = str(s.get("id") or "")
        if sid and sid not in used:
            used.add(sid)
            selected.append(sid)

    # Track unmatched themes (best-effort signal, does not affect success)
    for t in themes_norm:
        if t in SPELL_THEME_MAP:
            continue
        # Heuristic: if no spell name/desc contains the theme string, consider unmatched
        any_match = any(
            t in str(s.get("name") or "").lower() or t in str(s.get("description") or "").lower()
            for s in (available or [])
        )
        if not any_match:
            unmatched.append(t)

    return selected


def translate_spell_themes(
    cantrip_themes: Sequence[str],
    spell_themes: Sequence[str],
    constraints: SpellcastingConstraints,
    level: int,
    ability_scores_post_racial: Dict[str, int],
) -> SpellTranslationResult:
    issues: List[str] = []
    unmatched: List[str] = []

    available_cantrips = list(constraints.available_cantrips or [])
    available_spells = list(constraints.available_spells or [])

    cantrip_count = int(constraints.cantrips_known or 0)

    caster_type = str(constraints.caster_type or "").lower().strip()
    expected_spells = 0
    if caster_type == "known":
        expected_spells = int(constraints.spells_known or 0)
    elif caster_type == "prepared":
        ability_key = str(constraints.ability.value if hasattr(constraints.ability, "value") else constraints.ability)
        ability_mod = _ability_mod(int(ability_scores_post_racial.get(ability_key, 10)))
        formula = str(constraints.prepared_formula or "").strip()
        if formula == "abilityModPlusLevel":
            expected_spells = max(1, ability_mod + int(level))
        elif formula == "abilityModPlusHalfLevel":
            expected_spells = max(1, ability_mod + (int(level) // 2))
        else:
            issues.append(f"Unsupported preparedFormula: {constraints.prepared_formula}")
            expected_spells = 0
    else:
        issues.append(f"Unknown casterType: {constraints.caster_type}")
        expected_spells = 0

    max_spell_level = int(constraints.max_spell_level or 1)
    available_spells = [s for s in available_spells if int(s.get("level") or 0) <= max_spell_level]

    cantrips = _select_spells_by_themes(
        themes=cantrip_themes,
        available=available_cantrips,
        count=cantrip_count,
        unmatched=unmatched,
    )
    spells = _select_spells_by_themes(
        themes=spell_themes,
        available=available_spells,
        count=expected_spells,
        unmatched=unmatched,
    )

    if len(cantrips) != cantrip_count:
        issues.append(f"Incorrect cantrip count: selected {len(cantrips)}, expected {cantrip_count}")
    if len(spells) != expected_spells:
        issues.append(f"Incorrect spell count: selected {len(spells)}, expected {expected_spells}")

    success = (len(cantrips) == cantrip_count) and (len(spells) == expected_spells) and (len(issues) == 0)
    return SpellTranslationResult(
        success=success,
        cantrips=cantrips,
        spells=spells,
        unmatched_themes=unmatched,
        issues=issues,
    )


def translate_preferences(
    *,
    preferences: AiPreferences,
    constraints: GenerationConstraints,
    level: int,
) -> Tuple[bool, ValidationChoices, List[str]]:
    """
    Translate AI preferences into backend ValidationChoices.

    Returns: (success, choices, issues)
    """
    issues: List[str] = []

    # 1) Abilities (post-racial)
    ability_result = translate_ability_priorities(
        priorities=list(preferences.ability_priorities or []),
        racial_bonuses=dict(constraints.race.ability_bonuses or {}),
    )
    issues.extend(ability_result.issues)

    # 2) Skills
    skill_result = translate_skill_themes(list(preferences.skill_themes or []), constraints.skills)
    issues.extend(skill_result.issues)

    # 3) Equipment
    packages = (constraints.equipment or {}).get("packages", []) or []
    equipment_result = translate_equipment_style(preferences.equipment_style, packages)
    issues.extend(equipment_result.issues)

    # 4) Feature choices
    feature_result = translate_feature_choices(preferences, constraints.feature_choices or [])
    issues.extend(feature_result.issues)

    # 5) Spells
    spell_cantrips: List[str] = []
    spell_spells: List[str] = []
    spell_ok = True
    if constraints.spellcasting:
        spell_result = translate_spell_themes(
            list(preferences.cantrip_themes or []),
            list(preferences.spell_themes or []),
            constraints.spellcasting,
            level,
            ability_result.scores_post_racial,
        )
        spell_cantrips = spell_result.cantrips
        spell_spells = spell_result.spells
        issues.extend(spell_result.issues)
        spell_ok = spell_result.success

    scores = ability_result.scores_post_racial
    ability_scores = AbilityScores(
        strength=int(scores["strength"]),
        dexterity=int(scores["dexterity"]),
        constitution=int(scores["constitution"]),
        intelligence=int(scores["intelligence"]),
        wisdom=int(scores["wisdom"]),
        charisma=int(scores["charisma"]),
    )

    choices = ValidationChoices(
        abilityScores=ability_scores,
        selectedSkills=skill_result.selected,
        equipmentPackageId=str(equipment_result.package_id or ""),
        featureChoices=feature_result.choices,
        selectedCantrips=spell_cantrips,
        selectedSpells=spell_spells,
    )

    success = ability_result.success and skill_result.success and equipment_result.success and feature_result.success and spell_ok
    return success, choices, issues


