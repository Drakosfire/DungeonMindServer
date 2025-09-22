# StatBlockGenerator Design Document

## Project Overview

The StatBlockGenerator is a comprehensive web application that allows users to create custom D&D 5e creature statblocks through a structured 5-step workflow. The project integrates AI-powered text generation, creature image generation, 3D model creation, and custom HTML rendering to produce high-quality, professionally formatted D&D creature statblocks with full project management and state persistence capabilities.

## Technical Architecture

### Backend (Python/FastAPI)
- **Framework**: FastAPI with modular router structure
- **Location**: `/DungeonMindServer/routers/statblockgenerator_router.py`
- **Core Components**:
  - `statblock_generator.py`: Main statblock composition and validation logic
  - `statblock_prompts.py`: GPT-5 prompts for creature generation with versioned prompt management
  - `statblock_html_renderer.py`: HTML template generation and rendering
  - `statblockgenerator_router.py`: Comprehensive API endpoints for statblock generation and project management
  - `statblockgenerator_project_router.py`: Project-specific endpoints
  - `statblockgenerator_compatibility_router.py`: Legacy compatibility endpoints

### Frontend (React/TypeScript)
- **Framework**: React with TypeScript
- **Location**: `/LandingPage/src/components/StatBlockGenerator/`
- **UI Library**: Mantine Core components with custom design system
- **Architecture**: Component-based with comprehensive state management
  - Local state for UI interactions
  - Project-based persistence with Firestore integration
  - Real-time auto-save functionality
  - Generation lock system to prevent navigation during async operations

### External Services
- **AI Text Generation**: OpenAI GPT-4 with structured output validation for D&D 5e statblocks
- **Image Generation**: Fal.ai Flux for creature artwork generation
- **3D Model Generation**: Tripo3D API for converting 2D images to 3D models
- **Image Storage**: Cloudflare Images and R2 for CDN delivery
- **Database**: Firestore for project persistence and session management

## Current Feature Set

### 1. Five-Step Workflow System
**Components**: `Step1CreatureDescription.tsx`, `Step2CreatureImage.tsx`, `Step3StatblockCustomization.tsx`, `Step4ModelGeneration.tsx`, `Step5ExportFinalization.tsx`

#### Step 1: Creature Description
- **Component**: `Step1CreatureDescription.tsx` with `CreatureForm.tsx`
- **Functionality**: AI-powered creature statblock generation
- **Input**: Natural language creature description with options for spellcaster and legendary actions
- **Processing**: GPT-4 structured output with D&D 5e JSON schema validation
- **Output**: Complete statblock data structure including all core D&D stats, abilities, actions, spells, and descriptive text

#### Step 2: Creature Image Generation
- **Component**: `Step2CreatureImage.tsx`
- **Functionality**: Generate creature artwork using AI
- **Process**: Uses SD prompt from Step 1 to generate thematic creature images
- **Features**: 
  - Multiple image variants (4 per generation)
  - Image selection interface
  - Re-generation with prompt modifications
- **Output**: High-quality creature artwork for statblock integration

#### Step 3: Statblock Customization
- **Component**: `Step3StatblockCustomization.tsx`
- **Functionality**: Comprehensive statblock editing and validation
- **Features**: 
  - Editable forms for all D&D 5e statblock fields
  - Dynamic visibility for optional sections (spells, legendary actions)
  - Real-time validation and error checking
  - Challenge Rating calculations and recommendations
  - Ability score modifier calculations
- **Output**: Finalized and validated creature statblock

#### Step 4: 3D Model Generation
- **Component**: `Step4ModelGeneration.tsx`
- **Functionality**: Convert 2D creature image to 3D model
- **Features**:
  - Tripo3D API integration
  - Model preview and rotation
  - Download options (.glb format)
  - Progress tracking for model generation
- **Status**: Implementation planned
- **Output**: 3D model file for VTT or 3D printing use

#### Step 5: Export & Finalization
- **Component**: `Step5ExportFinalization.tsx`
- **Functionality**: Generate final outputs and export options
- **Features**:
  - HTML statblock preview with D&D 5e styling
  - PDF export generation
  - Multiple format options (JSON, XML, Roll20, etc.)
  - Print-optimized layouts
  - Final creature preview with image integration

### 2. Project Management System
**Components**: `StatBlockProjectsDrawer.tsx`, `CreateStatBlockProjectModal.tsx`, `StatBlockProjectCard.tsx`

#### Core Features
- **Project Creation**: Named statblock collections with descriptions
- **Auto-Save**: Real-time state persistence across all steps
- **Project Switching**: Seamless navigation between creature projects
- **Project Operations**: Save, load, duplicate, delete, export
- **Search & Filter**: Find projects by name, creature type, or challenge rating
- **Project Metadata**: Creation date, last modified, creature count, total CR

#### State Persistence Architecture
```typescript
interface StatBlockGeneratorState {
  currentStepId: string;
  stepCompletion: Record<string, boolean>;
  creatureDetails: StatBlockDetails;
  selectedAssets: {
    creatureImage?: string;
    selectedImageIndex?: number;
    generatedImages: string[];
    modelFile?: string;
  };
  generatedContent: {
    images: GeneratedImage[];
    models: Generated3DModel[];
    exports: GeneratedExport[];
  };
  autoSaveEnabled: boolean;
  lastSaved?: string;
}
```

### 3. Shared Component System
**Location**: `/LandingPage/src/components/StatBlockGenerator/shared/`

#### Statblock Display Components
- **StatBlockPreview.tsx**: Real-time statblock preview with D&D 5e styling
- **StatBlockEditor.tsx**: Comprehensive editing interface for all statblock fields
- **AbilityScoreCalculator.tsx**: Interactive ability score and modifier calculator
- **ChallengeRatingCalculator.tsx**: CR calculation based on offensive/defensive metrics

#### Image and Model Management
- **CreatureImageGallery.tsx**: Image selection and management interface
- **Model3DViewer.tsx**: 3D model preview and interaction component
- **ExportModal.tsx**: Multi-format export options and download management

#### Integration Status
- ✅ Statblock preview and editing components
- ✅ Image gallery with selection
- 🔄 3D model viewer (planned)
- 🔄 Export system (planned)

### 4. Generation Lock System
**Purpose**: Prevent navigation during async operations
**Implementation**: 
- Tracks generation state across all steps
- Disables navigation and project switching during generation
- Provides visual feedback for ongoing operations (AI generation, image creation, model processing)
- Prevents data loss during long-running AI operations

### 5. Navigation & UI Components
**Components**: `StatBlockStepNavigation.tsx`, `StatBlockHeader.tsx`

#### Step Navigation
- Visual step progression with completion indicators
- D&D-themed step icons and descriptions
- Responsive design for mobile and desktop
- Generation lock integration
- Keyboard navigation support

#### Header Integration
- Project management integration
- Save status indicators
- Export quick-actions
- Responsive design with mobile optimization

## Data Model Architecture

### Core StatBlock Interface
```typescript
interface StatBlockDetails {
  // Basic Information
  name: string;
  size: CreatureSize; // "Tiny" | "Small" | "Medium" | "Large" | "Huge" | "Gargantuan"
  type: CreatureType; // "aberration" | "beast" | "celestial" | etc.
  subtype?: string;
  alignment: Alignment;

  // Combat Statistics
  armorClass: number;
  hitPoints: number;
  hitDice: string;
  speed: SpeedObject;

  // Ability Scores
  abilities: AbilityScores;
  savingThrows: SavingThrows;
  skills: Skills;

  // Resistances and Senses
  damageResistance?: string;
  damageImmunity?: string;
  conditionImmunity?: string;
  senses: SensesObject;
  languages: string;

  // Challenge and Experience
  challengeRating: number | string; // Supports fractions like "1/4", "1/2"
  xp: number;

  // Actions and Abilities
  actions: Action[];
  bonusActions?: Action[];
  reactions?: Action[];
  spells?: SpellcastingBlock;
  legendaryActions?: LegendaryActionsBlock;
  lairActions?: LairActionsBlock;

  // Descriptive Content
  description: string;
  sdPrompt: string;

  // Project Integration
  projectId?: string;
  createdAt?: string;
  lastModified?: string;
  tags?: string[];
}
```

### Supporting Type Definitions
```typescript
interface AbilityScores {
  str: number;
  dex: number;
  con: number;
  int: number;
  wis: number;
  cha: number;
}

interface SpeedObject {
  walk?: number;
  fly?: number;
  swim?: number;
  climb?: number;
  burrow?: number;
}

interface Action {
  name: string;
  desc: string;
  attackBonus?: number;
  damage?: string;
  damageType?: string;
  range?: string;
  recharge?: string; // "5-6", "6", etc.
}

interface SpellcastingBlock {
  level: number;
  ability: string;
  save: number;
  attack: number;
  cantrips?: Spell[];
  knownSpells?: Spell[];
  spellSlots: SpellSlots;
}
```

## Test Infrastructure & Quality Assurance

### Test Suite Architecture ✅
- **Location**: `DungeonMindServer/tests/statblockgenerator/`
- **Framework**: pytest with async support and OpenAI integration
- **Coverage**: 31 comprehensive unit tests covering all core functionality
- **Test Categories**: 
  - Unit tests (fast, no external API calls)
  - Integration tests (with mocked services)
  - Live tests (real OpenAI API validation)
  - Performance benchmarks and reliability tests

### Test Runner System ✅
- **Custom Test Runner**: `run_tests.py` with intelligent environment loading
- **Environment Management**: Automatic .env file detection and loading
- **API Key Validation**: OpenAI API key verification and masking
- **Test Selection**: Marker-based test filtering (unit/integration/live/fast)
- **Performance Tracking**: Execution time monitoring and reporting

### Recent Test Infrastructure Fixes ✅
1. **Pytest Configuration**: Fixed `[tool:pytest]` → `[pytest]` section header issue
2. **Schema Validation**: Updated tests for Pydantic v2 `$ref` structure compatibility  
3. **Field Alias Handling**: Resolved `AbilityScores.int` field access in validation
4. **Marker System**: Proper test categorization with strict marker validation
5. **All Tests Passing**: 31/31 tests now pass successfully

### Test Coverage Areas ✅
- **Model Validation**: Pydantic schema validation and serialization
- **Generation Logic**: AI-powered creature generation workflows
- **D&D Rules Validation**: Challenge rating calculation and rule compliance
- **Performance Benchmarks**: Model creation, schema generation, validation speed
- **Error Handling**: Comprehensive error scenarios and edge cases
- **Integration Scenarios**: End-to-end workflow testing

## Technical Implementation Details

### Backend Data Processing
- **Statblock Validation**: D&D 5e rules compliance checking
- **CR Calculation**: Automated challenge rating computation based on offensive/defensive metrics
- **HTML Generation**: Template-based rendering with embedded D&D 5e CSS styling
- **Export Processing**: Multi-format export generation (PDF, JSON, XML, VTT formats)
- **Project Persistence**: Firestore integration with real-time sync

### Frontend State Management
- **Local State**: React hooks for UI interactions and form management
- **Persistent State**: Firestore integration for project and session persistence
- **Validation State**: Real-time validation feedback and error handling
- **Generation State**: Progress tracking for AI operations and model generation

### API Endpoints
#### Core Generation
- `POST /api/statblockgenerator/generate-creature`: Complete creature generation
- `POST /api/statblockgenerator/generate-creature-image`: Creature artwork generation
- `POST /api/statblockgenerator/generate-3d-model`: 3D model creation from image
- `POST /api/statblockgenerator/validate-statblock`: D&D 5e validation
- `POST /api/statblockgenerator/calculate-cr`: Challenge rating calculation

#### Project Management
- `POST /api/statblockgenerator/create-project`: Create new statblock project
- `GET /api/statblockgenerator/list-projects`: List user's statblock projects
- `GET /api/statblockgenerator/project/{project_id}`: Load specific project
- `PUT /api/statblockgenerator/project/{project_id}`: Update project
- `DELETE /api/statblockgenerator/project/{project_id}`: Delete project
- `POST /api/statblockgenerator/project/{project_id}/duplicate`: Duplicate project

#### Export and Rendering
- `POST /api/statblockgenerator/render-html`: Generate HTML statblock
- `POST /api/statblockgenerator/export-pdf`: Generate PDF export
- `POST /api/statblockgenerator/export-json`: Export statblock data
- `POST /api/statblockgenerator/export-vtt`: Generate VTT-compatible formats

#### Session Management
- `POST /api/statblockgenerator/save-session`: Auto-save and manual save
- `GET /api/statblockgenerator/load-session`: Session restoration
- `DELETE /api/statblockgenerator/delete-session`: Session cleanup

## Current UI/UX Features

### Responsive Design
- Mobile-first approach optimized for creature creation on any device
- Collapsible project drawer for mobile statblock editing
- Touch-friendly form controls and image selection
- Adaptive layouts for different screen sizes

### Visual Design System
- **Color Scheme**: D&D-themed color palette with fantasy aesthetics
- **Typography**: D&D-appropriate fonts (serif for statblocks, fantasy for headers)
- **Component Cohesion**: Consistent Mantine-based design system with D&D styling
- **Accessibility**: ARIA labels, keyboard navigation, and screen reader support

### User Experience
- **Workflow Clarity**: Clear step progression with D&D-themed visual indicators
- **Error Handling**: Comprehensive validation with helpful D&D rules guidance
- **Progress Indication**: Real-time save status and generation progress
- **Result Management**: Full project persistence and multi-format export

## Completed Features

### ✅ Planning & Design (COMPLETED)
1. **Architecture Design**: Complete technical architecture following CardGenerator patterns
2. **Data Model**: Comprehensive D&D 5e statblock data structure
3. **API Design**: Complete endpoint specification for all features
4. **Component Architecture**: React component hierarchy and state management
5. **Workflow Design**: 5-step user workflow with clear progression

### ✅ Backend Implementation (COMPLETED)
1. **Statblock Generation**: AI-powered creature generation with GPT-4 and OpenAI Structured Outputs
2. **Validation System**: D&D 5e rules compliance checking with comprehensive field validation
3. **Data Models**: Complete Pydantic v2 models with proper field aliases and validation
4. **API Router**: Full FastAPI router with 12 endpoints for generation and project management
5. **Prompt Management**: Versioned prompt system with structured JSON output
6. **Test Suite**: Comprehensive test coverage with 31 unit tests
   - Performance benchmarks and reliability tests
   - Integration tests with real OpenAI API validation
   - Proper pytest configuration with markers (unit, integration, slow, live)
   - Test runner with environment management and API key handling
   - All tests passing with full coverage

### 🔄 Implementation Roadmap

#### Phase 1: Core Backend ✅ (COMPLETED)
1. ✅ **Statblock Generation**: AI-powered creature generation with GPT-4 and OpenAI Structured Outputs
2. ✅ **Validation System**: D&D 5e rules compliance checking with comprehensive field validation
3. 🔄 **HTML Rendering**: Template-based statblock display (planned)
4. ✅ **Basic API**: Core generation and validation endpoints (12 endpoints implemented)

#### Phase 2: Frontend Foundation (Priority: High)
1. **Step Components**: React components for each workflow step
2. **Statblock Editor**: Comprehensive editing interface
3. **Project Management**: Basic project creation and persistence
4. **State Management**: React state and Firestore integration

#### Phase 3: Advanced Features (Priority: Medium)
1. **Image Generation**: Creature artwork with Fal.ai integration
2. **3D Model Generation**: Tripo3D API integration
3. **Export System**: Multi-format export capabilities
4. **Advanced Validation**: CR calculation and balance recommendations

#### Phase 4: Polish & Integration (Priority: Medium)
1. **Enhanced UI**: D&D-themed styling and animations
2. **Mobile Optimization**: Touch-friendly interface improvements
3. **Project Integration**: Campaign and encounter management
4. **Performance Optimization**: Caching and optimization

## Data Flow Architecture

```
1. User Input → Step 1: Creature Description (GPT-4 → Structured Statblock Data)
2. SD Prompt → Step 2: Creature Image Generation (Fal.ai → Creature Artwork)
3. Statblock Editing → Step 3: Customization (Validation → Finalized Stats)
4. Image Processing → Step 4: 3D Model Generation (Tripo3D → 3D Model)
5. Export Generation → Step 5: Finalization (Templates → Multi-format Outputs)
```

## Integration Benefits

### Immediate Value
1. **Complete D&D Toolset**: Unified creature and item creation platform
2. **Professional Output**: High-quality statblocks matching official D&D formatting
3. **Workflow Efficiency**: Streamlined creature creation process
4. **Cross-Tool Synergy**: Integration with CardGenerator for complete campaign tools

### Future Expansion Potential
1. **Campaign Management**: Link creatures to encounters and campaigns
2. **Encounter Balancing**: Automated CR calculations and party balance recommendations
3. **VTT Integration**: Direct export to popular virtual tabletop platforms
4. **Adventure Modules**: Complete adventure creation with creatures, items, and maps
5. **Homebrew Community**: Share and discover user-created creatures

## Performance Considerations

### Frontend Optimizations
- Debounced auto-save to reduce API calls during editing
- Lazy loading of creature galleries and images
- Memoized components for complex statblock calculations
- Efficient form validation with real-time feedback

### Backend Optimizations
- Async processing for AI generation and model creation
- Efficient database queries with proper indexing
- CDN delivery for generated images and exports
- Rate limiting and circuit breakers for external AI APIs

## Security Considerations

### Authentication & Authorization
- User-based project isolation with secure access controls
- Secure API key management for external services
- Session validation and automatic cleanup
- Input sanitization and validation for all user data

### Data Protection
- Encrypted storage of user projects and creature data
- Secure image upload and processing pipelines
- Audit logging for user actions and data modifications
- GDPR-compliant data handling and user privacy

## Monitoring & Observability

### Error Tracking
- Comprehensive error logging for AI generation failures
- User-friendly error messages with troubleshooting guidance
- Automatic error reporting and monitoring
- Performance monitoring for generation times

### Analytics
- User behavior tracking for workflow optimization
- Feature usage statistics and adoption metrics
- Generation success rates and failure analysis
- Performance metrics for all external API integrations

This design document provides a comprehensive roadmap for implementing the StatBlock Generator as a fully integrated component of the DungeonMind platform, following the proven patterns established by the CardGenerator while addressing the unique requirements of D&D 5e creature creation.
