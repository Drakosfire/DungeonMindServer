from typing import Any, Dict, List, Tuple

from playercharactergenerator.models.pcg_models import AbilityScores, GenerationConstraints, GenerationInput, ValidationChoices


POINT_BUY_TOTAL = 27
POINT_BUY_MIN_SCORE = 8
POINT_BUY_MAX_SCORE = 15
POINT_BUY_COSTS: Dict[int, int] = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}


def _ability_scores_to_dict(scores: AbilityScores) -> Dict[str, int]:
    return scores.model_dump()


def validate_point_buy(
    *,
    ability_scores_post_racial: AbilityScores,
    racial_bonuses: Dict[str, int],
) -> Tuple[bool, List[str], Dict[str, Any]]:
    issues: List[str] = []
    post = _ability_scores_to_dict(ability_scores_post_racial)

    base_scores: Dict[str, int] = {}
    total_cost = 0

    for ability, score_post in post.items():
        bonus = int(racial_bonuses.get(ability, 0) or 0)
        score_base = int(score_post) - bonus
        base_scores[ability] = score_base

        if score_base < POINT_BUY_MIN_SCORE or score_base > POINT_BUY_MAX_SCORE:
            issues.append(
                f"PointBuy base score out of range for {ability}: {score_base} "
                f"(post={score_post}, bonus={bonus}, allowed={POINT_BUY_MIN_SCORE}-{POINT_BUY_MAX_SCORE})"
            )
            continue

        cost = POINT_BUY_COSTS.get(score_base)
        if cost is None:
            issues.append(f"PointBuy cost missing for base score {score_base} ({ability})")
            continue

        total_cost += cost

    if total_cost > POINT_BUY_TOTAL:
        issues.append(f"PointBuy total exceeded: {total_cost}/{POINT_BUY_TOTAL}")

    success = len(issues) == 0
    details = {"baseScores": base_scores, "pointsSpent": total_cost, "pointsTotal": POINT_BUY_TOTAL}
    return success, issues, details


def validate_skills(
    *,
    selected_skills: List[str],
    constraints: GenerationConstraints,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    issues: List[str] = []

    granted = list(constraints.skills.granted_by_background)
    class_opts = list(constraints.skills.class_options)
    choose_count = int(constraints.skills.choose_count)

    selected = list(selected_skills)
    selected_set = set(selected)

    if len(selected) != len(selected_set):
        issues.append("Duplicate skills selected")

    for s in granted:
        if s not in selected_set:
            issues.append(f"Missing background-granted skill: {s}")

    allowed = set(granted) | set(class_opts)
    for s in selected:
        if s not in allowed:
            issues.append(f"Selected skill not allowed by constraints: {s}")

    expected_total = len(set(granted)) + choose_count
    if len(selected_set) != expected_total:
        issues.append(f"Incorrect total skills: {len(selected_set)} selected, expected {expected_total} (bg={len(set(granted))}, classChoose={choose_count})")

    success = len(issues) == 0
    details = {"grantedByBackground": granted, "classOptions": class_opts, "chooseCount": choose_count}
    return success, issues, details


def validate_equipment_package(
    *,
    equipment_package_id: str,
    constraints: GenerationConstraints,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    issues: List[str] = []

    packages = constraints.equipment.get("packages", [])
    pkg_ids = {p.id for p in packages}

    if equipment_package_id not in pkg_ids:
        issues.append(f"Invalid equipmentPackageId: {equipment_package_id} (allowed: {sorted(pkg_ids)})")

    success = len(issues) == 0
    details = {"allowedPackageIds": sorted(pkg_ids)}
    return success, issues, details


def validate_feature_choices(
    *,
    feature_choices: Dict[str, str],
    constraints: GenerationConstraints,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    issues: List[str] = []

    required = constraints.feature_choices or []
    required_ids = [fc.feature_id for fc in required]

    for fc in required:
        if fc.feature_id not in feature_choices:
            issues.append(f"Missing feature choice for {fc.feature_id}")
            continue
        chosen = feature_choices[fc.feature_id]
        allowed = {o.id for o in fc.options}
        if chosen not in allowed:
            issues.append(f"Invalid choice for {fc.feature_id}: {chosen} (allowed: {sorted(allowed)})")

    # Extra keys are allowed (forward compatibility), but we surface them for debugging.
    extra = [k for k in feature_choices.keys() if k not in required_ids]
    details = {"requiredFeatureIds": required_ids, "extraFeatureIds": extra}

    success = len(issues) == 0
    return success, issues, details


def validate_translated_choices(
    *,
    input_data: GenerationInput,
    constraints: GenerationConstraints,
    choices: ValidationChoices,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    issues: List[str] = []
    sections: Dict[str, Any] = {}

    ok, sec_issues, details = validate_point_buy(
        ability_scores_post_racial=choices.ability_scores,
        racial_bonuses=constraints.race.ability_bonuses,
    )
    sections["pointBuy"] = {"success": ok, "issues": sec_issues, "details": details}
    issues.extend(sec_issues)

    ok, sec_issues, details = validate_skills(
        selected_skills=choices.selected_skills,
        constraints=constraints,
    )
    sections["skills"] = {"success": ok, "issues": sec_issues, "details": details}
    issues.extend(sec_issues)

    ok, sec_issues, details = validate_equipment_package(
        equipment_package_id=choices.equipment_package_id,
        constraints=constraints,
    )
    sections["equipment"] = {"success": ok, "issues": sec_issues, "details": details}
    issues.extend(sec_issues)

    ok, sec_issues, details = validate_feature_choices(
        feature_choices=choices.feature_choices,
        constraints=constraints,
    )
    sections["featureChoices"] = {"success": ok, "issues": sec_issues, "details": details}
    issues.extend(sec_issues)

    # Spell validation (E4)
    if constraints.spellcasting:
        ok, sec_issues, details = validate_spells(
            input_data=input_data,
            constraints=constraints,
            choices=choices,
        )
        sections["spells"] = {"success": ok, "issues": sec_issues, "details": details}
        issues.extend(sec_issues)

    return len(issues) == 0, issues, sections


def _ability_mod(score: int) -> int:
    return (int(score) - 10) // 2


def validate_spells(
    *,
    input_data: GenerationInput,
    constraints: GenerationConstraints,
    choices: ValidationChoices,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    issues: List[str] = []
    sc = constraints.spellcasting
    if not sc:
        return True, [], {"note": "No spellcasting constraints"}

    selected_cantrips = list(choices.selected_cantrips or [])
    selected_spells = list(choices.selected_spells or [])

    # Dedupe checks
    if len(selected_cantrips) != len(set(selected_cantrips)):
        issues.append("Duplicate cantrips selected")
    if len(selected_spells) != len(set(selected_spells)):
        issues.append("Duplicate spells selected")

    cantrips_known = int(sc.cantrips_known or 0)
    if len(selected_cantrips) != cantrips_known:
        issues.append(f"Incorrect cantrip count: {len(selected_cantrips)} selected, expected {cantrips_known}")

    caster_type = (sc.caster_type or "").lower().strip()
    expected_spells = 0
    if caster_type == "known":
        expected_spells = int(sc.spells_known or 0)
    elif caster_type == "prepared":
        # Prepared formula: ability mod + level
        if (sc.prepared_formula or "").strip() != "abilityModPlusLevel":
            issues.append(f"Unsupported preparedFormula: {sc.prepared_formula}")
        scores = _ability_scores_to_dict(choices.ability_scores)
        ability_key = str(sc.ability.value if hasattr(sc.ability, "value") else sc.ability)
        ability_mod = _ability_mod(int(scores.get(ability_key, 10)))
        expected_spells = max(1, ability_mod + int(input_data.level))
    else:
        issues.append(f"Unknown casterType: {sc.caster_type}")

    if len(selected_spells) != expected_spells:
        issues.append(f"Incorrect spell count: {len(selected_spells)} selected, expected {expected_spells}")

    max_spell_level = int(sc.max_spell_level or 1)

    allowed_cantrips = {c.get("id") for c in (sc.available_cantrips or []) if isinstance(c, dict)}
    allowed_spells = {s.get("id") for s in (sc.available_spells or []) if isinstance(s, dict)}
    allowed_all = allowed_cantrips | allowed_spells

    for cid in selected_cantrips:
        if cid not in allowed_cantrips:
            issues.append(f"Cantrip not allowed by constraints: {cid}")

    for sid in selected_spells:
        if sid not in allowed_spells:
            issues.append(f"Spell not allowed by constraints: {sid}")

    # Level violations (best-effort: infer level from availableSpells entries)
    spell_level_by_id = {
        s.get("id"): int(s.get("level", 0))
        for s in (sc.available_spells or [])
        if isinstance(s, dict) and s.get("id")
    }
    for sid in selected_spells:
        lvl = int(spell_level_by_id.get(sid, 0))
        if lvl <= 0:
            continue
        if lvl > max_spell_level:
            issues.append(f"Spell level too high for constraints: {sid} (level {lvl}, max {max_spell_level})")

    details = {
        "casterType": sc.caster_type,
        "preparedFormula": sc.prepared_formula,
        "expectedCantrips": cantrips_known,
        "expectedSpells": expected_spells,
        "maxSpellLevel": max_spell_level,
        "allowedCantripIds": sorted([x for x in allowed_cantrips if x]),
        "allowedSpellIds": sorted([x for x in allowed_spells if x]),
        "selectedCantrips": selected_cantrips,
        "selectedSpells": selected_spells,
    }
    return len(issues) == 0, issues, details


