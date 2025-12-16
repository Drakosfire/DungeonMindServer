"""
Tests for subrace handling in PCG rule engine.

Tests verify:
- Subrace lookup in catalog
- get_constraints() with subrace_id
- Validation that base races requiring subraces are rejected
- Ability bonuses from subraces are correctly applied
"""

import pytest
from playercharactergenerator.models.pcg_models import GenerationInput
from playercharactergenerator.rule_engine import PCGRuleEngine


class TestSubraceCatalog:
    """Test that subraces are available in the catalog"""

    def test_subraces_exist_in_catalog(self):
        """Verify all expected subraces are in the catalog"""
        engine = PCGRuleEngine()
        catalog = engine._catalog

        # Dwarf subraces
        assert "hill-dwarf" in catalog.races_by_id
        assert "mountain-dwarf" in catalog.races_by_id
        
        # Elf subraces
        assert "high-elf" in catalog.races_by_id
        assert "wood-elf" in catalog.races_by_id
        
        # Halfling subraces
        assert "lightfoot-halfling" in catalog.races_by_id
        assert "stout-halfling" in catalog.races_by_id
        
        # Gnome subraces
        assert "forest-gnome" in catalog.races_by_id
        assert "rock-gnome" in catalog.races_by_id

    def test_subraces_have_base_race_field(self):
        """Verify subraces have baseRace field linking to base race"""
        engine = PCGRuleEngine()
        catalog = engine._catalog

        hill_dwarf = catalog.races_by_id["hill-dwarf"]
        assert hill_dwarf.get("baseRace") == "dwarf"

        high_elf = catalog.races_by_id["high-elf"]
        assert high_elf.get("baseRace") == "elf"

        lightfoot_halfling = catalog.races_by_id["lightfoot-halfling"]
        assert lightfoot_halfling.get("baseRace") == "halfling"

        forest_gnome = catalog.races_by_id["forest-gnome"]
        assert forest_gnome.get("baseRace") == "gnome"

    def test_subraces_have_correct_ability_bonuses(self):
        """Verify subraces have correct ability bonuses"""
        engine = PCGRuleEngine()
        catalog = engine._catalog

        # Hill Dwarf: +2 CON, +1 WIS
        hill_dwarf = catalog.races_by_id["hill-dwarf"]
        assert hill_dwarf["abilityBonuses"]["constitution"] == 2
        assert hill_dwarf["abilityBonuses"]["wisdom"] == 1

        # Mountain Dwarf: +2 CON, +2 STR
        mountain_dwarf = catalog.races_by_id["mountain-dwarf"]
        assert mountain_dwarf["abilityBonuses"]["constitution"] == 2
        assert mountain_dwarf["abilityBonuses"]["strength"] == 2

        # High Elf: +2 DEX, +1 INT
        high_elf = catalog.races_by_id["high-elf"]
        assert high_elf["abilityBonuses"]["dexterity"] == 2
        assert high_elf["abilityBonuses"]["intelligence"] == 1

        # Wood Elf: +2 DEX, +1 WIS
        wood_elf = catalog.races_by_id["wood-elf"]
        assert wood_elf["abilityBonuses"]["dexterity"] == 2
        assert wood_elf["abilityBonuses"]["wisdom"] == 1

        # Lightfoot Halfling: +2 DEX, +1 CHA
        lightfoot = catalog.races_by_id["lightfoot-halfling"]
        assert lightfoot["abilityBonuses"]["dexterity"] == 2
        assert lightfoot["abilityBonuses"]["charisma"] == 1

        # Stout Halfling: +2 DEX, +1 CON
        stout = catalog.races_by_id["stout-halfling"]
        assert stout["abilityBonuses"]["dexterity"] == 2
        assert stout["abilityBonuses"]["constitution"] == 1

        # Forest Gnome: +2 INT, +1 DEX
        forest_gnome = catalog.races_by_id["forest-gnome"]
        assert forest_gnome["abilityBonuses"]["intelligence"] == 2
        assert forest_gnome["abilityBonuses"]["dexterity"] == 1

        # Rock Gnome: +2 INT, +1 CON
        rock_gnome = catalog.races_by_id["rock-gnome"]
        assert rock_gnome["abilityBonuses"]["intelligence"] == 2
        assert rock_gnome["abilityBonuses"]["constitution"] == 1


class TestSubraceConstraints:
    """Test get_constraints() with subrace selection"""

    def test_get_constraints_with_subrace_id(self):
        """Verify get_constraints works when subrace_id is provided"""
        engine = PCGRuleEngine()

        input_data = GenerationInput(
            classId="fighter",
            raceId="dwarf",  # Base race (will be ignored)
            subraceId="hill-dwarf",  # Subrace (should be used)
            level=1,
            backgroundId="soldier",
            concept="A sturdy hill dwarf warrior",
        )

        constraints = engine.get_constraints(input_data)

        # Should use subrace, not base race
        assert constraints.race.id == "hill-dwarf"
        assert constraints.race.name == "Hill Dwarf"
        
        # Should have subrace ability bonuses
        assert constraints.race.ability_bonuses["constitution"] == 2
        assert constraints.race.ability_bonuses["wisdom"] == 1

    def test_get_constraints_with_subrace_as_race_id(self):
        """Verify get_constraints works when race_id is a subrace ID"""
        engine = PCGRuleEngine()

        input_data = GenerationInput(
            classId="wizard",
            raceId="high-elf",  # Subrace ID used as race_id
            level=1,
            backgroundId="sage",
            concept="A scholarly high elf wizard",
        )

        constraints = engine.get_constraints(input_data)

        # Should use the subrace
        assert constraints.race.id == "high-elf"
        assert constraints.race.name == "High Elf"
        
        # Should have subrace ability bonuses
        assert constraints.race.ability_bonuses["dexterity"] == 2
        assert constraints.race.ability_bonuses["intelligence"] == 1

    def test_get_constraints_rejects_base_race_requiring_subrace(self):
        """Verify get_constraints rejects base races that require subraces"""
        engine = PCGRuleEngine()

        # Dwarf requires subrace
        input_data = GenerationInput(
            classId="fighter",
            raceId="dwarf",  # Base race without subrace
            level=1,
            backgroundId="soldier",
            concept="A dwarf warrior",
        )

        with pytest.raises(ValueError) as exc_info:
            engine.get_constraints(input_data)

        error_msg = str(exc_info.value)
        assert "requires a subrace selection" in error_msg
        assert "Hill Dwarf" in error_msg or "Mountain Dwarf" in error_msg

    def test_get_constraints_rejects_elf_without_subrace(self):
        """Verify get_constraints rejects elf without subrace"""
        engine = PCGRuleEngine()

        input_data = GenerationInput(
            classId="ranger",
            raceId="elf",  # Base race without subrace
            level=1,
            backgroundId="folk-hero",
            concept="An elf ranger",
        )

        with pytest.raises(ValueError) as exc_info:
            engine.get_constraints(input_data)

        error_msg = str(exc_info.value)
        assert "requires a subrace selection" in error_msg
        assert "High Elf" in error_msg or "Wood Elf" in error_msg

    def test_get_constraints_rejects_halfling_without_subrace(self):
        """Verify get_constraints rejects halfling without subrace"""
        engine = PCGRuleEngine()

        input_data = GenerationInput(
            classId="rogue",
            raceId="halfling",  # Base race without subrace
            level=1,
            backgroundId="criminal",
            concept="A halfling rogue",
        )

        with pytest.raises(ValueError) as exc_info:
            engine.get_constraints(input_data)

        error_msg = str(exc_info.value)
        assert "requires a subrace selection" in error_msg

    def test_get_constraints_rejects_gnome_without_subrace(self):
        """Verify get_constraints rejects gnome without subrace"""
        engine = PCGRuleEngine()

        input_data = GenerationInput(
            classId="wizard",
            raceId="gnome",  # Base race without subrace
            level=1,
            backgroundId="sage",
            concept="A gnome wizard",
        )

        with pytest.raises(ValueError) as exc_info:
            engine.get_constraints(input_data)

        error_msg = str(exc_info.value)
        assert "requires a subrace selection" in error_msg

    def test_get_constraints_allows_races_without_subraces(self):
        """Verify get_constraints allows races that don't require subraces"""
        engine = PCGRuleEngine()

        # Human doesn't require subrace
        input_data = GenerationInput(
            classId="fighter",
            raceId="human",
            level=1,
            backgroundId="soldier",
            concept="A human fighter",
        )

        constraints = engine.get_constraints(input_data)
        assert constraints.race.id == "human"
        assert constraints.race.name == "Human"

        # Half-Orc doesn't require subrace
        input_data2 = GenerationInput(
            classId="fighter",  # Use fighter instead of barbarian (not in catalog)
            raceId="half-orc",
            level=1,
            backgroundId="soldier",
            concept="A half-orc fighter",
        )

        constraints2 = engine.get_constraints(input_data2)
        assert constraints2.race.id == "half-orc"
        assert constraints2.race.name == "Half-Orc"


class TestSubraceEndToEnd:
    """End-to-end tests with subraces"""

    def test_hill_dwarf_fighter_constraints(self):
        """Test complete constraint building for Hill Dwarf Fighter"""
        engine = PCGRuleEngine()

        input_data = GenerationInput(
            classId="fighter",
            raceId="hill-dwarf",
            level=1,
            backgroundId="soldier",
            concept="A sturdy hill dwarf defender",
        )

        constraints = engine.get_constraints(input_data)

        # Verify race constraints
        assert constraints.race.id == "hill-dwarf"
        assert constraints.race.name == "Hill Dwarf"
        assert constraints.race.ability_bonuses["constitution"] == 2
        assert constraints.race.ability_bonuses["wisdom"] == 1

        # Verify class constraints
        assert constraints.class_info.id == "fighter"
        assert constraints.class_info.name == "Fighter"

    def test_wood_elf_ranger_constraints(self):
        """Test complete constraint building for Wood Elf Ranger"""
        engine = PCGRuleEngine()

        input_data = GenerationInput(
            classId="ranger",
            raceId="wood-elf",
            level=1,
            backgroundId="folk-hero",
            concept="A swift wood elf tracker",
        )

        constraints = engine.get_constraints(input_data)

        # Verify race constraints
        assert constraints.race.id == "wood-elf"
        assert constraints.race.name == "Wood Elf"
        assert constraints.race.ability_bonuses["dexterity"] == 2
        assert constraints.race.ability_bonuses["wisdom"] == 1

        # Verify class constraints
        assert constraints.class_info.id == "ranger"
        assert constraints.class_info.name == "Ranger"

    def test_mountain_dwarf_paladin_constraints(self):
        """Test complete constraint building for Mountain Dwarf Paladin"""
        engine = PCGRuleEngine()

        input_data = GenerationInput(
            classId="paladin",
            raceId="mountain-dwarf",
            level=1,
            backgroundId="noble",
            concept="A strong mountain dwarf champion",
        )

        constraints = engine.get_constraints(input_data)

        # Verify race constraints
        assert constraints.race.id == "mountain-dwarf"
        assert constraints.race.name == "Mountain Dwarf"
        assert constraints.race.ability_bonuses["constitution"] == 2
        assert constraints.race.ability_bonuses["strength"] == 2

        # Verify class constraints
        assert constraints.class_info.id == "paladin"
        assert constraints.class_info.name == "Paladin"

