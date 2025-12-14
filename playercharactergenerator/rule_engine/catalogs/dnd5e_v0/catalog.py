"""
PCG "middle layer" catalog (v0).

Why python data instead of JSON?
- DungeonMindServer/.cursorignore blocks *.json in this repo for IDE performance,
  which prevents Cursor tool edits on JSON files.

Intended end-state:
- These structures move to JSON and are loaded by a future shared DungeonMindEngine.
"""

from typing import Any, Dict, List


RACES: List[Dict[str, Any]] = [
    {"id": "human", "name": "Human", "abilityBonuses": {}},
    {"id": "dwarf", "name": "Dwarf", "abilityBonuses": {"constitution": 2}},
    {"id": "elf", "name": "Elf", "abilityBonuses": {"dexterity": 2}},
    {"id": "halfling", "name": "Halfling", "abilityBonuses": {"dexterity": 2}},
    {"id": "half-orc", "name": "Half-Orc", "abilityBonuses": {"strength": 2, "constitution": 1}},
]


BACKGROUNDS: List[Dict[str, Any]] = [
    {"id": "soldier", "name": "Soldier", "grantedSkills": ["Athletics", "Intimidation"]},
    {"id": "sage", "name": "Sage", "grantedSkills": ["Arcana", "History"]},
    {"id": "criminal", "name": "Criminal", "grantedSkills": ["Deception", "Stealth"]},
    {"id": "acolyte", "name": "Acolyte", "grantedSkills": ["Insight", "Religion"]},
    {"id": "folk-hero", "name": "Folk Hero", "grantedSkills": ["Animal Handling", "Survival"]},
]


CLASSES: List[Dict[str, Any]] = [
    {
        "id": "fighter",
        "name": "Fighter",
        "hitDie": 10,
        "primaryAbilities": ["strength", "dexterity"],
        "skillChoices": {
            "choose": 2,
            "from": [
                "Acrobatics",
                "Animal Handling",
                "Athletics",
                "History",
                "Insight",
                "Intimidation",
                "Perception",
                "Survival",
            ],
        },
        "equipmentPackages": [
            {"id": "A", "description": "Chain mail + shield + martial weapon", "items": ["chain-mail", "shield", "martial-weapon-choice"]},
            {"id": "B", "description": "Leather armor + longbow + 20 arrows", "items": ["leather-armor", "longbow", "arrows-20"]},
        ],
        "featureChoicesByLevel": {
            "1": [
                {
                    "featureId": "fighter-fighting-style",
                    "featureName": "Fighting Style",
                    "options": [
                        {"id": "defense", "name": "Defense", "description": "While wearing armor, gain +1 AC."},
                        {"id": "dueling", "name": "Dueling", "description": "When wielding a melee weapon in one hand, +2 damage."},
                        {"id": "archery", "name": "Archery", "description": "Gain +2 to ranged weapon attack rolls."},
                    ],
                }
            ],
            "3": [
                {
                    "featureId": "fighter-subclass",
                    "featureName": "Martial Archetype",
                    "options": [
                        {"id": "champion", "name": "Champion", "description": "Simple, reliable martial excellence."},
                        {"id": "battle-master", "name": "Battle Master", "description": "Tactical maneuvers and battlefield control."},
                    ],
                }
            ],
        },
        "spellcastingByLevel": {},
    },
    {
        "id": "rogue",
        "name": "Rogue",
        "hitDie": 8,
        "primaryAbilities": ["dexterity"],
        "skillChoices": {
            "choose": 4,
            "from": [
                "Acrobatics",
                "Athletics",
                "Deception",
                "Insight",
                "Intimidation",
                "Investigation",
                "Perception",
                "Performance",
                "Persuasion",
                "Sleight of Hand",
                "Stealth",
            ],
        },
        "equipmentPackages": [
            {"id": "A", "description": "Rapier + shortbow + burglar's pack", "items": ["rapier", "shortbow", "arrows-20", "burglars-pack"]},
            {"id": "B", "description": "Shortsword + dagger + thief's tools", "items": ["shortsword", "dagger", "thieves-tools"]},
        ],
        "featureChoicesByLevel": {
            "3": [
                {
                    "featureId": "rogue-subclass",
                    "featureName": "Roguish Archetype",
                    "options": [
                        {"id": "thief", "name": "Thief", "description": "Quick hands, climbing, and practical skills."},
                        {"id": "assassin", "name": "Assassin", "description": "Infiltration and deadly first strikes."},
                    ],
                }
            ]
        },
        "spellcastingByLevel": {},
    },
    {
        "id": "wizard",
        "name": "Wizard",
        "hitDie": 6,
        "primaryAbilities": ["intelligence"],
        "skillChoices": {
            "choose": 2,
            "from": ["Arcana", "History", "Insight", "Investigation", "Medicine", "Religion"],
        },
        "equipmentPackages": [
            {"id": "A", "description": "Quarterstaff + component pouch + scholar's pack", "items": ["quarterstaff", "component-pouch", "scholars-pack"]},
            {"id": "B", "description": "Dagger + arcane focus + explorer's pack", "items": ["dagger", "arcane-focus", "explorers-pack"]},
        ],
        "featureChoicesByLevel": {
            "2": [
                {
                    "featureId": "wizard-subclass",
                    "featureName": "Arcane Tradition",
                    "options": [
                        {"id": "evocation", "name": "School of Evocation", "description": "Elemental power and raw damage."},
                        {"id": "illusion", "name": "School of Illusion", "description": "Deception, misdirection, and tricks."},
                    ],
                }
            ]
        },
        "spellcastingByLevel": {
            "1": {"ability": "intelligence", "cantripsKnown": 3, "casterType": "prepared", "preparedFormula": "abilityModPlusLevel", "maxSpellLevel": 1, "spellListId": "wizard-srd-l1-3"},
            "2": {"ability": "intelligence", "cantripsKnown": 3, "casterType": "prepared", "preparedFormula": "abilityModPlusLevel", "maxSpellLevel": 1, "spellListId": "wizard-srd-l1-3"},
            "3": {"ability": "intelligence", "cantripsKnown": 3, "casterType": "prepared", "preparedFormula": "abilityModPlusLevel", "maxSpellLevel": 2, "spellListId": "wizard-srd-l1-3"},
        },
    },
    {
        "id": "cleric",
        "name": "Cleric",
        "hitDie": 8,
        "primaryAbilities": ["wisdom"],
        "skillChoices": {
            "choose": 2,
            "from": ["History", "Insight", "Medicine", "Persuasion", "Religion"],
        },
        "equipmentPackages": [
            {"id": "A", "description": "Scale mail + shield + mace", "items": ["scale-mail", "shield", "mace"]},
            {"id": "B", "description": "Leather armor + light crossbow + 20 bolts", "items": ["leather-armor", "light-crossbow", "bolts-20"]},
        ],
        "featureChoicesByLevel": {
            "1": [
                {
                    "featureId": "cleric-subclass",
                    "featureName": "Divine Domain",
                    "options": [
                        {"id": "life", "name": "Life Domain", "description": "Healing and protection."},
                        {"id": "war", "name": "War Domain", "description": "Martial zeal and battle blessings."},
                    ],
                }
            ]
        },
        "spellcastingByLevel": {
            "1": {"ability": "wisdom", "cantripsKnown": 3, "casterType": "prepared", "preparedFormula": "abilityModPlusLevel", "maxSpellLevel": 1, "spellListId": "cleric-srd-l1-3"},
            "2": {"ability": "wisdom", "cantripsKnown": 3, "casterType": "prepared", "preparedFormula": "abilityModPlusLevel", "maxSpellLevel": 1, "spellListId": "cleric-srd-l1-3"},
            "3": {"ability": "wisdom", "cantripsKnown": 3, "casterType": "prepared", "preparedFormula": "abilityModPlusLevel", "maxSpellLevel": 2, "spellListId": "cleric-srd-l1-3"},
        },
    },
    {
        "id": "bard",
        "name": "Bard",
        "hitDie": 8,
        "primaryAbilities": ["charisma"],
        "skillChoices": {
            "choose": 3,
            "from": [
                "Acrobatics",
                "Animal Handling",
                "Arcana",
                "Athletics",
                "Deception",
                "History",
                "Insight",
                "Intimidation",
                "Investigation",
                "Medicine",
                "Nature",
                "Perception",
                "Performance",
                "Persuasion",
                "Religion",
                "Sleight of Hand",
                "Stealth",
                "Survival",
            ],
        },
        "equipmentPackages": [
            {"id": "A", "description": "Rapier + lute + entertainer's pack", "items": ["rapier", "lute", "entertainers-pack"]},
            {"id": "B", "description": "Longsword + flute + diplomat's pack", "items": ["longsword", "flute", "diplomats-pack"]},
        ],
        "featureChoicesByLevel": {
            "3": [
                {
                    "featureId": "bard-subclass",
                    "featureName": "Bard College",
                    "options": [
                        {"id": "lore", "name": "College of Lore", "description": "Knowledge, magic, and cutting words."},
                        {"id": "valor", "name": "College of Valor", "description": "Martial inspiration and battlefield presence."},
                    ],
                }
            ]
        },
        "spellcastingByLevel": {
            "1": {"ability": "charisma", "cantripsKnown": 2, "spellsKnown": 4, "casterType": "known", "maxSpellLevel": 1, "spellListId": "bard-srd-l1-3"},
            "2": {"ability": "charisma", "cantripsKnown": 2, "spellsKnown": 5, "casterType": "known", "maxSpellLevel": 1, "spellListId": "bard-srd-l1-3"},
            "3": {"ability": "charisma", "cantripsKnown": 2, "spellsKnown": 6, "casterType": "known", "maxSpellLevel": 2, "spellListId": "bard-srd-l1-3"},
        },
    },
]


# ============================================================================
# SPELLS (v0)
# ============================================================================

SPELLS: List[Dict[str, Any]] = [
    # --- Cantrips ---
    {"id": "fire-bolt", "name": "Fire Bolt", "level": 0, "school": "evocation", "description": "Ranged fire damage."},
    {"id": "mage-hand", "name": "Mage Hand", "level": 0, "school": "conjuration", "description": "Spectral hand manipulates objects at range."},
    {"id": "prestidigitation", "name": "Prestidigitation", "level": 0, "school": "transmutation", "description": "Minor magical tricks and utility."},
    {"id": "light", "name": "Light", "level": 0, "school": "evocation", "description": "Object sheds bright light."},
    {"id": "sacred-flame", "name": "Sacred Flame", "level": 0, "school": "evocation", "description": "Radiant damage, targets a creature."},
    {"id": "thaumaturgy", "name": "Thaumaturgy", "level": 0, "school": "transmutation", "description": "Minor divine wonders (voice, doors, tremors)."},
    {"id": "vicious-mockery", "name": "Vicious Mockery", "level": 0, "school": "enchantment", "description": "Psychic damage; disadvantage on next attack."},

    # --- Level 1 ---
    {"id": "magic-missile", "name": "Magic Missile", "level": 1, "school": "evocation", "description": "Auto-hit force darts."},
    {"id": "shield", "name": "Shield", "level": 1, "school": "abjuration", "description": "Reaction: +5 AC until start of your next turn."},
    {"id": "burning-hands", "name": "Burning Hands", "level": 1, "school": "evocation", "description": "Cone of fire damage."},
    {"id": "cure-wounds", "name": "Cure Wounds", "level": 1, "school": "evocation", "description": "Touch healing."},
    {"id": "healing-word", "name": "Healing Word", "level": 1, "school": "evocation", "description": "Bonus action ranged healing."},
    {"id": "guiding-bolt", "name": "Guiding Bolt", "level": 1, "school": "evocation", "description": "Radiant damage; next attack has advantage."},
    {"id": "shield-of-faith", "name": "Shield of Faith", "level": 1, "school": "abjuration", "description": "Bonus action: +2 AC concentration."},
    {"id": "dissonant-whispers", "name": "Dissonant Whispers", "level": 1, "school": "enchantment", "description": "Psychic damage; forced movement."},
    {"id": "thunderwave", "name": "Thunderwave", "level": 1, "school": "evocation", "description": "Thunder damage; pushes creatures away."},

    # --- Level 2 ---
    {"id": "mirror-image", "name": "Mirror Image", "level": 2, "school": "illusion", "description": "Defensive duplicates; harder to hit."},
    {"id": "misty-step", "name": "Misty Step", "level": 2, "school": "conjuration", "description": "Bonus action teleport."},
    {"id": "scorching-ray", "name": "Scorching Ray", "level": 2, "school": "evocation", "description": "Multiple ranged fire rays."},
    {"id": "spiritual-weapon", "name": "Spiritual Weapon", "level": 2, "school": "evocation", "description": "Bonus action force weapon attack; no concentration."},
    {"id": "lesser-restoration", "name": "Lesser Restoration", "level": 2, "school": "abjuration", "description": "Cures a disease or condition."},
    {"id": "shatter", "name": "Shatter", "level": 2, "school": "evocation", "description": "Thunder AoE damage; good vs objects."},
    {"id": "suggestion", "name": "Suggestion", "level": 2, "school": "enchantment", "description": "Magically influence a creature's actions."},
    {"id": "invisibility", "name": "Invisibility", "level": 2, "school": "illusion", "description": "Become invisible until you attack or cast."},
]


SPELL_LISTS: Dict[str, Dict[str, List[str]]] = {
    "wizard-srd-l1-3": {
        "cantrips": ["fire-bolt", "mage-hand", "prestidigitation", "light"],
        "spells": ["magic-missile", "shield", "burning-hands", "mirror-image", "misty-step", "scorching-ray", "invisibility"],
    },
    "cleric-srd-l1-3": {
        "cantrips": ["light", "sacred-flame", "thaumaturgy"],
        "spells": ["cure-wounds", "healing-word", "guiding-bolt", "shield-of-faith", "spiritual-weapon", "lesser-restoration"],
    },
    "bard-srd-l1-3": {
        "cantrips": ["vicious-mockery", "light", "prestidigitation"],
        "spells": ["healing-word", "dissonant-whispers", "thunderwave", "shatter", "suggestion", "invisibility"],
    },
}


