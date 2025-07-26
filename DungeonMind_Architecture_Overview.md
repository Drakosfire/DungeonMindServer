# DungeonMind Architecture Overview
## System Design, Patterns, and Evolution Path

### 🏛️ **System Architecture**

DungeonMind is a multi-application platform for TTRPG content creation, built on a unified backend with specialized frontend applications.

```
┌─────────────────────────────────────────────────────────────┐
│                    DungeonMind Ecosystem                     │
├─────────────────────────────────────────────────────────────┤
│  Frontend Applications                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ LandingPage │  │ CardGen     │  │ StoreGen    │        │
│  │ (React)     │  │ (React)     │  │ (Vanilla)   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
├─────────────────────────────────────────────────────────────┤
│  Unified Backend (DungeonMindServer)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ FastAPI     │  │ Auth        │  │ AI Services │        │
│  │ Router      │  │ Service     │  │ (OpenAI)    │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
├─────────────────────────────────────────────────────────────┤
│  Data Layer                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Firestore   │  │ CloudflareR2│  │ Session     │        │
│  │ Database    │  │ Storage     │  │ Management  │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎨 **Design System Architecture**

### **UI Hierarchy & Z-Index Management**
```
Layer 4: Modals & Overlays (z-index: 1000+)
├── Critical alerts, loading overlays
├── Modal dialogs, confirmation prompts
└── Tooltips, dropdowns (600-999)

Layer 3: Primary Navigation (z-index: 1000)
├── NavBar - Fixed left sidebar, 80px width
├── Always visible, highest application priority
└── User authentication, main app switching

Layer 2: Secondary Navigation (z-index: 500)
├── FloatingHeader - Tool-specific controls
├── Step navigation, save/load functions
└── Context-aware to current application

Layer 1: Content Areas (z-index: 100)
├── Main application content
├── Cards, forms, galleries
└── Respects 80px left margin for NavBar
```

### **Design Tokens**
```css
/* Spacing System */
--space-1: 0.25rem    /* 4px */
--space-2: 0.5rem     /* 8px */
--space-3: 0.75rem    /* 12px */
--space-4: 1rem       /* 16px */

/* Color System */
--primary-blue: #3b82f6
--success-green: #10b981
--warning-amber: #f59e0b
--surface-white: #ffffff
--surface-light: #f8fafc
--text-primary: #1f2937
--text-muted: #6b7280

/* Typography */
--font-primary: 'Inter', sans-serif
--text-xs: 0.75rem
--text-sm: 0.875rem
--text-base: 1rem
--text-lg: 1.125rem
```

---

## 🔐 **Authentication Architecture**

### **Unified OAuth System**
- **Provider**: Google OAuth 2.0
- **Backend**: Centralized `auth_service.py`
- **Frontend**: React `AuthContext` with auto-refresh
- **Session**: HTTP-only cookies with CORS support
- **Endpoints**: Consistent `/api/auth/*` across all apps

### **Authentication Flow**
```
User Login → Google OAuth → DungeonMind Backend → Session Cookie
     ↓              ↓             ↓                    ↓
All Apps ← Auto-refresh ← Token validation ← Firestore user data
```

### **Session Management**
```python
# Consistent across all applications
cookie_name = "dungeonmind_session"
max_age = 24 * 60 * 60  # 24 hours
secure = True  # HTTPS only in production
samesite = "lax"  # CORS-friendly
```

---

## 📊 **Data Architecture**

### **Project Management System**
```
User (Google OAuth ID)
├── Projects (Firestore collections)
│   ├── Project Metadata (name, description, timestamps)
│   ├── Project State (complete application state)
│   └── Project Assets (images, templates)
└── Sessions (temporary working state)
```

### **State Management Patterns**

#### **CardGenerator State Flow**
```
User Input → Local React State → Debounced Auto-save → Firestore
     ↓              ↓                     ↓               ↓
Real-time UI ← Optimistic updates ← Save feedback ← Persistence
```

#### **Project Lifecycle**
```
1. Initialize: Load user's projects → Select most recent
2. Create: New project for significantly different content
3. Update: Modify existing project for similar content
4. Auto-save: Debounced state persistence (5s delay)
5. Manual save: Immediate save with visual feedback
```

---

## 🔄 **State Management Patterns**

### **React State Architecture**
```typescript
// Component State (UI-specific)
const [isLoading, setIsLoading] = useState(false);
const [showDropdown, setShowDropdown] = useState(false);

// Application State (business logic)
const [itemDetails, setItemDetails] = useState<ItemDetails>({});
const [currentProject, setCurrentProject] = useState<Project | null>(null);

// Derived State (computed from other state)
const getReliableItemName = useCallback(() => {
  return itemDetails.name?.trim() || currentProject?.name || 'Untitled';
}, [itemDetails.name, currentProject?.name]);
```

### **Auto-save Implementation**
```typescript
// Debounced save to prevent excessive API calls
const debouncedSave = useCallback(
  debounce(saveCurrentState, 5000), 
  [saveCurrentState]
);

// Stabilized save function to prevent recreation loops
const saveCurrentProject = useCallback(async (overrideName?: string) => {
  // Implementation with stable dependencies
}, [currentProject?.id, userId]);
```

---

## 🧠 **AI Integration Architecture**

### **Content Generation Pipeline**
```
User Input → Prompt Engineering → OpenAI API → Structured Response
     ↓              ↓                  ↓              ↓
Natural language → Context-aware → JSON Schema → Validated data
```

### **AI Service Integration**
```python
# Modular AI services
ai_services/
├── text_generation.py    # Item descriptions, stories
├── image_generation.py   # Visual content creation
├── data_extraction.py    # Structured data from text
└── content_enhancement.py # Polish and refinement
```

---

## 🚀 **Deployment Architecture**

### **Current Infrastructure**
```
Domain: dev.dungeonmind.net
├── Backend: FastAPI server
├── Frontend: Static file serving
├── Database: Google Firestore
├── Storage: Cloudflare R2
└── CDN: Cloudflare
```

### **Development Workflow**
```
Local Development → Git Push → Deployment Script → Live Update
       ↓              ↓            ↓                ↓
Hot reload ← File watching ← Automated build ← Server restart
```

---

## 📈 **Evolution Path & Scaling Strategy**

### **Phase 1: CardGenerator Stabilization** (Current)
- ✅ Core functionality stable
- ✅ Project management system
- ✅ Design system compliance
- 🔄 Steps 2-5 polish
- 🔄 Performance optimization

### **Phase 2: Content Ecosystem Expansion**
    How to organize these is a worthy question for semantic generation props. 
- 📋 NPC Generator
- 📋 Location Builder
- 📋 Campaign Manager
- 📋 Rules Creator

### **Phase 3: Platform Integration**
MCP SERVER FOR VTT
STANDARDIZED DATA MODEL FOR VTT DATA THAT DISTRIBUTES VIA MCP.
LLM Translate between values?
LLM generated cross key? 
Feel doable.
Build Character Generator, then a standardized Data Model across DungeonMind objects. Or something like that. More efficient than now anyway. 
A single unified storage and object system to encourage world building. Open Source! 
Getting advanced and down into the k:v should be accessible. Not necessarily easy. 

Sharing. To DungeonMind. To Others eventually. 
Fine tune could be fun, to test specifically. How to measure that is not an easy question. Not worth the effort initially except as fun. Core models are plenty sufficient to do this quite well I think. 
- 📋 MCP Server for AI agents
- 📋 VTT platform exports
- 📋 Collaboration features
- 📋 Mobile applications

### **Phase 4: Community & Marketplace**
- 📋 User-generated content sharing
- 📋 Template marketplace
- 📋 Creator monetization
- 📋 Community features



---

## 🛠️ **Development Patterns & Best Practices**

### **Component Architecture**
```typescript
// Smart components (data management)
const CardGenerator: React.FC = () => {
  // State management, API calls, business logic
  return <CardGeneratorView {...props} />;
};

// Dumb components (presentation only)
const CardGeneratorView: React.FC<Props> = ({ data, handlers }) => {
  // Pure presentation, no business logic
  return <div>...</div>;
};
```

### **API Design Patterns**
```python
# Consistent router structure
@router.post('/api/cardgenerator/action')
async def action(request: RequestModel, user = Depends(get_current_user)):
    # 1. Validate input
    # 2. Check permissions
    # 3. Business logic
    # 4. Return structured response
    # 5. Log for debugging
```

### **Error Handling Strategy**
```typescript
// Progressive error handling
try {
  await primaryAction();
} catch (error) {
  console.error('Primary action failed:', error);
  try {
    await fallbackAction();
  } catch (fallbackError) {
    // User-friendly error message
    showErrorToUser('Something went wrong. Please try again.');
  }
}
```

---

## 🔍 **Debugging & Monitoring**

### **Logging Strategy**
```
Frontend (Console):
├── User actions and state changes
├── API calls and responses
├── Component lifecycle events
└── Error conditions with context

Backend (Structured logs):
├── Request/response cycles
├── Database operations
├── AI service calls
└── Authentication events
```

### **Performance Monitoring**
```typescript
// Key metrics to track
const metrics = {
  bundleSize: 'Frontend load time',
  apiLatency: 'Backend response time',
  saveLatency: 'Data persistence speed',
  errorRate: 'User-facing failures',
  sessionLength: 'User engagement'
};
```

---

## 🎯 **Technical Debt & Improvement Opportunities**

### **High Priority**
1. **Bundle Optimization**: Reduce frontend load times
2. **Database Indexing**: Optimize Firestore queries
3. **Error Boundaries**: Better React error handling
4. **Type Safety**: Strengthen TypeScript coverage

### **Medium Priority**
1. **Testing**: Automated UI and API testing
2. **Documentation**: Living architecture docs
3. **Monitoring**: Real-time error tracking
4. **Security**: Enhanced session management

### **Future Considerations**
1. **Microservices**: Split backend by domain
2. **Caching**: Redis for frequently accessed data
3. **CDN**: Optimize static asset delivery
4. **Mobile**: React Native or PWA approach

---

## 💡 **Innovation Opportunities**

### **MCP Server Integration**
```
Vision: DungeonMind as AI Agent Tool
┌─────────────────────────────────────┐
│ User's AI Agent (Claude, GPT, etc.) │
├─────────────────────────────────────┤
│ MCP Protocol Communication         │
├─────────────────────────────────────┤
│ DungeonMind MCP Server             │
│ ├── Content generation tools       │
│ ├── Project management tools       │
│ ├── Export/sharing tools           │
│ └── User account integration       │
├─────────────────────────────────────┤
│ Existing DungeonMind Infrastructure │
│ ├── Authentication system          │
│ ├── Project management             │
│ ├── AI content generation          │
│ └── Data persistence               │
└─────────────────────────────────────┘
```

### **Content Intelligence**
- Context-aware content suggestions
- Cross-content referencing and linking
- Style consistency across projects
- Collaborative worldbuilding features

---

## 🏆 **Architecture Achievements**

### **Stability & Reliability**
- ✅ Eliminated runtime crashes
- ✅ Resolved data persistence issues
- ✅ Fixed auto-save loops
- ✅ Implemented robust error handling

### **User Experience**
- ✅ Intuitive project management
- ✅ Visual feedback for all actions
- ✅ Smart project detection
- ✅ Consistent design patterns

### **Developer Experience**
- ✅ Comprehensive logging for debugging
- ✅ Clear component boundaries
- ✅ Consistent coding patterns
- ✅ Modular, maintainable architecture

### **Scalability Foundation**
- ✅ Authentication system ready for multi-app growth
- ✅ Project management scales to multiple content types
- ✅ AI integration patterns established
- ✅ Design system supports rapid feature development

---

*This architecture represents a solid foundation for DungeonMind's evolution from a single-purpose tool to a comprehensive D&D content creation platform, with clear patterns for scaling, integration, and innovation.* 