# DungeonMind Storage System Architecture
## Comprehensive Guide to State Management and Persistence

### 🎯 **Executive Summary**

DungeonMind uses a multi-layered storage architecture that combines real-time session management, persistent project storage, and global object persistence. The system is designed to support multiple tools (CardGenerator, StoreGenerator, RulesLawyer, etc.) with unified state management while maintaining tool-specific functionality.

---

## 🏗️ **Storage Architecture Overview**

```
┌─────────────────────────────────────────────────────────────┐
│                    DungeonMind Storage Layers               │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Client-Side State (React/LocalStorage)           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Component   │  │ LocalStorage│  │ Memory Cache│        │
│  │ State       │  │ Backup      │  │ (Session)   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Global Session Management (Backend Memory)       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Session     │  │ Tool-Specific│  │ Cross-Tool  │        │
│  │ Manager     │  │ State       │  │ Context     │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Project Management (Firestore)                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Projects    │  │ Named Saves │  │ Collections │        │
│  │ (cardgen_   │  │ (card_      │  │ (user       │        │
│  │ projects)   │  │ sessions)   │  │ workspaces) │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Global Object Store (Firestore)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ DungeonMind │  │ Shared      │  │ Public      │        │
│  │ Objects     │  │ Objects     │  │ Templates   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 **Data Models and Relationships**

### **1. Global Session State**

**Location**: Backend Memory (`session_management.py`)

```typescript
interface EnhancedGlobalSession {
    // Session Identity
    session_id: string;
    user_id?: string;
    created_at: datetime;
    last_accessed: datetime;
    expires_at: datetime;
    
    // Tool-Specific States
    cardgenerator?: CardGeneratorSessionState;
    storegenerator?: StoreGeneratorSessionState;
    ruleslawyer?: RulesLawyerSessionState;
    statblockgenerator?: StatblockGeneratorSessionState;
    
    // Global Context
    active_world_id?: string;
    active_project_id?: string;
    current_tool: string;
    
    // Cross-Tool Features
    clipboard: string[];              // Object IDs
    recently_viewed: string[];        // Object IDs
    pinned_objects: string[];         // Object IDs
    
    // User Preferences
    preferences: GlobalSessionPreferences;
}
```

**Purpose**: 
- Maintains working state across browser sessions
- Provides cross-tool context and clipboard
- Manages tool switching and context preservation
- Handles session expiration and cleanup

### **2. CardGenerator Session State**

**Location**: Tool-specific state within Global Session

```typescript
interface CardGeneratorSessionState {
    // Current Work
    current_step: StepId;
    active_item_id?: string;
    draft_item_data?: object;
    
    // Step Progress
    step_completion: Record<string, boolean>;
    generation_locks: Record<string, boolean>;
    
    // Project Context
    current_project_id?: string;
    recent_items: string[];
    
    // Visual Assets
    generated_images: string[];
    selected_assets: Record<string, string>;
    
    // User Preferences
    preferences: Record<string, any>;
}
```

### **3. Project Data Structure**

**Location**: Firestore collection `cardgen_projects`

```typescript
interface CardGeneratorProject {
    id: string;
    user_id: string;
    name: string;
    description: string;
    
    // Timestamps
    created_at: number;
    updated_at: number;
    
    // Project Data
    state: CardSessionData;           // Complete working state
    metadata: ProjectMetadata;
    
    // Organization
    is_template: boolean;
    tags: string[];
}

interface CardSessionData {
    sessionId: string;
    userId: string;
    currentStep: string;
    stepCompletion: Record<string, boolean>;
    itemDetails: ItemDetails;
    selectedAssets: SelectedAssets;
    generatedContent: GeneratedContent;
    metadata: SessionMetadata;
}
```

### **4. Global Objects**

**Location**: Firestore collection `dungeonmind-objects`

```typescript
interface DungeonMindObject {
    id: string;
    type: ObjectType;
    name: string;
    description?: string;
    
    // System Integration
    systemData?: Record<string, any>;
    rulesets?: string[];
    
    // Relationships
    references?: Reference[];
    collections?: string[];
    
    // Metadata
    metadata: ObjectMetadata;
    
    // Sharing
    visibility: 'private' | 'project' | 'public';
    sharePermissions?: SharePermissions;
}
```

---

## 🔄 **Data Flow Architecture**

### **Complete Save/Load Cycle**

```
User Action → Component State → Global Session → Project Storage → Object Store
     ↓              ↓                ↓               ↓              ↓
  Immediate    Auto-debounced    Cross-tool      Named saves    Permanent
  feedback     (2 seconds)       context         collections    objects
     ↓              ↓                ↓               ↓              ↓
LocalStorage ← Session Memory ← Tool State ← Project Data ← Global Objects
```

### **1. Real-Time State Management**

**Frontend Flow**:
```typescript
// Component updates local state
setItemDetails(newDetails);

// CardGenerator provider updates global session
await globalSession.updateToolState({
    draft_item_data: newDetails,
    step_completion: { ...completion, currentStep: true }
});

// Automatic localStorage backup
localStorage.setItem('cardGenerator_backup', JSON.stringify(state));
```

**Backend Flow**:
```python
# Session manager updates tool state
await session_manager.update_cardgenerator_state(
    session_id, 
    {
        "draft_item_data": new_details,
        "step_completion": completion_status
    }
)

# Cross-tool context update
session.add_to_recent_objects(object_id)
session.update_clipboard(clipboard_items)
```

### **2. Project Persistence**

**Save Project**:
```typescript
// Frontend: Save current state as named project
const projectData = {
    name: "Fire Sword Collection",
    description: "Magical weapons for campaign",
    state: currentCardGeneratorState
};

await projectAPI.createProject(projectData);
```

**Backend Storage**:
```python
# Save complete project to Firestore
project_doc = {
    "id": project_id,
    "user_id": user_id,
    "name": request.name,
    "state": complete_card_session_data,
    "metadata": project_metadata
}

firestore_utils.add_document('cardgen_projects', project_id, project_doc)

# Update global session context
await session_manager.update_tool_state(session_id, "cardgenerator", {
    "activeProjectId": project_id,
    "current_project_id": project_id
})
```

### **3. Global Object Creation**

**Convert Card to Global Object**:
```typescript
// Frontend: Promote working card to global object
const objectData = {
    type: 'item',
    name: itemDetails.name,
    description: itemDetails.description,
    systemData: {
        dnd5e: {
            rarity: itemDetails.rarity,
            damage: itemDetails.damageFormula
        }
    }
};

const globalObject = await globalSession.saveAsGlobalObject(objectData);
```

**Backend Processing**:
```python
# Convert to DungeonMindObject
dungeon_object = DungeonMindObject(
    type=ObjectType.ITEM,
    name=item_data.name,
    description=item_data.description,
    createdBy=user_id,
    visibility='private',
    systemData=system_specific_data
)

# Save to global object store
object_id = await dungeonmind_db.save_object(dungeon_object)

# Update session context
session.add_to_recent_objects(object_id)
```

---

## 🔧 **Implementation Strategy**

### **Current State Analysis**

**Working Components**:
- ✅ Global Session Manager (backend)
- ✅ Basic tool state updates
- ✅ Project creation and management
- ✅ Firestore persistence
- ✅ LocalStorage backup

**Integration Issues**:
- 🔄 **Dual Persistence Systems**: Old CardGenerator persistence vs. new global sessions
- 🔄 **Data Model Mismatches**: Different schemas in different layers
- 🔄 **Session Recovery**: Incomplete integration between localStorage and global sessions
- 🔄 **Cross-Tool Context**: Limited implementation of clipboard/recent objects

### **Integration Fixes Required**

#### **1. Unified CardGenerator State Management**

**Problem**: CardGenerator has its own persistence (`firestorePersistence.ts`) running parallel to global sessions.

**Solution**:
```typescript
// Remove direct Firestore calls from CardGenerator
// Replace with global session integration

// OLD (remove):
await saveCardSession(state, templateBlob, userId);

// NEW (implement):
await globalSession.updateToolState({
    draft_item_data: state.itemDetails,
    selected_assets: state.selectedAssets,
    step_completion: state.stepCompletion
});

// Auto-save projects through global session
await globalSession.saveCurrentProject();
```

#### **2. Standardize Data Models**

**Problem**: Different data structures used across layers.

**Solution**: Create conversion layers:
```python
# Backend conversion utilities
def convert_legacy_card_session_to_tool_state(legacy_session: CardSessionData) -> CardGeneratorSessionState:
    return CardGeneratorSessionState(
        current_step=StepId(legacy_session.currentStep),
        draft_item_data=legacy_session.itemDetails,
        selected_assets=legacy_session.selectedAssets,
        step_completion=legacy_session.stepCompletion
    )

def convert_tool_state_to_project_data(tool_state: CardGeneratorSessionState) -> CardSessionData:
    # Convert back for project storage
    pass
```

#### **3. Session Recovery Protocol**

**Implementation**:
```typescript
// On app initialization
const initializeCardGenerator = async () => {
    // 1. Try to restore global session
    const globalSession = await GlobalSessionAPI.restoreSession();
    
    if (globalSession.cardgenerator) {
        // Use global session state
        return globalSession.cardgenerator;
    }
    
    // 2. Try localStorage backup
    const localBackup = localStorage.getItem('cardGenerator_backup');
    if (localBackup) {
        // Convert and migrate to global session
        const state = JSON.parse(localBackup);
        await globalSession.updateToolState(convertLegacyState(state));
        return state;
    }
    
    // 3. Return default state
    return getDefaultCardGeneratorState();
};
```

---

## 🚀 **Recommended Migration Path**

### **Phase 1: Backend Integration** (Priority: High)
1. **Enhance CardGenerator Router**:
   - Integrate existing save endpoints with global session manager
   - Update data models to use unified schemas
   - Add conversion utilities for legacy data

2. **Fix Session State Updates**:
   - Ensure all CardGenerator state changes update global session
   - Implement proper tool state serialization
   - Add session persistence to Firestore as backup

### **Phase 2: Frontend Unification** (Priority: High)
1. **Replace Direct Persistence**:
   - Remove `firestorePersistence.ts` direct calls
   - Route all saves through `useGlobalSession` hook
   - Implement debounced auto-save through global session

2. **Update CardGenerator Provider**:
   - Fully integrate with global session state
   - Remove duplicate state management
   - Implement proper loading states

### **Phase 3: Enhanced Features** (Priority: Medium)
1. **Cross-Tool Integration**:
   - Implement clipboard functionality
   - Add recent objects tracking
   - Enable object sharing between tools

2. **Advanced Project Management**:
   - Add project templates
   - Implement project sharing
   - Enable collaborative editing

### **Phase 4: Performance Optimization** (Priority: Low)
1. **Caching Strategy**:
   - Implement Redis for session caching
   - Add CDN for static assets
   - Optimize Firestore queries

2. **Scaling Preparation**:
   - Add database indexing
   - Implement connection pooling
   - Add monitoring and analytics

---

## 📋 **Troubleshooting Guide**

### **CRITICAL ISSUE ARCHIVE**

#### **🚨 STATE DATA NOT PERSISTING TO FIRESTORE (RESOLVED)**

**Date Discovered**: July 2025
**Severity**: Critical - Complete data loss on load
**Status**: ✅ RESOLVED

**Symptoms**:
- Frontend shows complete form data (type: "Weapon", rarity: "Legendary", value: "52500 gp")
- Save operation returns 200 OK
- Backend logs show complete data received
- After refresh/reload, only name and description persist, all other fields empty

**Root Cause**:
```python
# BUG: In cardgenerator_project_router.py update_project function
# The state data was NEVER being saved to Firestore!

update_data = {
    'updated_at': current_time
}

if request.name is not None:
    update_data['name'] = request.name
    
if request.description is not None:
    update_data['description'] = request.description
    
if request.metadata is not None:
    update_data['metadata'] = request.metadata.dict()

# ❌ MISSING: No handling of request.state!
# Result: State data silently ignored, never saved to database
```

**The Fix**:
```python
# ✅ CRITICAL FIX: Add state persistence
if request.state is not None:
    update_data['state'] = request.state.dict()
    logger.info(f"💾 SAVING STATE TO FIRESTORE: {request.state.dict()}")
```

**Debugging Process That Led to Discovery**:
1. **Save Pipeline**: ✅ Frontend → Backend (complete data transmitted)
2. **Backend Processing**: ✅ Data received and logged correctly  
3. **Database Write**: ❌ State field never included in Firestore update
4. **Load Pipeline**: ❌ Missing state data from database

**Diagnostic Commands**:
```bash
# Check what's actually in Firestore
# Look for 'state' field in cardgen_projects collection

# Enhanced logging to add:
logger.info(f"Raw project_data keys: {list(project_data.keys())}")
logger.info(f"Raw state from database: {project_data.get('state', {})}")
```

**Prevention Strategy**:
- ✅ Added comprehensive save/load debugging 
- ✅ Added explicit state field handling
- ✅ Added validation logging for all update_data fields

**Lesson Learned**: Always verify that ALL request fields are handled in update operations, especially when using selective field updates.

---

### **Common Issues and Solutions**

#### **1. State Not Persisting**
**Symptoms**: User changes lost on refresh
**Diagnosis**:
```bash
# Check global session status
curl -X GET "http://localhost:8000/api/session/status" --cookie "dungeonmind_session_id=SESSION_ID"

# Check localStorage
console.log(localStorage.getItem('cardGenerator_backup'));

# Check Firestore
# Look in collections: card_sessions, cardgen_projects
```

**Solutions**:
- Verify session authentication
- Check network connectivity
- Validate data model schemas
- Confirm Firestore permissions

#### **2. Session Not Restoring**
**Symptoms**: App starts with default state despite previous work
**Diagnosis**:
- Check session cookie existence
- Verify backend session manager has session
- Check for data model mismatches
- Confirm user authentication status

#### **3. Project Load Failures**
**Symptoms**: Projects exist but won't load
**Diagnosis**:
- Verify project ownership
- Check data model compatibility
- Confirm Firestore access permissions
- Validate project document structure

---

## 🔮 **Future Architecture Evolution**

### **MCP Server Integration**
```typescript
// Future: MCP-compatible object management
interface MCPDungeonMindServer {
    createObject(request: MCPObjectRequest): Promise<DungeonMindObject>;
    loadProject(projectId: string): Promise<ProjectData>;
    syncToVTT(objectIds: string[]): Promise<VTTExportData>;
}
```

### **Multi-Tenant Architecture**
```python
# Future: Organization-level sharing
class OrganizationContext:
    def __init__(self, org_id: str):
        self.shared_projects = SharedProjectManager(org_id)
        self.shared_objects = SharedObjectManager(org_id)
        self.collaboration_tools = CollaborationManager(org_id)
```

### **Real-Time Collaboration**
```typescript
// Future: Live collaboration features
interface CollaborativeSession {
    joinProject(projectId: string): Promise<void>;
    syncChanges(changes: ProjectChanges): Promise<void>;
    handleConflicts(conflicts: ChangeConflict[]): Promise<Resolution>;
}
```

---

## 📊 **Success Metrics**

### **Performance Targets**
- Session recovery: < 500ms
- Save operations: < 2s
- Cross-tool navigation: < 200ms
- Project loading: < 1s

### **Reliability Targets**
- Data persistence: 99.9%
- Session recovery: 99.5%
- Cross-browser compatibility: 100%
- Network failure graceful degradation: 95%

---

**This architecture provides a robust foundation for DungeonMind's evolution into a comprehensive TTRPG content creation platform, with clear separation of concerns, reliable data persistence, and seamless user experience across all tools.**