# StatBlock Generator Porting Guide

## Overview

This document serves as a practical guide for porting the standalone StatBlock Generator into the DungeonMind ecosystem, following the patterns established by the CardGenerator. Rather than reusing code directly, this focuses on architectural patterns, implementation strategies, and lessons learned.

## Source Reference Files

### Current StatBlock Generator (Standalone)
**Location**: `/StatblockGenerator/`

#### Core Logic Files
- **`app.py`** (609 lines) - Main Gradio application structure
  - **Key Lessons**: State management patterns, UI flow control
  - **Adaptable Concepts**: Step progression, form validation, generation workflows
  - **Skip**: Gradio-specific UI code, direct state variables

- **`description_helper.py`** (249 lines) - LLM integration and prompt management
  - **Key Lessons**: OpenAI API integration, prompt engineering, response parsing
  - **Adaptable Concepts**: Structured output validation, error handling
  - **Reference for**: Backend AI integration patterns

- **`process_html.py`** (318 lines) - HTML generation and rendering
  - **Key Lessons**: Template-based rendering, dynamic content insertion
  - **Adaptable Concepts**: Statblock formatting, CSS integration
  - **Reference for**: Export functionality design

- **`process_text.py`** (61 lines) - Text formatting utilities
  - **Key Lessons**: Data transformation patterns, text processing
  - **Adaptable Concepts**: Format conversion functions
  - **Reference for**: Data validation and formatting

- **`utilities.py`** (96 lines) - File management and utility functions
  - **Key Lessons**: File handling, timestamp generation, cleanup patterns
  - **Adaptable Concepts**: Resource management
  - **Reference for**: Backend utility functions

#### Supporting Files
- **`sd_generator.py`** (53 lines) - Image generation with Fal.ai
- **`tripo3d.py`** (130 lines) - 3D model generation
- **`pyproject.toml`** - Dependencies and project structure

### CardGenerator Reference Files (Target Patterns)
**Location**: `/DungeonMindServer/cardgenerator/` and `/LandingPage/src/components/CardGenerator/`

#### Backend Reference Files

##### Core Architecture
- **`/routers/cardgenerator_router.py`** - Main API router
  - **Pattern**: RESTful endpoint organization
  - **Lessons**: Authentication, validation, error handling
  - **Adapt for**: StatBlock API endpoints

- **`cardgenerator/card_generator.py`** (230 lines) - Legacy compatibility layer
  - **Pattern**: Backward compatibility design
  - **Lessons**: Migration strategies, API versioning
  - **Adapt for**: StatBlock generator core logic

- **`cardgenerator/card_generator_new.py`** (166 lines) - Modern pipeline
  - **Pattern**: Modular, async-first architecture
  - **Lessons**: Pipeline design, error handling, logging
  - **Adapt for**: StatBlock generation pipeline

##### Prompt and AI Integration
- **`cardgenerator/prompts/`** directory structure
  - **Pattern**: Versioned prompt management
  - **Lessons**: Prompt engineering, structured outputs
  - **Adapt for**: StatBlock prompt organization

- **`cardgenerator/services/`** directory
  - **Pattern**: External service integrations
  - **Lessons**: Service abstraction, error handling
  - **Adapt for**: AI and image generation services

#### Frontend Reference Files

##### Main Component Architecture
- **`CardGenerator.tsx`** (1372 lines) - Main orchestrator component
  - **Pattern**: Step-based workflow management
  - **Lessons**: State management, navigation, persistence
  - **Adapt for**: StatBlockGenerator main component

- **`CardGeneratorProvider.tsx`** (393 lines) - Context and state management
  - **Pattern**: React Context for complex state
  - **Lessons**: State sharing, persistence, auto-save
  - **Adapt for**: StatBlock state management

##### Step Components
- **`steps/Step1TextGeneration.tsx`** - Text generation workflow
  - **Pattern**: Form management, AI integration
  - **Lessons**: User input handling, generation feedback
  - **Adapt for**: Creature description input

- **`steps/Step2CoreImage.tsx`** - Image generation workflow
  - **Pattern**: Gallery management, selection interface
  - **Lessons**: Image handling, generation progress
  - **Adapt for**: Creature image generation

- **`steps/Step5FinalAssembly.tsx`** - Final composition and export
  - **Pattern**: Preview generation, export options
  - **Lessons**: Final output handling, download management
  - **Adapt for**: StatBlock HTML/PDF export

##### Shared Components
- **`shared/`** directory structure
  - **Pattern**: Reusable UI components
  - **Lessons**: Component composition, modal management
  - **Adapt for**: StatBlock-specific shared components

- **`ProjectsDrawerEnhanced.tsx`** (611 lines) - Project management
  - **Pattern**: Project CRUD operations, drawer UI
  - **Lessons**: Project persistence, search/filter
  - **Adapt for**: StatBlock project management

## Implementation Strategy

### Phase 1: Backend Foundation

#### 1.1 Router Structure
**Reference**: `/routers/cardgenerator_router.py`
**Create**: `/routers/statblockgenerator_router.py`

```python
# Key patterns to adapt:
- Authentication middleware integration
- Request/response validation schemas
- Error handling patterns
- Async endpoint design
```

#### 1.2 Core Generation Logic
**Reference**: `cardgenerator/card_generator_new.py`
**Create**: `statblockgenerator/statblock_generator.py`

```python
# Key patterns to adapt:
- Pipeline-based processing
- Async/await patterns
- Structured logging
- Error recovery mechanisms
```

#### 1.3 Prompt Management
**Reference**: `cardgenerator/prompts/` structure
**Create**: `statblockgenerator/prompts/`

```python
# Key patterns to adapt:
- Versioned prompt files
- Structured output schemas
- Prompt testing and validation
- Response parsing utilities
```

### Phase 2: Frontend Components

#### 2.1 Main Component Structure
**Reference**: `CardGenerator.tsx` patterns
**Create**: `StatBlockGenerator.tsx`

```typescript
// Key patterns to adapt:
- Step-based state management
- Generation lock system
- Auto-save functionality
- Navigation guards
```

#### 2.2 Step Components
**Reference**: `steps/` directory patterns
**Create**: `statblockgenerator/steps/`

```typescript
// Components to create:
- Step1CreatureDescription.tsx (from Step1TextGeneration.tsx patterns)
- Step2CreatureImage.tsx (from Step2CoreImage.tsx patterns)
- Step3StatblockCustomization.tsx (new, unique to statblocks)
- Step4ModelGeneration.tsx (from image generation patterns)
- Step5ExportFinalization.tsx (from Step5FinalAssembly.tsx patterns)
```

#### 2.3 Shared Components
**Reference**: `shared/` directory
**Create**: `statblockgenerator/shared/`

```typescript
// Components to create:
- StatBlockPreview.tsx (custom statblock display)
- AbilityScoreEditor.tsx (D&D-specific editor)
- ChallengeRatingCalculator.tsx (CR computation)
- StatBlockExportModal.tsx (export options)
```

### Phase 3: Data Model Adaptation

#### 3.1 Type Definitions
**Reference**: `types/card.types.ts`
**Create**: `types/statblock.types.ts`

```typescript
// Key patterns to adapt:
- Comprehensive type coverage
- Validation-friendly structures
- Optional/required field patterns
- Project integration types
```

#### 3.2 API Schemas
**Reference**: CardGenerator Pydantic models
**Create**: StatBlock Pydantic models

```python
# Key patterns to adapt:
- Validation schemas
- Serialization patterns
- Type conversion utilities
- Error message customization
```

## Key Lessons from CardGenerator

### ✅ Successful Patterns to Replicate

#### 1. Step-Based Workflow
- **Lesson**: Clear progression prevents user confusion
- **Adaptation**: 5-step StatBlock workflow with clear goals
- **Implementation**: Step validation, navigation guards, progress tracking

#### 2. Generation Lock System
- **Lesson**: Prevents data loss during async operations
- **Adaptation**: Lock navigation during AI generation, image creation, model processing
- **Implementation**: Global lock state, visual feedback, operation queuing

#### 3. Auto-Save with Manual Override
- **Lesson**: Balances convenience with user control
- **Adaptation**: Save StatBlock state automatically, allow manual saves
- **Implementation**: Debounced saves, save status indicators, conflict resolution

#### 4. Project-Based Organization
- **Lesson**: Users need to organize their creations
- **Adaptation**: StatBlock collections, campaign organization
- **Implementation**: Project CRUD, search/filter, metadata tracking

#### 5. Modular Component Architecture
- **Lesson**: Shared components reduce duplication
- **Adaptation**: Reusable StatBlock editing components
- **Implementation**: Shared UI components, consistent styling, prop interfaces

### ⚠️ Challenges to Address

#### 1. Complex Data Validation
- **Challenge**: D&D rules are more complex than item properties
- **Solution**: Multi-layer validation (client + server), helpful error messages
- **Implementation**: Schema validation, business logic validation, user guidance

#### 2. Performance with Large Forms
- **Challenge**: StatBlocks have many more fields than cards
- **Solution**: Form optimization, lazy loading, efficient re-renders
- **Implementation**: React.memo, useMemo, field grouping, progressive disclosure

#### 3. Export Complexity
- **Challenge**: Multiple output formats with different requirements
- **Solution**: Template-based rendering, format-specific optimizations
- **Implementation**: Modular export system, preview generation, format validation

### 🔄 Improvements to Implement

#### 1. Enhanced Error Recovery
- **Improvement**: Better handling of AI generation failures
- **Implementation**: Retry mechanisms, fallback options, user guidance

#### 2. Real-time Collaboration Preparation
- **Improvement**: Architecture ready for future collaboration features
- **Implementation**: Conflict resolution patterns, version tracking, change notifications

#### 3. Performance Optimization
- **Improvement**: Faster load times and smoother interactions
- **Implementation**: Code splitting, lazy loading, caching strategies

## File Creation Checklist

### Backend Files to Create
```
DungeonMindServer/statblockgenerator/
├── __init__.py
├── statblock_generator.py          # Core generation logic
├── statblock_prompts.py            # AI prompt management  
├── statblock_html_renderer.py      # HTML/PDF export
├── statblock_validator.py          # D&D rules validation
├── models/
│   ├── __init__.py
│   ├── statblock_models.py         # Pydantic schemas
│   └── cr_calculator.py            # Challenge rating logic
├── services/
│   ├── __init__.py
│   ├── ai_service.py              # OpenAI integration
│   ├── image_service.py           # Fal.ai integration
│   └── model_service.py           # Tripo3D integration
└── prompts/
    ├── __init__.py
    ├── creature_generation.py      # Main generation prompts
    └── validation_prompts.py       # Validation assistance

DungeonMindServer/routers/
└── statblockgenerator_router.py    # Main API router
```

### Frontend Files to Create
```
LandingPage/src/components/StatBlockGenerator/
├── StatBlockGenerator.tsx          # Main component
├── StatBlockGeneratorProvider.tsx  # State management
├── steps/
│   ├── Step1CreatureDescription.tsx
│   ├── Step2CreatureImage.tsx
│   ├── Step3StatblockCustomization.tsx
│   ├── Step4ModelGeneration.tsx
│   └── Step5ExportFinalization.tsx
├── shared/
│   ├── StatBlockPreview.tsx
│   ├── StatBlockEditor.tsx
│   ├── AbilityScoreEditor.tsx
│   ├── ActionEditor.tsx
│   ├── SpellEditor.tsx
│   └── CRCalculator.tsx
├── hooks/
│   ├── useStatBlockValidation.ts
│   ├── useStatBlockPersistence.ts
│   └── useStatBlockGeneration.ts
└── types/
    └── statblock.types.ts

LandingPage/src/types/
└── statblock.types.ts              # Global type definitions
```

## Implementation Priority

### 🔴 High Priority (MVP)
1. **Core Backend**: Basic statblock generation and validation
2. **Step 1-3 Frontend**: Description → Image → Customization
3. **Basic Export**: HTML preview and simple PDF export
4. **Project Integration**: Save/load functionality

### 🟡 Medium Priority (V1.1)
1. **Advanced Validation**: CR calculation and balance recommendations
2. **Step 4-5**: 3D models and advanced export options
3. **Enhanced UI**: Improved styling and mobile optimization
4. **Performance**: Optimization and caching

### 🟢 Low Priority (Future)
1. **Collaboration**: Multi-user editing and sharing
2. **Campaign Integration**: Link to encounter management
3. **VTT Export**: Advanced format support
4. **Community Features**: Creature sharing and discovery

## Success Metrics

### Technical Success
- [ ] All 5 workflow steps functional
- [ ] D&D 5e rule compliance validation
- [ ] Export to HTML/PDF working
- [ ] Project persistence operational
- [ ] Performance comparable to CardGenerator

### User Experience Success
- [ ] Intuitive workflow progression
- [ ] Clear error messages and guidance
- [ ] Fast generation times (<30s for complete creature)
- [ ] Mobile-responsive interface
- [ ] Seamless integration with existing DungeonMind experience

This porting guide provides a structured approach to implementing the StatBlock Generator while leveraging the proven success patterns from the CardGenerator implementation.
