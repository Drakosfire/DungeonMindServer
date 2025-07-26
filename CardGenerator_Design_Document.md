# CardGenerator Design Document

## Project Overview

The CardGenerator is a comprehensive web application that allows users to create custom D&D-style item cards through a multi-step workflow. The project integrates AI-powered text generation, image generation, and custom text rendering to produce high-quality, visually appealing trading card-style items.

## Technical Architecture

### Backend (Python/FastAPI)
- **Framework**: FastAPI with modular router structure
- **Location**: `/DungeonMindServer/cardgenerator/`
- **Core Components**:
  - `card_generator.py`: Main card composition and rendering logic
  - `render_card_text.py`: Text positioning and font rendering
  - `prompts.py`: GPT-4 prompts for item generation
  - `cardgenerator_router.py`: API endpoints for card generation
  - `session_manager.py`: State persistence and session management

### Frontend (React/TypeScript)
- **Framework**: React with TypeScript
- **Location**: `/LandingPage/src/components/CardGenerator/`
- **UI Library**: Mantine Core components
- **Architecture**: Component-based with hybrid state management
  - Local state for UI interactions
  - localStorage for immediate persistence
  - Firestore for authenticated user sessions

### External Services
- **AI Text Generation**: OpenAI GPT-4 with structured output
- **Image Generation**: Fal.ai Flux-LoRA for image-to-image generation
- **Image Storage**: Cloudflare Images and R2 for CDN delivery
- **Database**: Firestore for data persistence and session management

### State Persistence Architecture

#### Hybrid Persistence System
**Primary Layer**: localStorage auto-save
- Immediate state persistence on every change
- Survives browser refreshes and restarts
- Works without user authentication
- Automatic cleanup of old sessions

**Secondary Layer**: Firestore integration
- Authenticated user session management
- Cross-device synchronization
- Named card saves and collections
- Integration with existing user management system

#### State Management Schema
```typescript
interface CardGeneratorState {
  sessionId: string;
  currentStep: string;
  stepCompletion: Record<string, boolean>;
  itemDetails: ItemDetails;
  selectedAssets: {
    finalImage: string;
    border: string;
    seedImage: string;
    templateBlob?: string;
  };
  generatedContent: {
    images: GeneratedImage[];
    renderedCards: RenderedCard[];
  };
  metadata: {
    lastSaved: timestamp;
    version: string;
  };
}
```

## Current Feature Set

### 1. Template Selection System
**Components**: `BorderGallery.tsx`, `SeedImageGallery.tsx`, `TemplatePreview.tsx`

- **Border Templates**: 7 predefined border styles (Onyx, Flaming, Yellow Sandstone, Green Intricate, Blue Ink, Teal Crystal, Cookie)
- **Seed Images**: 13 thematic base images (weapons, potions, magical items, etc.)
- **Template Preview**: Real-time composition preview with user selections

### 2. AI-Powered Text Generation
**Components**: `ItemForm.tsx`
**Backend**: `generate-item-dict` endpoint

- **Input**: Natural language item description
- **Processing**: GPT-4 structured output with JSON schema validation
- **Output**: Complete item data structure including:
  - Name, Type, Rarity, Value
  - Properties array
  - Damage formula and type
  - Weight, Description, Quote
  - SD Prompt for image generation

### 3. Image Generation Pipeline
**Components**: `ImageGallery.tsx`
**Backend**: `generate-card-images` endpoint

- **Process**: Template + AI text → Flux-LoRA image-to-image generation
- **Output**: 4 generated card variants per request
- **Integration**: Uses SD Prompt from text generation for thematic consistency

### 4. Text Rendering System
**Components**: `CardWithTextGallery.tsx`
**Backend**: `render_card_text` endpoint, `render_card_text.py`

- **Dynamic Font Sizing**: Auto-adjusts text size based on content length
- **Multi-section Layout**: Title, type, description, quote, value positioning
- **Rarity Indicators**: Color-coded stickers based on item rarity
- **Typography**: Custom Balgruf font family with shadow effects

## Data Flow Architecture

```
1. User Input → Template Selection (Border + Seed Image)
2. Template Composition → Blob Generation
3. Text Generation → GPT-4 → Structured Item Data
4. Image Generation → Flux-LoRA → 4 Card Variants
5. Text Rendering → PIL Text Composition → Final Card
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
- **Image Generation**: Fal.ai integration with 0.85 strength parameter
- **Text Rendering**: PIL-based with dynamic font scaling and positioning
- **Rarity System**: Predefined sticker overlay system

### API Endpoints
- `POST /api/cardgenerator/generate-item-dict`: Text generation
- `POST /api/cardgenerator/generate-card-images`: Image generation
- `POST /api/cardgenerator/render-card-text`: Final card composition
- `POST /api/cardgenerator/upload-image`: Image upload utility
- `POST /api/cardgenerator/save-card-session`: State persistence (auto-save and manual)
- `GET /api/cardgenerator/load-card-session`: Session restoration
- `GET /api/cardgenerator/list-user-cards`: User's card management
- `POST /api/cardgenerator/save-completed-card`: Permanent card saves

## Current UI/UX Issues

### Layout Problems
1. **Inconsistent Spacing**: Manual CSS styling leads to uneven component spacing
2. **Responsive Design**: Limited mobile optimization
3. **Visual Hierarchy**: Unclear step progression and information hierarchy
4. **Loading States**: Basic loading indicators without proper UX feedback

### Styling Concerns
1. **Color Scheme**: Limited color palette, lacks modern design principles
2. **Typography**: Inconsistent text sizing and spacing
3. **Component Cohesion**: Disconnected visual elements
4. **Accessibility**: Missing ARIA labels and keyboard navigation

### User Experience
1. **Workflow Clarity**: Steps not clearly defined or numbered
2. **Error Handling**: Basic error messages without user guidance
3. **Progress Indication**: No clear progress tracking through the workflow
4. ~~**Result Management**: Limited options for saving or sharing results~~ (**RESOLVED**: State persistence now implemented)

## Planned Features

### 1. CardBack Generator (Priority: High)
**Purpose**: Allow users to create custom card backs that complement their items

**Technical Requirements**:
- New component: `CardBackGenerator.tsx`
- Backend endpoint: `generate-card-back`
- Integration with existing template system
- Separate design workflow for back-side composition

**Design Considerations**:
- Thematic consistency with front card
- Customizable elements (logos, patterns, text)
- Export options for complete card sets

### 2. Enhanced Card Management (Priority: Medium)
**Now Enabled by State Persistence**:
- Card gallery with persistent storage ✅
- User card collections and organization
- Advanced export options (PDF, PNG, print-ready formats)
- Batch card generation
- Social sharing capabilities

### 3. Advanced Customization (Priority: Low)
- Custom color schemes
- Font selection options
- Layout template variations
- Import/export of custom templates

## State Persistence Benefits

### Immediate Improvements
1. **Development Efficiency**: No more lost progress during testing and development
2. **User Retention**: Users can return to incomplete cards without starting over
3. **Error Recovery**: Automatic recovery from browser crashes or accidental navigation
4. **Cross-Session Continuity**: Seamless experience across device restarts

### Future Capabilities Enabled
1. **User Galleries**: Personal collections of created cards
2. **Collaboration**: Share works-in-progress with others
3. **Version History**: Track card iterations and changes
4. **Analytics**: Understanding user behavior and popular card types 