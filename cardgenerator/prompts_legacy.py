prompt_instructions = """ **Purpose**: ONLY Generate a structured inventory entry for a specific item as a hashmap. Do NOT reply with anything other than a hashmap.

**Instructions**:
1. Replace `{item}` with the name of the user item, DO NOT CHANGE THE USER ITEM NAME enclosed in single quotes (e.g., `'Magic Wand'`).
2. Weapons MUST have a key 'Damage' 
3. The description should be brief and punchy, or concise and thoughtful.
4. The quote should be richly detailed and from the perspective of someone commenting on the impact of the {item} on their life
5. **SD Prompt Requirements**: Create detailed, comprehensive image prompts that include:
   - **Subject**: Detailed description of the item's appearance, materials, and unique features
   - **Art Style**: Specify artistic approach (e.g., "fantasy concept art", "photorealistic", "medieval manuscript illustration")
   - **Composition**: Camera angle, framing, perspective (e.g., "dramatic low angle", "centered composition", "three-quarter view")
   - **Lighting**: Detailed lighting setup (e.g., "dramatic rim lighting", "soft ethereal glow", "harsh directional light")
   - **Atmosphere**: Mood and environmental elements (e.g., "mystical fog", "ancient chamber", "ethereal particles")
   - **Colors**: Specific color palette and materials (e.g., "deep obsidian black with silver inlay", "warm golden brass")
   - **Details**: Texture, weathering, magical effects, and fine details
   - **Quality Tags**: Include terms like "masterpiece", "highly detailed", "8k resolution", "professional concept art"
6. Value should be assigned as an integer of copper pieces (cp), silver pieces (sp), electrum pieces (ep), gold pieces (gp), and platinum pieces (pp). 
7. Use this table for reference on value : 

1 cp 	1 lb. of wheat
2 cp 	1 lb. of flour or one chicken
5 cp 	1 lb. of salt
1 sp 	1 lb. of iron or 1 sq. yd. of canvas
5 sp 	1 lb. of copper or 1 sq. yd. of cotton cloth
1 gp 	1 lb. of ginger or one goat
2 gp 	1 lb. of cinnamon or pepper, or one sheep
3 gp 	1 lb. of cloves or one pig
5 gp 	1 lb. of silver or 1 sq. yd. of linen
10 gp 	1 sq. yd. of silk or one cow
15 gp 	1 lb. of saffron or one ox
50 gp 	1 lb. of gold
500 gp 	1 lb. of platinum


300 gp +1 Melee or Ranged Weapon 
2000 gp +2 Melee or Ranged Weapon 
10000 gp  +3 Melee or Ranged Weapon 
300 gp +1 Armor Uncommon
2000 gp +2 Armor Rare
10000 gp +3 Armor Very Rare
300 gp +1 Shield Uncommon
2000 gp +2 Shield Rare
10000 gp +3 Shield Very Rare

8. Examples of Magical Scroll Value:
    Common: 50-100 gp
    Uncommon: 101-500 gp
    Rare: 501-5000 gp
    Very rare: 5001-50000 gp
    Legendary: 50001+ gp

A scroll's rarity depends on the spell's level:
    Cantrip-1: Common
    2-3: Uncommon
    4-5: Rare
    6-8: Very rare
    9: Legendary

9. Explanation of Mimics:
Mimics are shapeshifting predators able to take on the form of inanimate objects to lure creatures to their doom. In dungeons, these cunning creatures most often take the form of doors and chests, having learned that such forms attract a steady stream of prey.
Imitative Predators. Mimics can alter their outward texture to resemble wood, stone, and other basic materials, and they have evolved to assume the appearance of objects that other creatures are likely to come into contact with. A mimic in its altered form is nearly unrecognizable until potential prey blunders into its reach, whereupon the monster sprouts pseudopods and attacks.
When it changes shape, a mimic excretes an adhesive that helps it seize prey and weapons that touch it. The adhesive is absorbed when the mimic assumes its amorphous form and on parts the mimic uses to move itself.
Cunning Hunters. Mimics live and hunt alone, though they occasionally share their feeding grounds with other creatures. Although most mimics have only predatory intelligence, a rare few evolve greater cunning and the ability to carry on simple conversations in Common or Undercommon. Such mimics might allow safe passage through their domains or provide useful information in exchange for food.

    
- **Input Placeholder**:
    - "{item}": Replace with the item name, ensuring it's wrapped in single quotes.

**Output Examples**:
1. Cloak of Whispering Shadows Entry:
    
    {
    'Name': 'Cloak of Whispering Shadows',
    'Type': 'Cloak',
    'Rarity': 'Very Rare', 
    'Value': '7500 gp',
    'Properties': ["Grants invisibility in dim light or darkness","Allows communication with shadows for gathering information"],
    'Weight': '1 lb',
    'Description': "A cloak woven from the essence of twilight, blending its wearer into the shadows. Whispers of the past and present linger in its folds, offering secrets to those who listen.",
    'Quote': "In the embrace of night, secrets surface in the silent whispers of the dark.",
    'SD Prompt': "Fantasy concept art of an ornate hooded cloak made from deep indigo fabric that appears almost black, with intricate silver threadwork forming mystical runes along the edges, swirling shadow patterns that seem to move and shift across the surface, ethereal wisps of darkness flowing from the hem, dramatic side lighting casting deep shadows, three-quarter view showcasing the cloak's flowing form, rich velvet texture with subtle magical shimmer, wisps of dark energy emanating from the fabric, ancient mystical atmosphere, masterpiece quality, highly detailed, 8k resolution, professional fantasy art" 
    } 
    
2. Health Potion Entry:
    
    {
    'Rarity' : 'Common',
    'Value': '50 gp',
    'Properties': ["Quafable", "Restores 1d4 + 2 HP upon consumption"],
    'Weight': '0.5 lb',
    'Description': "Contained within this small vial is a crimson liquid that sparkles when shaken, a life-saving elixir for those who brave the unknown.",
    'Quote': "To the weary, a drop of hope; to the fallen, a chance to stand once more.",
    'SD Prompt' : "Photorealistic fantasy still life of a small crystal vial containing luminous crimson liquid with golden sparkles suspended throughout, cork stopper with wax seal, sitting on ancient wooden table, soft warm backlighting creating internal glow within the potion, shallow depth of field, macro lens perspective, rich burgundy and gold color palette, glass surface reflections, condensation droplets on exterior, warm candlelight illumination, medieval apothecary atmosphere, highly detailed textures, professional product photography, 8k resolution, masterpiece quality" 
    } 
    
3. Wooden Shield Entry:
    
    {
    'Name' : "Wooden Shield",
    'Type' : 'Armor, Shield',
    'Rarity' : 'Common',
    'Value' : '2 gp',
    'Properties' : ['Made of wood','Provides protection','May use a bonus action to Shove','AC + 2'],
    'Weight' : '6 lb',
    'Description' : "A simple round shield fashioned from sturdy oak, banded with iron. Scarred from use but still reliable, this shield shows the marks of countless battles fought by warriors in defense of their allies.",
    'Quote' : "Behind this humble oak, I stood when the world tried to beat me down. It's not much, but it's mine, and it's enough.",
    'SD Prompt': "fantasy medieval wooden round shield made of oak planks bound with iron bands, battle-scarred surface with scratches and dents, natural wood grain texture, worn leather grip on back, medieval craftsmanship, realistic proportions, muted brown and amber tones, soft natural lighting, three-quarter angle view, highly detailed wood texture, professional prop photography, 8k resolution, masterpiece quality"
    }
    
4. Acid Vial Entry:
    
    {
    'Name' : "Acid",
    'Type' : 'Adventuring Gear',
    'Rarity' : 'Common',
    'Value' : '25 gp',
    'Properties' : ['Throwable','As an action, you can splash the contents of this vial onto a creature within 5 feet of you or throw the vial up to 20 feet, shattering it on impact. In either case, make a ranged attack against a creature or object, treating the acid as an improvised weapon. On a hit, the target takes 2d6 acid damage.'],
    'Damage Formula' : 'Improvised weapon 2d6 acid damage',
    'Weight' : '1 lb',
    'Description' : "A glass vial containing a highly corrosive green acid that bubbles and hisses menacingly. The liquid seems to eat away at the very air around it, warning of its destructive potential.",
    'Quote' : "Watched it melt through a lock faster than any key ever could. Just wish I hadn't gotten any on my boots.",
    'SD Prompt': "Fantasy alchemy vial containing bright green bubbling acid, corrosive liquid with small bubbles rising to surface, glass container with cork stopper, slight green glow emanating from contents, wisps of vapor rising from liquid surface, dangerous chemical warning signs, medieval laboratory setting, detailed glass reflections, caustic green color palette with amber highlights, dramatic lighting casting green shadows, professional product photography style, highly detailed, 8k resolution, masterpiece quality"
    }
    
5. Bedroll Entry:
    
    {
    'Name' : "Bedroll",
    'Type' : 'Adventuring Gear',
    'Rarity' : 'Common',
    'Value' : '2 sp',
    'Properties' : ['Portable sleeping equipment','Provides basic comfort while resting outdoors'],
    'Weight' : '7 lb',
    'Description' : "A simple but essential piece of adventuring gear consisting of a wool-stuffed mattress and waterproof canvas covering. Designed to provide basic comfort during long journeys and nights spent under the stars.",
    'Quote' : "After walking twenty miles in muddy boots, even the hardest ground feels like a feather bed when you've got your trusty bedroll.",
    'SD Prompt': "medieval fantasy bedroll made of canvas and wool, rolled up and secured with leather straps, weathered fabric showing signs of travel, natural earth tones of brown and tan, sitting beside a campfire in outdoor setting, soft natural lighting, detailed fabric texture showing wear and durability, cozy camping atmosphere, professional outdoor gear photography, highly detailed, 8k resolution, masterpiece quality"
    }
    
6. Component Pouch Entry:
    
    {
    'Name' : "Component Pouch",
    'Type' : 'Adventuring Gear',
    'Rarity' : 'Common',
    'Value' : '25 gp',
    'Properties' : ['Spellcasting focus','Contains material components for spells','Can be used as a spellcasting focus for spells that require material components'],
    'Weight' : '2 lb',
    'Description' : "A small leather pouch filled with carefully organized spell components - herbs, crystals, powders, and other mystical materials. Each compartment holds precisely what a spellcaster needs to weave magic into reality.",
    'Quote' : "Every ingredient has its place, every component its purpose. Magic isn't just about power - it's about preparation.",
    'SD Prompt': "fantasy spellcaster component pouch made of rich brown leather with multiple small compartments, filled with colorful magical ingredients, sparkling crystals, dried herbs, mystical powders, brass buckles and straps, magical shimmer emanating from contents, detailed leather craftsmanship, warm lighting highlighting textures, medieval fantasy aesthetic, professional product photography, highly detailed, 8k resolution, masterpiece quality"
    }
    
7. Handaxe Entry:
    
    {
    'Name' : "Handaxe",
    'Type' : 'Simple Melee Weapon',
    'Rarity' : 'Common',
    'Value' : '5 gp',
    'Properties' : ['Light','Thrown (range 20/60)','Versatile tool and weapon'],
    'Damage Formula' : '1d6 slashing',
    'Weight' : '2 lb',
    'Description' : "A practical tool that doubles as a weapon, featuring a sharp steel head mounted on a sturdy wooden handle. Equally useful for chopping wood around camp or defending against threats on the road.",
    'Quote' : "It's split more firewood than skulls, but when trouble comes calling, it does both jobs just fine.",
    'SD Prompt': "medieval fantasy handaxe with sharp steel blade and wooden handle, practical tool design, weathered metal with slight rust patina, worn wooden grip showing use, balanced proportions for throwing, natural lighting emphasizing blade edge, detailed metal and wood textures, traditional blacksmith craftsmanship, earth tone color palette, professional weapon photography, highly detailed, 8k resolution, masterpiece quality"
    }
    
8. Dagger Entry:

    {
    'Name' : "Dagger",
    'Type' : 'Simple Melee Weapon',
    'Rarity' : 'Common',
    'Value' : '2 gp',
    'Properties' : ['Finesse','Light','Thrown (range 20/60)'],
    'Damage Formula' : '1d4 piercing',
    'Weight' : '1 lb',
    'Description' : "A sleek, double-edged blade designed for quick strikes and precise work. Whether worn openly or concealed, this versatile weapon serves rogues and warriors alike as both tool and weapon.",
    'Quote' : "Small enough to hide, sharp enough to matter. Sometimes the best blade is the one they never see coming.",
    'SD Prompt': "medieval fantasy dagger with polished steel double-edged blade, leather-wrapped handle with brass crossguard, sharp pointed tip perfect for thrusting, sleek and deadly design, detailed metalwork with slight reflections, dark leather grip showing wear, balanced proportions, dramatic lighting highlighting blade edge, professional weapon photography, medieval craftsmanship, highly detailed, 8k resolution, masterpiece quality"
    }

9. Mace Entry:

    {
    'Name' : "Mace",
    'Type' : 'Simple Melee Weapon', 
    'Rarity' : 'Common',
    'Value' : '5 gp',
    'Properties' : ['Versatile bludgeoning weapon','Effective against armor'],
    'Damage Formula' : '1d6 bludgeoning',
    'Weight' : '4 lb',
    'Description' : "A heavy weapon featuring a reinforced head of iron or steel mounted on a solid wooden shaft. Designed to crush through armor and bone with devastating blunt force, favored by clerics and warriors alike.",
    'Quote' : "Armor means nothing when the blow comes down like a hammer. Simple, brutal, effective - just how I like my weapons.",
    'SD Prompt': "medieval fantasy mace with heavy iron head featuring flanged ridges, solid wooden handle with leather grip, imposing bludgeoning weapon design, dark metal with weathered surface, traditional medieval craftsmanship, intimidating proportions, dramatic lighting emphasizing weight and mass, detailed metal and wood textures, professional weapon photography, earth tones with metallic highlights, highly detailed, 8k resolution, masterpiece quality"
    }
"""