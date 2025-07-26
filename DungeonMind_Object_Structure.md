# DungeonMind Object Structure
## Flexible TTRPG Content Data Model

### 🎯 **Design Philosophy**

DungeonMind objects are designed to be:
- **System-Agnostic**: Work across D&D, Pathfinder, and any TTRPG system
- **Completely Flexible**: All properties optional, extensible structure
- **AI-Translatable**: Models can convert between systems with context
- **Cross-Referenced**: Objects can link and relate to each other
- **Public by Default**: Built for sharing and collaboration

---

## 🏗️ **Core Object Structure**

### **Base Object Schema**
```typescript
interface DungeonMindObject {
  // Core Identity
  id: string;                    // Unique identifier
  type: ObjectType;              // Primary classification
  name: string;                  // Display name
  
  // Content
  description?: string;          // Rich text description
  summary?: string;              // Brief one-line summary
  tags?: string[];               // Searchable keywords
  
  // System Integration
  systemData?: Record<string, any>;  // System-specific properties
  rulesets?: string[];           // Compatible game systems
  
  // Relationships
  references?: Reference[];      // Links to other objects
  collections?: string[];        // Project/campaign associations
  
  // Metadata
  metadata: ObjectMetadata;      // Creation, ownership, sharing info
  
  // Extensibility
  customProperties?: Record<string, any>;  // User-defined fields
  
  // AI Enhancement
  aiContext?: AIContext;         // Generation history and prompts
  
  // Public Sharing
  visibility: 'private' | 'project' | 'public';
  sharePermissions?: SharePermissions;
}
```

---

## 🎮 **Object Types**

### **Primary Classifications**
```typescript
type ObjectType = 
  | 'item'           // Equipment, consumables, treasures
  | 'character'      // NPCs, PCs, creatures
  | 'location'       // Places, maps, environments  
  | 'encounter'      // Combat, social, exploration scenarios
  | 'ability'        // Spells, skills, features
  | 'rule'           // Mechanics, house rules, variants
  | 'campaign'       // Adventures, story arcs
  | 'organization'   // Factions, guilds, governments
  | 'event'          // Historical events, plot points
  | 'custom';        // User-defined content types
```

---

## 📦 **Specialized Object Schemas**

### **Item Objects**
```typescript
interface ItemObject extends DungeonMindObject {
  type: 'item';
  
  // Classification
  category?: 'weapon' | 'armor' | 'consumable' | 'tool' | 'treasure' | 'artifact';
  subcategory?: string;          // "longsword", "potion", "ring"
  
  // Properties
  rarity?: 'common' | 'uncommon' | 'rare' | 'very rare' | 'legendary' | 'artifact';
  value?: {
    amount: number;
    currency: string;            // "gp", "credits", "coins"
  };
  weight?: {
    amount: number;
    unit: string;                // "lbs", "kg", "stones"
  };
  
  // Mechanics
  properties?: string[];         // ["magical", "finesse", "two-handed"]
  damage?: {
    formula: string;             // "1d8+2"
    type: string;                // "slashing", "fire", "psychic"
  };
  armorClass?: {
    base: number;
    modifier?: string;           // "+Dex", "max 2"
  };
  
  // Usage
  charges?: {
    current: number;
    maximum: number;
    recharge?: string;           // "dawn", "short rest", "1d6 rounds"
  };
  requirements?: string[];       // ["attunement", "proficiency with martial weapons"]
  
  // Visual
  appearance?: string;           // Rich description of looks
  imageUrl?: string;             // Visual representation
}
```

### **Character Objects**
```typescript
interface CharacterObject extends DungeonMindObject {
  type: 'character';
  
  // Classification
  category?: 'npc' | 'pc' | 'creature' | 'monster';
  role?: string;                 // "merchant", "guard", "dragon", "villain"
  
  // Identity
  pronouns?: string;             // "they/them", "she/her", "it/its"
  age?: string;                  // "ancient", "middle-aged", "342 years"
  ancestry?: string;             // "elf", "human", "construct"
  background?: string;           // "noble", "soldier", "hermit"
  
  // Personality
  personality?: {
    traits?: string[];           // Notable characteristics
    ideals?: string[];           // Core beliefs
    bonds?: string[];            // Important connections
    flaws?: string[];            // Weaknesses or quirks
  };
  
  // Abilities
  stats?: Record<string, number>; // System-specific ability scores
  skills?: Record<string, number>; // Skill proficiencies
  features?: string[];           // Special abilities, spells, etc.
  
  // Combat
  hitPoints?: {
    current: number;
    maximum: number;
    temporary?: number;
  };
  armorClass?: number;
  speed?: Record<string, number>; // {"walk": 30, "fly": 60}
  
  // Equipment
  equipment?: Reference[];       // Links to item objects
  
  // Relationships
  affiliations?: Reference[];    // Organizations, factions
  allies?: Reference[];          // Other characters
  enemies?: Reference[];         // Hostile relationships
  
  // Story
  backstory?: string;            // Rich narrative background
  motivations?: string[];        // Current goals and drives
  secrets?: string[];            // Hidden information
}
```

### **Location Objects**
```typescript
interface LocationObject extends DungeonMindObject {
  type: 'location';
  
  // Classification  
  category?: 'settlement' | 'dungeon' | 'wilderness' | 'building' | 'room' | 'region';
  scale?: 'continental' | 'regional' | 'local' | 'encounter';
  
  // Geography
  climate?: string;              // "temperate", "arctic", "desert"
  terrain?: string[];            // ["forest", "mountainous", "coastal"]
  size?: string;                 // "village", "metropolis", "10x10 ft"
  
  // Population
  population?: {
    size: number;
    demographics?: Record<string, number>; // {"human": 60, "elf": 25, "dwarf": 15}
  };
  
  // Features
  landmarks?: Reference[];       // Notable sub-locations
  resources?: string[];          // Available materials, services
  dangers?: string[];            // Hazards, threats, challenges
  
  // Connections
  connections?: {
    location: Reference;
    method: string;              // "road", "portal", "secret passage"
    distance?: string;           // "3 days travel", "50 feet"
    difficulty?: string;         // "easy", "treacherous"
  }[];
  
  // Atmosphere
  atmosphere?: string;           // Rich sensory description
  sounds?: string[];             // Ambient audio
  smells?: string[];             // Distinctive scents
  lighting?: string;             // Light conditions
  
  // Map Data
  mapUrl?: string;               // Visual map reference
  coordinates?: {
    x: number;
    y: number;
    system?: string;             // Coordinate system reference
  };
}
```

### **Encounter Objects**
```typescript
interface EncounterObject extends DungeonMindObject {
  type: 'encounter';
  
  // Classification
  category?: 'combat' | 'social' | 'exploration' | 'puzzle' | 'stealth';
  difficulty?: 'trivial' | 'easy' | 'medium' | 'hard' | 'deadly';
  
  // Setup
  trigger?: string;              // How encounter begins
  location?: Reference;          // Where it takes place
  participants?: Reference[];    // Characters involved
  
  // Challenge
  objectives?: string[];         // Win conditions
  obstacles?: string[];          // Challenges to overcome
  complications?: string[];      // Potential twists
  
  // Resources
  enemies?: Reference[];         // Hostile creatures
  allies?: Reference[];          // Helpful characters
  environment?: string[];        // Environmental factors
  
  // Rewards
  experience?: number;           // XP value
  treasure?: Reference[];        // Item rewards
  story?: string[];              // Narrative outcomes
  
  // Scaling
  scalingNotes?: string;         // How to adjust difficulty
  alternatives?: string[];       // Different approach options
}
```

### **Ability Objects**
```typescript
interface AbilityObject extends DungeonMindObject {
  type: 'ability';
  
  // Classification
  category?: 'spell' | 'skill' | 'feature' | 'action' | 'reaction';
  school?: string;               // "evocation", "enchantment"
  level?: number;                // Spell level or ability tier
  
  // Usage
  castingTime?: string;          // "1 action", "10 minutes"
  duration?: string;             // "instantaneous", "1 hour", "concentration"
  range?: string;                // "touch", "60 feet", "self"
  components?: {
    verbal?: boolean;
    somatic?: boolean; 
    material?: string;           // Material component description
    cost?: number;               // Expensive component cost
  };
  
  // Mechanics
  effect?: string;               // What the ability does
  damage?: {
    formula: string;
    type: string;
    scaling?: string;            // Higher level effects
  };
  savingThrow?: {
    ability: string;             // "Dexterity", "Wisdom"
    difficulty?: number;         // DC value
    effect?: string;             // What happens on save/fail
  };
  
  // Prerequisites
  requirements?: string[];       // Class, level, feat requirements
  restrictions?: string[];       // Usage limitations
  
  // Progression
  advancement?: {
    level: number;
    enhancement: string;
  }[];
}
```

---

## 🔗 **Relationship System**

### **Reference Structure**
```typescript
interface Reference {
  id: string;                    // Target object ID
  type: ObjectType;              // What kind of object
  relationship: string;          // How they're connected
  context?: string;              // Additional details
  
  // Examples:
  // { id: "sword123", type: "item", relationship: "equipped", context: "main hand" }
  // { id: "tavern456", type: "location", relationship: "workplace", context: "bartender" }
  // { id: "quest789", type: "campaign", relationship: "participant", context: "main character" }
}
```

### **Relationship Types**
```typescript
type RelationshipType = 
  // Ownership/Usage
  | 'owns' | 'equipped' | 'carries' | 'created'
  
  // Location
  | 'located_in' | 'connected_to' | 'nearby' | 'origin'
  
  // Social
  | 'ally' | 'enemy' | 'neutral' | 'member' | 'leader' | 'subordinate'
  
  // Story
  | 'participant' | 'quest_giver' | 'objective' | 'reward'
  
  // Mechanical
  | 'prerequisite' | 'component' | 'enhancement' | 'counters'
  
  // Narrative
  | 'related' | 'inspired_by' | 'variant_of' | 'sequel_to';
```

---

## 📊 **Metadata System**

### **Object Metadata**
```typescript
interface ObjectMetadata {
  // Creation
  createdAt: number;             // Timestamp
  createdBy: string;             // User ID
  version: string;               // Semantic versioning
  
  // Modification
  updatedAt: number;
  updatedBy: string;
  changeLog?: ChangeEntry[];
  
  // Ownership
  owner: string;                 // User ID
  collaborators?: string[];      // Shared editing access
  
  // Origin
  source?: 'user_created' | 'ai_generated' | 'imported' | 'template';
  generator?: string;            // Which AI model/tool created it
  inspiration?: Reference[];     // What it was based on
  
  // Quality
  validated?: boolean;           // Has been reviewed
  rating?: number;               // Community rating (1-5)
  downloads?: number;            // Usage count
  
  // Publishing
  published?: boolean;           // Available publicly
  license?: string;              // Usage rights
  attribution?: string;          // Required credits
}

interface ChangeEntry {
  timestamp: number;
  user: string;
  action: 'created' | 'modified' | 'deleted' | 'shared';
  description?: string;
  fields?: string[];             // What was changed
}
```

---

## 🤖 **AI Integration**

### **AI Context**
```typescript
interface AIContext {
  // Generation
  originalPrompt?: string;       // What user requested
  systemPrompt?: string;         // AI instructions used
  model?: string;                // Which AI model generated it
  generatedAt?: number;          // When it was created
  
  // Enhancement
  suggestions?: AISuggestion[];  // Potential improvements
  alternatives?: Reference[];    // Other versions generated
  
  // Learning
  userFeedback?: 'positive' | 'negative' | 'neutral';
  improvements?: string[];       // How it was manually edited
  
  // Context
  relatedObjects?: Reference[];  // Objects used for context
  campaignStyle?: string;        // Tone/theme information
  systemContext?: string;        // Target game system info
}

interface AISuggestion {
  type: 'enhancement' | 'correction' | 'addition';
  field: string;                 // Which property to modify
  suggestion: string;            // Proposed change
  confidence: number;            // AI confidence (0-1)
  reasoning?: string;            // Why this suggestion
}
```

---

## 🌐 **Sharing & Permissions**

### **Share System**
```typescript
interface SharePermissions {
  // Public Access
  publicView?: boolean;          // Anyone can see
  publicUse?: boolean;           // Anyone can copy/use
  publicModify?: boolean;        // Anyone can suggest edits
  
  // Community
  communityRating?: boolean;     // Allow ratings/reviews
  communityComments?: boolean;   // Allow discussion
  communityDerivatives?: boolean; // Allow remixes/variants
  
  // Attribution
  requireAttribution?: boolean;  // Must credit creator
  allowCommercial?: boolean;     // Can be used commercially
  shareAlike?: boolean;          // Derivatives must be shared
  
  // Access Control
  allowedUsers?: string[];       // Specific user permissions
  allowedGroups?: string[];      // Group access
  
  // Integration
  vttExport?: boolean;           // Can export to VTT platforms
  apiAccess?: boolean;           // Available via MCP/API
}
```

---

## 🎲 **System-Specific Data**

### **Flexible System Integration**
```typescript
interface SystemData {
  [systemName: string]: {
    // Core conversion
    nativeEquivalent?: string;    // Official system object
    conversionNotes?: string;     // How to adapt
    
    // Mechanical
    stats?: Record<string, any>;  // System-specific numbers
    rules?: string[];             // Special mechanics
    
    // Balance
    powerLevel?: number;          // Relative strength
    restrictions?: string[];      // System limitations
    
    // Compatibility  
    tested?: boolean;             // Has been playtested
    issues?: string[];            // Known problems
    
    // Examples:
    // "dnd5e": { stats: { ac: 15, damage: "1d8+3" }, powerLevel: 3 }
    // "pathfinder": { nativeEquivalent: "longsword +1", tested: true }
    // "savage_worlds": { conversionNotes: "Use as Str+d8 weapon" }
  };
}
```

---

## 📁 **Collections & Organization**

### **Project Structure**
```typescript
interface ProjectCollection {
  id: string;
  name: string;
  description?: string;
  
  // Content
  objects: Reference[];          // All objects in project
  categories?: {
    [category: string]: Reference[];
  };
  
  // Campaign Integration
  timeline?: TimelineEvent[];    // Story progression
  maps?: Reference[];            // Location hierarchies
  sessions?: SessionRecord[];    // Play history
  
  // Sharing
  collaborators?: string[];      // Co-creators
  visibility: 'private' | 'shared' | 'public';
  
  // AI Enhancement
  style?: string;                // Narrative tone/theme
  systemPreference?: string;     // Primary game system
  autoTags?: boolean;            // AI-suggested tags
}

interface TimelineEvent {
  timestamp: number;             // In-world time
  title: string;
  description?: string;
  participants?: Reference[];    // Characters involved
  location?: Reference;          // Where it happened
  consequences?: Reference[];    // What changed
}
```

---

## 🔮 **MCP Server Integration**

### **MCP-Compatible Interface**
```typescript
interface MCPObjectRequest {
  // Input
  naturalLanguageDescription: string;
  targetSystem?: string;         // "dnd5e", "pathfinder", etc.
  context?: {
    campaign?: Reference;        // Existing campaign context
    relatedObjects?: Reference[]; // For consistency
    style?: string;              // Tone/theme preferences
  };
  
  // Output Preferences
  detailLevel: 'basic' | 'detailed' | 'complete';
  includeRelationships?: boolean;
  generateAlternatives?: number; // How many variants
  
  // Integration
  saveToProject?: string;        // Project ID to add to
  shareSettings?: SharePermissions;
}

interface MCPObjectResponse {
  // Generated Content
  objects: DungeonMindObject[];  // Primary results
  alternatives?: DungeonMindObject[]; // Variations
  
  // Relationships
  suggestedConnections?: Reference[];
  requiredObjects?: MCPObjectRequest[]; // Dependencies to create
  
  // Enhancement
  aiContext: AIContext;          // Generation metadata
  systemCompatibility?: string[]; // Which systems work well
  
  // Quality
  confidence: number;            // AI confidence in result
  completeness: number;          // How detailed it is
  warnings?: string[];           // Potential issues
}
```

---

## 🏗️ **Implementation Strategy**

### **Phase 1: Core Objects** (Current CardGenerator)
- ✅ Item objects with full schema
- 🔄 Basic relationship system
- 🔄 Simple sharing permissions

### **Phase 2: Character & Location**
- 📋 NPC/Character objects
- 📋 Location objects with connections
- 📋 Enhanced relationship mapping

### **Phase 3: Campaign Integration**
- 📋 Encounter objects
- 📋 Timeline and session tracking
- 📋 Project collection system

### **Phase 4: MCP & AI Enhancement**
- 📋 MCP server implementation
- 📋 Cross-object AI suggestions
- 📋 System translation capabilities

---

## 💡 **Example Object**

### **Complete Item Example**
```json
{
  "id": "item_fire_sword_001",
  "type": "item",
  "name": "Flamebrand",
  "description": "This elegant longsword bears runes that glow with inner fire...",
  "summary": "A magical longsword that deals fire damage",
  "tags": ["magical", "weapon", "fire", "sword"],
  
  "category": "weapon",
  "subcategory": "longsword",
  "rarity": "rare",
  "value": { "amount": 5000, "currency": "gp" },
  "weight": { "amount": 3, "unit": "lbs" },
  
  "properties": ["magical", "finesse", "fire"],
  "damage": {
    "formula": "1d8+1",
    "type": "slashing plus 1d6 fire"
  },
  
  "systemData": {
    "dnd5e": {
      "attackBonus": 1,
      "damageBonus": 1,
      "properties": ["finesse", "versatile"],
      "attunement": true
    },
    "pathfinder": {
      "enhancement": 1,
      "specialAbilities": ["flaming"]
    }
  },
  
  "references": [
    {
      "id": "npc_blacksmith_001", 
      "type": "character",
      "relationship": "created",
      "context": "forged by master smith"
    }
  ],
  
  "metadata": {
    "createdAt": 1640995200000,
    "createdBy": "user_12345",
    "version": "1.2.0",
    "source": "ai_generated",
    "published": true,
    "rating": 4.3
  },
  
  "aiContext": {
    "originalPrompt": "Create a magical fire sword for my campaign",
    "model": "gpt-4",
    "userFeedback": "positive"
  },
  
  "visibility": "public",
  "sharePermissions": {
    "publicView": true,
    "publicUse": true,
    "requireAttribution": true,
    "vttExport": true
  }
}
```

---

*This object structure provides the foundation for DungeonMind to become the comprehensive TTRPG content creation platform, supporting any game system while maintaining flexibility for future innovation and MCP server integration.* 