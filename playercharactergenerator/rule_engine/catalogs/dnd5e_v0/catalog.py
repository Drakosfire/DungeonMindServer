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
    # Base races (kept for backward compatibility, but subraces are preferred)
    {"id": "human", "name": "Human", "abilityBonuses": {"strength": 1, "dexterity": 1, "constitution": 1, "intelligence": 1, "wisdom": 1, "charisma": 1}},
    {"id": "dwarf", "name": "Dwarf", "abilityBonuses": {"constitution": 2}, "baseRace": "dwarf"},
    {"id": "elf", "name": "Elf", "abilityBonuses": {"dexterity": 2}, "baseRace": "elf"},
    {"id": "halfling", "name": "Halfling", "abilityBonuses": {"dexterity": 2}, "baseRace": "halfling"},
    {"id": "half-orc", "name": "Half-Orc", "abilityBonuses": {"strength": 2, "constitution": 1}},
    {"id": "dragonborn", "name": "Dragonborn", "abilityBonuses": {"strength": 2, "charisma": 1}},
    {"id": "gnome", "name": "Gnome", "abilityBonuses": {"intelligence": 2}, "baseRace": "gnome"},
    {"id": "half-elf", "name": "Half-Elf", "abilityBonuses": {"charisma": 2}},
    {"id": "tiefling", "name": "Tiefling", "abilityBonuses": {"charisma": 2, "intelligence": 1}},
    
    # Dwarf subraces
    {"id": "hill-dwarf", "name": "Hill Dwarf", "baseRace": "dwarf", "abilityBonuses": {"constitution": 2, "wisdom": 1}},
    {"id": "mountain-dwarf", "name": "Mountain Dwarf", "baseRace": "dwarf", "abilityBonuses": {"constitution": 2, "strength": 2}},
    
    # Elf subraces
    {"id": "high-elf", "name": "High Elf", "baseRace": "elf", "abilityBonuses": {"dexterity": 2, "intelligence": 1}},
    {"id": "wood-elf", "name": "Wood Elf", "baseRace": "elf", "abilityBonuses": {"dexterity": 2, "wisdom": 1}},
    
    # Halfling subraces
    {"id": "lightfoot-halfling", "name": "Lightfoot Halfling", "baseRace": "halfling", "abilityBonuses": {"dexterity": 2, "charisma": 1}},
    {"id": "stout-halfling", "name": "Stout Halfling", "baseRace": "halfling", "abilityBonuses": {"dexterity": 2, "constitution": 1}},
    
    # Gnome subraces
    {"id": "forest-gnome", "name": "Forest Gnome", "baseRace": "gnome", "abilityBonuses": {"intelligence": 2, "dexterity": 1}},
    {"id": "rock-gnome", "name": "Rock Gnome", "baseRace": "gnome", "abilityBonuses": {"intelligence": 2, "constitution": 1}},
]


BACKGROUNDS: List[Dict[str, Any]] = [
    {"id": "soldier", "name": "Soldier", "grantedSkills": ["Athletics", "Intimidation"]},
    {"id": "sage", "name": "Sage", "grantedSkills": ["Arcana", "History"]},
    {"id": "criminal", "name": "Criminal", "grantedSkills": ["Deception", "Stealth"]},
    {"id": "acolyte", "name": "Acolyte", "grantedSkills": ["Insight", "Religion"]},
    {"id": "folk-hero", "name": "Folk Hero", "grantedSkills": ["Animal Handling", "Survival"]},
    {"id": "noble", "name": "Noble", "grantedSkills": ["History", "Persuasion"]},
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
    {
        "id": "warlock",
        "name": "Warlock",
        "hitDie": 8,
        "primaryAbilities": ["charisma"],
        "skillChoices": {
            "choose": 2,
            "from": ["Arcana", "Deception", "History", "Intimidation", "Investigation", "Nature", "Religion"],
        },
        "equipmentPackages": [
            {"id": "A", "description": "Leather armor + light crossbow + arcane focus", "items": ["leather-armor", "light-crossbow", "bolts-20", "arcane-focus"]},
            {"id": "B", "description": "Leather armor + dagger + component pouch", "items": ["leather-armor", "dagger", "component-pouch"]},
        ],
        "featureChoicesByLevel": {
            "1": [
                {
                    "featureId": "warlock-patron",
                    "featureName": "Otherworldly Patron",
                    "options": [
                        {"id": "fiend", "name": "The Fiend", "description": "Fire, bargains, and ruthless power."},
                        {"id": "archfey", "name": "The Archfey", "description": "Charm, illusions, and fey trickery."},
                    ],
                }
            ],
            "3": [
                {
                    "featureId": "warlock-pact-boon",
                    "featureName": "Pact Boon",
                    "options": [
                        {"id": "chain", "name": "Pact of the Chain", "description": "A familiar with extra capabilities."},
                        {"id": "blade", "name": "Pact of the Blade", "description": "Conjure a pact weapon; martial leaning."},
                        {"id": "tome", "name": "Pact of the Tome", "description": "Extra cantrips and ritual flavor."},
                    ],
                }
            ],
        },
        "spellcastingByLevel": {
            "1": {"ability": "charisma", "cantripsKnown": 2, "spellsKnown": 2, "casterType": "known", "maxSpellLevel": 1, "pactSlots": 1, "pactSlotLevel": 1, "spellListId": "warlock-srd-l1-3"},
            "2": {"ability": "charisma", "cantripsKnown": 2, "spellsKnown": 3, "casterType": "known", "maxSpellLevel": 1, "pactSlots": 2, "pactSlotLevel": 1, "spellListId": "warlock-srd-l1-3"},
            "3": {"ability": "charisma", "cantripsKnown": 2, "spellsKnown": 4, "casterType": "known", "maxSpellLevel": 2, "pactSlots": 2, "pactSlotLevel": 2, "spellListId": "warlock-srd-l1-3"},
        },
    },
    {
        "id": "paladin",
        "name": "Paladin",
        "hitDie": 10,
        "primaryAbilities": ["strength", "charisma"],
        "skillChoices": {
            "choose": 2,
            "from": ["Athletics", "Insight", "Intimidation", "Medicine", "Persuasion", "Religion"],
        },
        "equipmentPackages": [
            {"id": "A", "description": "Chain mail + shield + martial weapon", "items": ["chain-mail", "shield", "martial-weapon-choice"]},
            {"id": "B", "description": "Leather armor + shield + martial weapon", "items": ["leather-armor", "shield", "martial-weapon-choice"]},
        ],
        "featureChoicesByLevel": {
            "2": [
                {
                    "featureId": "paladin-fighting-style",
                    "featureName": "Fighting Style",
                    "options": [
                        {"id": "defense", "name": "Defense", "description": "While wearing armor, gain +1 AC."},
                        {"id": "dueling", "name": "Dueling", "description": "When wielding a melee weapon in one hand, +2 damage."},
                    ],
                }
            ],
            "3": [
                {
                    "featureId": "paladin-oath",
                    "featureName": "Sacred Oath",
                    "options": [
                        {"id": "devotion", "name": "Oath of Devotion", "description": "Honesty, courage, compassion."},
                        {"id": "vengeance", "name": "Oath of Vengeance", "description": "Relentless pursuit of justice."},
                    ],
                }
            ],
        },
        "spellcastingByLevel": {
            # Half-caster: paladin begins spellcasting at level 2
            "2": {"ability": "charisma", "cantripsKnown": 0, "casterType": "prepared", "preparedFormula": "abilityModPlusHalfLevel", "maxSpellLevel": 1, "spellListId": "paladin-srd-l1-3"},
            "3": {"ability": "charisma", "cantripsKnown": 0, "casterType": "prepared", "preparedFormula": "abilityModPlusHalfLevel", "maxSpellLevel": 1, "spellListId": "paladin-srd-l1-3"},
        },
    },
    {
        "id": "ranger",
        "name": "Ranger",
        "hitDie": 10,
        "primaryAbilities": ["dexterity", "wisdom"],
        "skillChoices": {
            "choose": 3,
            "from": ["Animal Handling", "Athletics", "Insight", "Investigation", "Nature", "Perception", "Stealth", "Survival"],
        },
        "equipmentPackages": [
            {"id": "A", "description": "Scale mail + two shortswords + dungeoneer's pack", "items": ["scale-mail", "shortsword", "shortsword", "dungeoneers-pack"]},
            {"id": "B", "description": "Leather armor + longbow + 20 arrows + explorer's pack", "items": ["leather-armor", "longbow", "arrows-20", "explorers-pack"]},
        ],
        "featureChoicesByLevel": {
            "2": [
                {
                    "featureId": "ranger-fighting-style",
                    "featureName": "Fighting Style",
                    "options": [
                        {"id": "archery", "name": "Archery", "description": "Gain +2 to ranged weapon attack rolls."},
                        {"id": "defense", "name": "Defense", "description": "While wearing armor, gain +1 AC."},
                        {"id": "dueling", "name": "Dueling", "description": "When wielding a melee weapon in one hand, +2 damage."},
                    ],
                }
            ],
            "3": [
                {
                    "featureId": "ranger-subclass",
                    "featureName": "Ranger Archetype",
                    "options": [
                        {"id": "hunter", "name": "Hunter", "description": "Relentless predator tactics and martial versatility."},
                        {"id": "beast-master", "name": "Beast Master", "description": "A loyal animal companion fights at your side."},
                    ],
                }
            ],
        },
        "spellcastingByLevel": {
            # Half-caster: ranger begins spellcasting at level 2, but is a known-caster (spells known table).
            "2": {"ability": "wisdom", "cantripsKnown": 0, "spellsKnown": 2, "casterType": "known", "maxSpellLevel": 1, "spellListId": "ranger-srd-l2-3"},
            "3": {"ability": "wisdom", "cantripsKnown": 0, "spellsKnown": 3, "casterType": "known", "maxSpellLevel": 1, "spellListId": "ranger-srd-l2-3"},
        },
    },
]


# ============================================================================
# SPELLS (v0)
# ============================================================================

SPELLS: List[Dict[str, Any]] = [
    # --- Cantrips ---
    {"id": "fire-bolt", "name": "Fire Bolt", "level": 0, "school": "evocation", "description": "Ranged spell attack; fire damage (damage)."},
    {"id": "mage-hand", "name": "Mage Hand", "level": 0, "school": "conjuration", "description": "Utility: spectral hand manipulates objects at range (utility)."},
    {"id": "prestidigitation", "name": "Prestidigitation", "level": 0, "school": "transmutation", "description": "Utility: minor magical tricks and effects (utility)."},
    {"id": "light", "name": "Light", "level": 0, "school": "evocation", "description": "Utility: object sheds bright light (utility)."},
    {"id": "sacred-flame", "name": "Sacred Flame", "level": 0, "school": "evocation", "description": "Radiant damage against a creature (damage)."},
    {"id": "thaumaturgy", "name": "Thaumaturgy", "level": 0, "school": "transmutation", "description": "Utility: minor divine wonders (utility)."},
    {"id": "vicious-mockery", "name": "Vicious Mockery", "level": 0, "school": "enchantment", "description": "Psychic damage; control via disadvantage on next attack (damage, control)."},
    {"id": "eldritch-blast", "name": "Eldritch Blast", "level": 0, "school": "evocation", "description": "Ranged spell attack; force damage (damage, attack)."},
    {"id": "ray-of-frost", "name": "Ray of Frost", "level": 0, "school": "evocation", "description": "Cold damage; control via reduced speed (damage, control, cold)."},
    {"id": "minor-illusion", "name": "Minor Illusion", "level": 0, "school": "illusion", "description": "Utility: create a sound or image (utility, illusion)."},
    {"id": "guidance", "name": "Guidance", "level": 0, "school": "divination", "description": "Buff: add d4 to an ability check (buff, utility)."},
    {"id": "spare-the-dying", "name": "Spare the Dying", "level": 0, "school": "necromancy", "description": "Healing: stabilize a creature at 0 HP (healing)."},
    {"id": "friends", "name": "Friends", "level": 0, "school": "enchantment", "description": "Utility/control: advantage on Charisma checks vs one creature (utility, control)."},

    # --- Level 1 ---
    {"id": "magic-missile", "name": "Magic Missile", "level": 1, "school": "evocation", "description": "Force damage that auto-hits (damage)."},
    {"id": "shield", "name": "Shield", "level": 1, "school": "abjuration", "description": "Protection: reaction +5 AC (protection, defense)."},
    {"id": "burning-hands", "name": "Burning Hands", "level": 1, "school": "evocation", "description": "Cone of fire damage (damage, fire)."},
    {"id": "cure-wounds", "name": "Cure Wounds", "level": 1, "school": "evocation", "description": "Healing via touch (healing)."},
    {"id": "healing-word", "name": "Healing Word", "level": 1, "school": "evocation", "description": "Healing at range as a bonus action (healing)."},
    {"id": "guiding-bolt", "name": "Guiding Bolt", "level": 1, "school": "evocation", "description": "Radiant damage; buff via advantage on next attack (damage, buff)."},
    {"id": "shield-of-faith", "name": "Shield of Faith", "level": 1, "school": "abjuration", "description": "Protection: +2 AC concentration (protection, defense)."},
    {"id": "dissonant-whispers", "name": "Dissonant Whispers", "level": 1, "school": "enchantment", "description": "Psychic damage; control via forced movement (damage, control)."},
    {"id": "thunderwave", "name": "Thunderwave", "level": 1, "school": "evocation", "description": "Thunder damage; control via push (damage, control)."},
    {"id": "hex", "name": "Hex", "level": 1, "school": "enchantment", "description": "Curse: extra damage; control via disadvantage on checks (damage, control)."},
    {"id": "armor-of-agathys", "name": "Armor of Agathys", "level": 1, "school": "abjuration", "description": "Protection: temp HP; cold damage to attackers (protection, damage, cold)."},
    {"id": "hellish-rebuke", "name": "Hellish Rebuke", "level": 1, "school": "evocation", "description": "Reaction: fire damage to attacker (damage, fire)."},
    {"id": "bless", "name": "Bless", "level": 1, "school": "enchantment", "description": "Buff: add d4 to attacks and saves (buff)."},
    {"id": "wrathful-smite", "name": "Wrathful Smite", "level": 1, "school": "evocation", "description": "Buff + damage: psychic damage; control via frighten (buff, damage, control)."},
    {"id": "hunters-mark", "name": "Hunter's Mark", "level": 1, "school": "divination", "description": "Buff: mark target; extra damage and tracking (buff, damage, utility)."},
    {"id": "goodberry", "name": "Goodberry", "level": 1, "school": "transmutation", "description": "Healing + utility: berries heal and provide nourishment (healing, utility)."},
    {"id": "ensnaring-strike", "name": "Ensnaring Strike", "level": 1, "school": "conjuration", "description": "Control: restrain target with vines (control)."},
    {"id": "mage-armor", "name": "Mage Armor", "level": 1, "school": "abjuration", "description": "Protection: increase AC without armor (protection, defense)."},
    {"id": "sleep", "name": "Sleep", "level": 1, "school": "enchantment", "description": "Control: put creatures to sleep (control)."},
    {"id": "detect-magic", "name": "Detect Magic", "level": 1, "school": "divination", "description": "Utility ritual: sense magic nearby (utility, ritual)."},
    {"id": "identify", "name": "Identify", "level": 1, "school": "divination", "description": "Utility ritual: learn properties of a magic item (utility, ritual)."},
    {"id": "feather-fall", "name": "Feather Fall", "level": 1, "school": "transmutation", "description": "Utility: slow falling to prevent damage (utility)."},
    {"id": "charm-person", "name": "Charm Person", "level": 1, "school": "enchantment", "description": "Control: charm a humanoid (control)."},
    {"id": "command", "name": "Command", "level": 1, "school": "enchantment", "description": "Control: force a creature to follow a one-word command (control)."},
    {"id": "bane", "name": "Bane", "level": 1, "school": "enchantment", "description": "Control: subtract d4 from attacks and saves (control)."},
    {"id": "sanctuary", "name": "Sanctuary", "level": 1, "school": "abjuration", "description": "Protection: ward a creature; attackers must save (protection)."},
    {"id": "heroism", "name": "Heroism", "level": 1, "school": "enchantment", "description": "Buff: temp HP each round; immune to fear (buff, protection)."},
    {"id": "disguise-self", "name": "Disguise Self", "level": 1, "school": "illusion", "description": "Utility: magical disguise (utility, illusion)."},
    {"id": "faerie-fire", "name": "Faerie Fire", "level": 1, "school": "evocation", "description": "Control: outline targets; attacks have advantage (control, buff)."},
    {"id": "tashas-hideous-laughter", "name": "Tasha's Hideous Laughter", "level": 1, "school": "enchantment", "description": "Control: incapacitate a creature with laughter (control)."},
    {"id": "arms-of-hadar", "name": "Arms of Hadar", "level": 1, "school": "conjuration", "description": "Damage + control: necrotic damage; prevent reactions (damage, control)."},
    {"id": "witch-bolt", "name": "Witch Bolt", "level": 1, "school": "evocation", "description": "Lightning damage sustained by a magical tether (damage, lightning)."},
    {"id": "divine-favor", "name": "Divine Favor", "level": 1, "school": "evocation", "description": "Buff: your weapon attacks deal extra radiant damage (buff, damage)."},
    {"id": "fog-cloud", "name": "Fog Cloud", "level": 1, "school": "conjuration", "description": "Control: heavily obscured area with fog (control)."},
    {"id": "speak-with-animals", "name": "Speak with Animals", "level": 1, "school": "divination", "description": "Utility: communicate with beasts (utility)."},
    {"id": "longstrider", "name": "Longstrider", "level": 1, "school": "transmutation", "description": "Buff: increase movement speed (buff, utility)."},

    # --- Level 2 ---
    {"id": "mirror-image", "name": "Mirror Image", "level": 2, "school": "illusion", "description": "Protection: defensive duplicates; harder to hit (protection)."},
    {"id": "misty-step", "name": "Misty Step", "level": 2, "school": "conjuration", "description": "Utility: bonus action teleport (utility)."},
    {"id": "scorching-ray", "name": "Scorching Ray", "level": 2, "school": "evocation", "description": "Fire damage with multiple rays (damage, fire)."},
    {"id": "spiritual-weapon", "name": "Spiritual Weapon", "level": 2, "school": "evocation", "description": "Damage: bonus action force weapon attack (damage)."},
    {"id": "lesser-restoration", "name": "Lesser Restoration", "level": 2, "school": "abjuration", "description": "Healing/restoration: cure a disease or condition (healing, restoration)."},
    {"id": "shatter", "name": "Shatter", "level": 2, "school": "evocation", "description": "Thunder damage in an area (damage)."},
    {"id": "suggestion", "name": "Suggestion", "level": 2, "school": "enchantment", "description": "Control: influence a creature's actions (control)."},
    {"id": "invisibility", "name": "Invisibility", "level": 2, "school": "illusion", "description": "Utility: become invisible (utility)."},
    {"id": "darkness", "name": "Darkness", "level": 2, "school": "evocation", "description": "Control: magical darkness blocks vision (control)."},
    {"id": "hold-person", "name": "Hold Person", "level": 2, "school": "enchantment", "description": "Control: paralyze a humanoid (control)."},
    {"id": "web", "name": "Web", "level": 2, "school": "conjuration", "description": "Control: restrain creatures in sticky webs (control)."},
    {"id": "levitate", "name": "Levitate", "level": 2, "school": "transmutation", "description": "Utility/control: move a creature or object vertically (utility, control)."},
    {"id": "blur", "name": "Blur", "level": 2, "school": "illusion", "description": "Protection: attacks against you have disadvantage (protection, buff)."},
    {"id": "silence", "name": "Silence", "level": 2, "school": "illusion", "description": "Control/utility: silence in an area; blocks spells with verbal components (control, utility)."},
    {"id": "aid", "name": "Aid", "level": 2, "school": "abjuration", "description": "Healing/buff: increase max HP and heal (healing, buff)."},
    {"id": "calm-emotions", "name": "Calm Emotions", "level": 2, "school": "enchantment", "description": "Control: suppress strong emotions; end charm/fear (control)."},
    {"id": "enhance-ability", "name": "Enhance Ability", "level": 2, "school": "transmutation", "description": "Buff: grant advantage on ability checks (buff, utility)."},
]


SPELL_LISTS: Dict[str, Dict[str, List[str]]] = {
    "wizard-srd-l1-3": {
        "cantrips": ["fire-bolt", "ray-of-frost", "mage-hand", "minor-illusion", "prestidigitation", "light"],
        "spells": [
            "magic-missile",
            "shield",
            "mage-armor",
            "burning-hands",
            "sleep",
            "detect-magic",
            "identify",
            "feather-fall",
            "charm-person",
            "disguise-self",
            "tashas-hideous-laughter",
            "mirror-image",
            "misty-step",
            "scorching-ray",
            "invisibility",
            "web",
            "levitate",
            "blur",
        ],
    },
    "cleric-srd-l1-3": {
        "cantrips": ["guidance", "light", "sacred-flame", "thaumaturgy", "spare-the-dying"],
        "spells": [
            "cure-wounds",
            "healing-word",
            "guiding-bolt",
            "shield-of-faith",
            "bless",
            "bane",
            "command",
            "sanctuary",
            "detect-magic",
            "spiritual-weapon",
            "lesser-restoration",
            "aid",
            "silence",
        ],
    },
    "bard-srd-l1-3": {
        "cantrips": ["vicious-mockery", "friends", "minor-illusion", "light", "prestidigitation"],
        "spells": [
            "healing-word",
            "cure-wounds",
            "dissonant-whispers",
            "thunderwave",
            "charm-person",
            "disguise-self",
            "faerie-fire",
            "sleep",
            "tashas-hideous-laughter",
            "shatter",
            "suggestion",
            "invisibility",
            "calm-emotions",
            "enhance-ability",
        ],
    },
    "warlock-srd-l1-3": {
        "cantrips": ["eldritch-blast", "minor-illusion", "mage-hand", "prestidigitation", "light"],
        "spells": [
            "hex",
            "armor-of-agathys",
            "hellish-rebuke",
            "arms-of-hadar",
            "witch-bolt",
            "charm-person",
            "hold-person",
            "darkness",
            "misty-step",
            "mirror-image",
            "suggestion",
        ],
    },
    "paladin-srd-l1-3": {
        "cantrips": [],
        "spells": [
            "bless",
            "cure-wounds",
            "shield-of-faith",
            "wrathful-smite",
            "divine-favor",
            "command",
            "heroism",
            "lesser-restoration",
            "aid",
        ],
    },
    "ranger-srd-l2-3": {
        "cantrips": [],
        "spells": [
            "hunters-mark",
            "goodberry",
            "ensnaring-strike",
            "fog-cloud",
            "longstrider",
            "speak-with-animals",
            "cure-wounds",
        ],
    },
}


