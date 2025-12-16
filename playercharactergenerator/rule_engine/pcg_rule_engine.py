import logging
from typing import List, Optional

from playercharactergenerator.models.pcg_models import (
    BackgroundConstraints,
    ClassConstraints,
    EquipmentPackage,
    FeatureChoice,
    FeatureOption,
    GenerationConstraints,
    GenerationInput,
    RaceConstraints,
    SkillConstraints,
    SpellcastingConstraints,
)

from .catalog_loader import load_dnd5e_catalog_v0

logger = logging.getLogger(__name__)


class PCGRuleEngine:
    """
    Backend rule engine for PCG (levels 1–3).

    Responsibilities:
    - Load PCG-local catalogs (future: JSON middle layer)
    - Build GenerationConstraints deterministically from GenerationInput
    """

    def __init__(self) -> None:
        self._catalog = load_dnd5e_catalog_v0()

    def get_constraints(self, input_data: GenerationInput) -> GenerationConstraints:
        level = input_data.level
        if level < 1 or level > 3:
            raise ValueError("PCG backend rule engine only supports levels 1–3")

        cls = self._catalog.classes_by_id.get(input_data.class_id)
        if not cls:
            raise ValueError(f"Unknown classId: {input_data.class_id}")

        # Handle subrace selection: if subrace_id is provided, use it; otherwise use race_id
        race = None
        if input_data.subrace_id:
            race = self._catalog.races_by_id.get(input_data.subrace_id)
            if not race:
                raise ValueError(f"Unknown subraceId: {input_data.subrace_id}")
        else:
            race = self._catalog.races_by_id.get(input_data.race_id)
            if not race:
                raise ValueError(f"Unknown raceId: {input_data.race_id}")
            
            # Check if this is a base race that requires a subrace
            # Base races have baseRace == id (self-reference)
            # Subraces have baseRace != id (reference to parent)
            race_id = race.get("id")
            base_race = race.get("baseRace")
            
            # Check if there are subraces available for this race
            # (i.e., other races with baseRace == this race's id but id != this race's id)
            available_subraces = [
                r for r in self._catalog.races_by_id.values()
                if r.get("baseRace") == race_id and r.get("id") != race_id
            ]
            
            # If this is a base race (baseRace == id) and has subraces available, require subrace selection
            if base_race == race_id and available_subraces:
                subrace_names = [r["name"] for r in available_subraces]
                raise ValueError(
                    f"Race '{race['name']}' requires a subrace selection. "
                    f"Available subraces: {', '.join(subrace_names)}"
                )

        background = self._catalog.backgrounds_by_id.get(input_data.background_id)
        if not background:
            raise ValueError(f"Unknown backgroundId: {input_data.background_id}")

        class_constraints = ClassConstraints(
            id=cls["id"],
            name=cls["name"],
            hitDie=cls["hitDie"],
            primaryAbilities=cls["primaryAbilities"],
        )

        race_constraints = RaceConstraints(
            id=race["id"],
            name=race["name"],
            abilityBonuses=race.get("abilityBonuses", {}),
        )

        background_constraints = BackgroundConstraints(
            id=background["id"],
            name=background["name"],
            grantedSkills=background.get("grantedSkills", []),
        )

        skill_constraints = SkillConstraints(
            grantedByBackground=background.get("grantedSkills", []),
            classOptions=cls["skillChoices"]["from"],
            chooseCount=int(cls["skillChoices"]["choose"]),
            # 5e behavior: if background grants a class skill, you pick a different one.
            overlapHandling="replace",
        )

        equipment_packages = [
            EquipmentPackage(id=p["id"], description=p["description"], items=p["items"])
            for p in cls.get("equipmentPackages", [])
        ]

        feature_choices: List[FeatureChoice] = []
        feature_choices_by_level = cls.get("featureChoicesByLevel", {})
        for lvl_str in (str(l) for l in range(1, level + 1)):
            for fc in feature_choices_by_level.get(lvl_str, []):
                options = [
                    FeatureOption(id=o["id"], name=o["name"], description=o.get("description", ""))
                    for o in fc.get("options", [])
                ]
                feature_choices.append(
                    FeatureChoice(
                        featureId=fc["featureId"],
                        featureName=fc["featureName"],
                        options=options,
                    )
                )

        spellcasting: Optional[SpellcastingConstraints] = None
        spell_by_level = cls.get("spellcastingByLevel", {}) or {}
        spell_row = spell_by_level.get(str(level))
        if spell_row:
            spell_list_id = spell_row.get("spellListId")
            spell_list = self._catalog.spell_lists_by_id.get(spell_list_id, {}) if spell_list_id else {}

            cantrip_ids = spell_list.get("cantrips", []) or []
            spell_ids = spell_list.get("spells", []) or []

            max_spell_level = int(spell_row.get("maxSpellLevel", 1))
            available_cantrips = [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "level": int(s.get("level", 0)),
                    "school": s.get("school", ""),
                    "description": s.get("description", ""),
                }
                for sid in cantrip_ids
                if (s := self._catalog.spells_by_id.get(sid))
            ]
            available_spells = [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "level": int(s.get("level", 0)),
                    "school": s.get("school", ""),
                    "description": s.get("description", ""),
                }
                for sid in spell_ids
                if (s := self._catalog.spells_by_id.get(sid)) and int(s.get("level", 0)) <= max_spell_level and int(s.get("level", 0)) > 0
            ]

            spellcasting = SpellcastingConstraints(
                ability=spell_row["ability"],
                cantripsKnown=int(spell_row.get("cantripsKnown", 0)),
                spellsKnown=spell_row.get("spellsKnown"),
                casterType=spell_row.get("casterType"),
                preparedFormula=spell_row.get("preparedFormula"),
                maxSpellLevel=max_spell_level,
                spellListId=spell_list_id,
                pactSlots=spell_row.get("pactSlots"),
                pactSlotLevel=spell_row.get("pactSlotLevel"),
                availableCantrips=available_cantrips,
                availableSpells=available_spells,
            )

        logger.debug(
            "PCG constraints built | class=%s race=%s bg=%s level=%s features=%s spellcasting=%s",
            input_data.class_id,
            input_data.race_id,
            input_data.background_id,
            level,
            len(feature_choices),
            bool(spellcasting),
        )

        # NOTE: GenerationConstraints.equipment is modeled as a dict on the backend
        # for backwards compatibility. We populate it with the frontend shape:
        # {"packages": [...]}.
        return GenerationConstraints(
            **{
                "class": class_constraints,
                "race": race_constraints,
                "background": background_constraints,
                "skills": skill_constraints,
                "equipment": {"packages": equipment_packages},
                "featureChoices": feature_choices,
                "spellcasting": spellcasting,
            }
        )


