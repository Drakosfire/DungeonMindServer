# Field disposition: `StatBlockDetails` to Statblock v1

This table makes §9 of the v1 contract executable. “Derived by server” describes an
accepted-definition/revision operation, not a field added to `StatblockDefinitionV1`.

| Legacy field | Disposition | V1 destination |
|---|---|---|
| `name`, `size`, `type`, `subtype`, `alignment` | retained but restructured | `identity.name`, `.size`, `.creature_type`, `.subtypes`, `.alignment` |
| `armor_class` | retained but restructured | `defenses.armor_classes[]` |
| `hit_points`, `hit_dice` | retained but restructured | `vitality.hit_points` (`formula` or `fixed_value`) |
| `speed` | retained but restructured | `movement.modes[]` |
| `abilities` | retained directly | `abilities` using full ability names |
| `saving_throws`, `skills` | retained but restructured | `proficiencies.saving_throws[]`, `.skills[]` |
| `damage_resistance`, `damage_immunity`, `damage_vulnerability` | retained but restructured | `defenses.damage_interactions[]` |
| `condition_immunity` | retained but restructured | `defenses.condition_immunities[]` |
| `senses` | retained but restructured | `senses.senses[]`, `.passive_perception` |
| `languages` | retained but restructured | `communication.languages[]`, `.special_modes` |
| `challenge_rating` | retained but restructured | `challenge.rating` |
| `xp` | derived by server | selected ruleset, unless `challenge.xp_override` |
| `proficiency_bonus` | retained directly | **`challenge.proficiency_bonus` only** (single authored authority; not duplicated on `proficiencies`) |
| `actions`, `bonus_actions`, `reactions`, `special_abilities` | retained but restructured | `rule_elements[]` selected by `section` |
| `spells` | retained but restructured | spellcasting `rule_elements[]` |
| `legendary_actions.actions_per_turn` | retained but restructured | named `resources[]` pool (`maximum`) |
| `legendary_actions.description` | retained but restructured | `resources[key=legendary_actions].rules_text` (introductory legendary prose) |
| `legendary_actions.actions` | retained but restructured | `rule_elements[]` with costs |
| `lair_actions.initiative` | retained but restructured | `lair.initiative_count` |
| `lair_actions.lair_name` | retained directly | `lair.name` |
| `lair_actions.lair_description` | retained directly | `lair.description` (sensory / environmental) |
| `lair_actions.description` | retained but restructured | introductory lair-action mechanics prose carried on `lair_action` `rule_elements[].summary` / `.rules_text` (not a second authored copy on `lair`) |
| `lair_actions.actions` | retained but restructured | `rule_elements[]` with `section: lair_action` |
| `description` | retained but restructured | `flavor_text`; campaign description moves to DungeonBuddy |
| `sd_prompt` | moved to candidate envelope | `asset_brief` |
| `project_id` | removed | no v1 definition equivalent |
| `created_at` | moved to revision envelope | server-created revision metadata |
| `last_modified` | removed | immutable revisions replace mutation dates |
| `tags` | moved to DungeonBuddy | threat/logical-statblock metadata |

## Legacy `Action`

| Legacy field | Disposition | V1 destination |
|---|---|---|
| `name`, `desc` | retained directly | `RuleElement.name`, `.rules_text` |
| `attack_bonus` | retained but restructured | `AttackMechanic.attack_bonus` |
| `damage`, `damage_type` | retained but restructured | `DamageEffect.damage`, `.damage_type` |
| `range` | retained but restructured | attack reach/range/target |
| `recharge` | retained but restructured | `Usage.recharge_range` as `{minimum, maximum}` object |

## Legacy spell fields

| Legacy field | Disposition | V1 destination |
|---|---|---|
| `SpellcastingBlock` | retained but restructured | one or more spellcasting `rule_elements[]` |
| `SpellcastingBlock.level` | retained but restructured | `SpellcastingMechanic.caster_level` |
| `SpellcastingBlock.ability`, `.save_dc`, `.attack_bonus` | retained directly | spellcasting mechanic fields |
| `cantrips`, `known_spells` | retained but restructured | `SpellGroup[]` |
| level 1–9 slots | retained but restructured | slot-bearing `SpellGroup[]` with `usage.kind = spell_slots` (not `at_will`) |
| `Spell.name` | retained directly | `SpellRef.name` |
| `Spell.level` | retained but restructured | `SpellGroup.level` (sole level authority; not duplicated on `SpellRef`) |
| `Spell.school` | retained directly | `SpellRef.school` |
| `Spell.description` | retained but restructured | `SpellRef.rules_text` |
