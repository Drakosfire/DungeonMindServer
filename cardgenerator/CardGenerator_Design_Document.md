# CardGenerator Design Document

## Project Overview

The CardGenerator is a comprehensive web application that allows users to create custom D&D-style item cards through a structured 5-step workflow. The project integrates AI-powered text generation, image generation, and custom text rendering to produce high-quality, visually appealing trading card-style items with full project management and state persistence capabilities.

## Technical Architecture

### Backend (Python/FastAPI)
- **Framework**: FastAPI with modular router structure
- **Location**: `/DungeonMindServer/routers/cardgenerator_router.py`
- **Core Components**:
  - `card_generator_new.py`: Main card composition and rendering logic
  - `prompts.py`: GPT-4 prompts for item generation with versioned prompt management
  - `cardgenerator_router.py`: Comprehensive API endpoints for card generation and project management
  - `cardgenerator_project_router.py`: Project-specific endpoints
  - `cardgenerator_compatibility_router.py`: Legacy compatibility endpoints

### Frontend (React/TypeScript)
- **Framework**: React with TypeScript
- **Location**: `/LandingPage/src/components/CardGenerator/`
- **UI Library**: Mantine Core components with custom design system
- **Architecture**: Component-based with comprehensive state management
  - Local state for UI interactions
  - Project-based persistence with Firestore integration
  - Real-time auto-save functionality
  - Generation lock system to prevent navigation during async operations

### External Services
- **AI Text Generation**: OpenAI GPT-4 with structured output validation
- **Image Generation**: Fal.ai Flux-LoRA for image-to-image generation
- **Image Storage**: Cloudflare Images and R2 for CDN delivery
- **Database**: Firestore for project persistence and session management

## Current Feature Set

### 1. Five-Step Workflow System
**Components**: `Step1TextGeneration.tsx`, `Step2CoreImage.tsx`, `Step3BorderGeneration.tsx`, `Step4CardBack.tsx`, `Step5FinalAssembly.tsx`

#### Step 1: Text Generation
- **Component**: `Step1TextGeneration.tsx` with `ItemForm.tsx`
- **Functionality**: AI-powered item description generation
- **Input**: Natural language item description
- **Processing**: GPT-4 structured output with JSON schema validation
- **Output**: Complete item data structure including name, type, rarity, value, properties, damage, weight, description, quote, and SD prompt

#### Step 2: Core Image Generation
- **Component**: `Step2CoreImage.tsx`
- **Functionality**: Generate base item images using AI
- **Process**: Uses SD prompt from Step 1 to generate thematic base images
- **Output**: Multiple core image variants for selection

#### Step 3: Border Generation
- **Component**: `Step3BorderGeneration.tsx`
- **Functionality**: Apply borders and generate final card variants
- **Features**: 
  - Border template selection (7 predefined styles)
  - Template composition with core images
  - AI-powered card generation with Flux-LoRA
  - 4 generated card variants per request
- **Output**: Complete card images with borders applied

#### Step 4: Card Back Generation
- **Component**: `Step4CardBack.tsx`
- **Functionality**: Create professional card backs
- **Options**:
  - Standard templates (Fantasy, Parchment, Arcane, Guild)
  - Custom text input
  - AI-generated backs
- **Status**: Implemented UI, backend integration pending

#### Step 5: Final Assembly
- **Component**: `Step5FinalAssembly.tsx`
- **Functionality**: Render text on cards and finalize
- **Features**:
  - Dynamic text rendering with custom fonts
  - Editable item details
  - Download options (PNG, PDF)
  - Final card preview with text overlay

### 2. Project Management System
**Components**: `ProjectsDrawer.tsx`, `CreateProjectModal.tsx`, `ProjectCard.tsx`

#### Core Features
- **Project Creation**: Named projects with descriptions
- **Auto-Save**: Real-time state persistence
- **Project Switching**: Seamless navigation between projects
- **Project Operations**: Save, load, duplicate, delete
- **Search & Filter**: Find projects by name or description
- **Project Metadata**: Creation date, last modified, card count

#### State Persistence Architecture
```typescript
interface CardGeneratorState {
  currentStepId: string;
  stepCompletion: Record<string, boolean>;
  itemDetails: ItemDetails;
  selectedAssets: {
    finalImage?: string;
    border?: string;
    seedImage?: string;
    generatedCardImages: string[];
    selectedGeneratedCardImage?: string;
    finalCardWithText?: string;
    templateBlob?: string;
  };
  generatedContent: {
    images: GeneratedImage[];
    renderedCards: RenderedCard[];
  };
  autoSaveEnabled: boolean;
  lastSaved?: string;
}
```

### 3. Shared Component System
**Location**: `/LandingPage/src/components/CardGenerator/shared/`

#### Image Modal System
- **ImageModal.tsx**: Expandable image modal with download functionality
- **ClickableImage.tsx**: Clickable image component with modal integration
- **useImageModal.tsx**: Custom hook for modal state management
- **Features**: Responsive design, download options, customizable titles/descriptions

#### Integration Status
- ✅ CoreImageGallery (example and generated images)
- ✅ CardWithTextGallery (final cards and examples)
- ✅ ImageGallery (generated card images)

### 4. Generation Lock System
**Purpose**: Prevent navigation during async operations
**Implementation**: 
- Tracks generation state across all steps
- Disables navigation and project switching during generation
- Provides visual feedback for ongoing operations
- Prevents data loss during AI operations

### 5. Navigation & UI Components
**Components**: `StepNavigation.tsx`, `FloatingHeader.tsx`

#### Step Navigation
- Visual step progression with completion indicators
- Responsive design for mobile and desktop
- Generation lock integration
- Keyboard navigation support

#### Floating Header
- Project management integration
- Save status indicators
- Responsive design with mobile optimization
- Real-time project switching

## Data Flow Architecture

```
1. User Input → Step 1: Text Generation (GPT-4 → Structured Item Data)
2. SD Prompt → Step 2: Core Image Generation (Fal.ai → Base Images)
3. Template Composition → Step 3: Border Generation (Flux-LoRA → Card Variants)
4. Card Back Selection → Step 4: Card Back Generation (Templates/Custom/AI)
5. Text Rendering → Step 5: Final Assembly (PIL → Final Card with Text)
```

## Technical Implementation Details

### Frontend State Management
```typescript
interface ItemDetails {
    name: string;
    type: string;
    rarity: string;
    value: string;
    properties: string[];
    damageFormula: string;
    damageType: string;
    weight: string;
    description: string;
    quote: string;
    sdPrompt: string;
}
```

### Backend Data Processing
- **Template Upload**: Cloudflare Images API for template storage
- **Image Generation**: Fal.ai integration with configurable strength parameters
- **Text Rendering**: PIL-based with dynamic font scaling and positioning
- **Rarity System**: Predefined sticker overlay system
- **Project Persistence**: Firestore integration with real-time sync

### API Endpoints
#### Core Generation
- `POST /api/cardgenerator/generate-item-dict`: Text generation
- `POST /api/cardgenerator/generate-core-images`: Core image generation
- `POST /api/cardgenerator/generate-card-images`: Border card generation
- `POST /api/cardgenerator/render-card-text`: Final card composition
- `POST /api/cardgenerator/upload-image`: Image upload utility

#### Project Management
- `POST /api/cardgenerator/create-project`: Create new project
- `GET /api/cardgenerator/list-projects`: List user projects
- `GET /api/cardgenerator/project/{project_id}`: Load project
- `PUT /api/cardgenerator/project/{project_id}`: Update project
- `DELETE /api/cardgenerator/project/{project_id}`: Delete project
- `POST /api/cardgenerator/project/{project_id}/duplicate`: Duplicate project

#### Session Management
- `POST /api/cardgenerator/save-card-session`: Auto-save and manual save
- `GET /api/cardgenerator/load-card-session`: Session restoration
- `GET /api/cardgenerator/list-user-sessions`: User's session management
- `DELETE /api/cardgenerator/delete-card-session`: Session cleanup

#### Asset Management
- `GET /api/cardgenerator/example-images`: Example image gallery
- `GET /api/cardgenerator/border-options`: Border template options
- `POST /api/cardgenerator/upload-generated-images`: Batch image upload
- `DELETE /api/cardgenerator/delete-image`: Image cleanup

## Current UI/UX Features

### Responsive Design
- Mobile-first approach with breakpoint optimization
- Collapsible project drawer for mobile devices
- Touch-friendly interface elements
- Adaptive layouts for different screen sizes

### Visual Design System
- **Color Scheme**: Custom CSS variables with dark/light theme support
- **Typography**: Custom Balgruf font family with shadow effects
- **Component Cohesion**: Consistent Mantine-based design system
- **Accessibility**: ARIA labels and keyboard navigation

### User Experience
- **Workflow Clarity**: Clear step progression with visual indicators
- **Error Handling**: Comprehensive error messages with user guidance
- **Progress Indication**: Real-time save status and generation progress
- **Result Management**: Full project persistence and export capabilities

## Completed Features

### ✅ Core Functionality
1. **Five-Step Workflow**: Complete implementation with step validation
2. **AI Text Generation**: GPT-4 integration with structured output
3. **Image Generation**: Fal.ai integration for core and border images
4. **Text Rendering**: PIL-based text composition with custom fonts
5. **Project Management**: Full CRUD operations with real-time persistence
6. **State Persistence**: Auto-save with manual save options
7. **Generation Lock System**: Prevents navigation during async operations
8. **Shared Component System**: Reusable image modal and gallery components

### ✅ User Experience
1. **Responsive Design**: Mobile and desktop optimization
2. **Visual Feedback**: Loading states and progress indicators
3. **Error Recovery**: Graceful handling of failures
4. **Cross-Session Continuity**: Seamless experience across device restarts
5. **Project Organization**: Search, filter, and metadata management

### ✅ Technical Infrastructure
1. **API Architecture**: Comprehensive REST endpoints
2. **Database Integration**: Firestore for project persistence
3. **Image Storage**: Cloudflare Images and R2 integration
4. **Security**: Authentication and authorization
5. **Error Handling**: Comprehensive error management
6. **Testing**: Integration tests for core functionality

## Planned Features

### 1. Card Back Integration (Priority: High)
**Status**: UI implemented, backend integration pending
**Requirements**:
- Backend endpoint for card back generation
- Integration with existing template system
- Export options for complete card sets

### 2. Advanced Customization (Priority: Medium)
- Custom color schemes and themes
- Font selection options
- Layout template variations
- Import/export of custom templates

### 3. Collaboration Features (Priority: Low)
- Share works-in-progress with others
- Collaborative editing capabilities
- Public card galleries
- Social sharing integration

## State Persistence Benefits

### Immediate Improvements
1. **Development Efficiency**: No more lost progress during testing
2. **User Retention**: Users can return to incomplete cards
3. **Error Recovery**: Automatic recovery from browser crashes
4. **Cross-Session Continuity**: Seamless experience across restarts

### Future Capabilities Enabled
1. **User Galleries**: Personal collections of created cards
2. **Version History**: Track card iterations and changes
3. **Analytics**: Understanding user behavior and popular card types
4. **Templates**: Reusable project templates for common card types

## Performance Optimizations

### Frontend Optimizations
- Debounced auto-save to reduce API calls
- Lazy loading of image galleries
- Memoized components for expensive operations
- Efficient state updates with React hooks

### Backend Optimizations
- Async image processing with background tasks
- Efficient database queries with indexing
- CDN delivery for static assets
- Rate limiting and circuit breakers for external APIs

## Security Considerations

### Authentication & Authorization
- User-based project isolation
- Secure API key management
- Session validation and cleanup
- Input sanitization and validation

### Data Protection
- Encrypted storage of sensitive data
- Secure image upload and processing
- Audit logging for user actions
- GDPR-compliant data handling

## Monitoring & Observability

### Error Tracking
- Comprehensive error logging
- User-friendly error messages
- Automatic error reporting
- Performance monitoring

### Analytics
- User behavior tracking
- Feature usage statistics
- Performance metrics
- Error rate monitoring

This updated design document accurately reflects the current implementation of the CardGenerator project, including all completed features, the 5-step workflow, project management system, and comprehensive state persistence capabilities. 