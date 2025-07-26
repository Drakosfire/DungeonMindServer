# CardGenerator Visual Refresh Document

## Design Philosophy

### Core Principles
- **Mobile-First Design**: Every component and layout should work seamlessly on mobile devices
- **Progressive Enhancement**: Start with core functionality, enhance with advanced features
- **Thematic Consistency**: Maintain fantasy/D&D aesthetic while modernizing the interface
- **Intuitive Workflow**: Guide users through the creation process with clear visual hierarchy

### Visual Direction
- **Evolutionary, Not Revolutionary**: Build upon existing parchment + dark sidebar foundation
- **Enhanced Color System**: Introduce rarity-based accent colors and improved contrast
- **Component-Driven**: Establish reusable design system for entire DungeonMind platform
- **Dynamic Emphasis**: Adapt interface prominence based on current step in workflow

## New Workflow Design

### Revised Step Flow
```
Step 1: Text Description & Generation
Step 2: Core Image (Upload/Generate) 
Step 3: AI Border Analysis & Generation
Step 4: Card Back Generation
Step 5: Final Assembly & Gallery
```

### Navigation System

**Primary Navigation**: Horizontal tab system with mobile optimization
- **Desktop**: Full-width tabs with step labels and icons
- **Mobile**: Scrollable horizontal tabs with condensed labels
- **State Indicators**: 
  - ✓ Completed (green accent)
  - ● Current (primary blue)
  - ○ Pending (muted gray)
  - ⚠ Error state (warning red)

**Secondary Navigation**: Contextual actions within each step
- Previous/Next buttons always visible
- Step-specific actions (Generate, Upload, Edit, etc.)
- Quick access to "My Cards" gallery

## Component Library Specification

### Color Palette Evolution

**Base Colors** (Existing):
- `--parchment-base`: #f4f1e8
- `--sidebar-dark`: #3a3a52
- `--text-primary`: #2d2d2d

**New Accent System**:
- `--primary-blue`: #4a90e2 (interactive elements)
- `--success-green`: #7ed321 (completed states)
- `--warning-amber`: #f5a623 (attention states)
- `--error-red`: #d0021b (error states)

**Rarity Colors**:
- `--common-gray`: #9b9b9b
- `--uncommon-green`: #1eff00
- `--rare-blue`: #0070dd
- `--epic-purple`: #a335ee
- `--legendary-orange`: #ff8000

### Typography System

**Primary Font**: Continue with Balgruf for thematic consistency
**Secondary Font**: System fonts for UI elements (better performance)

**Scale**:
- `--text-xs`: 12px (captions, metadata)
- `--text-sm`: 14px (form labels, secondary content)
- `--text-base`: 16px (body text)
- `--text-lg`: 18px (section headers)
- `--text-xl`: 24px (step titles)
- `--text-2xl`: 32px (page title)

### Button System

**Primary Button**:
```css
.btn-primary {
  background: linear-gradient(135deg, #4a90e2, #357abd);
  color: white;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 600;
  box-shadow: 0 4px 12px rgba(74, 144, 226, 0.3);
  transition: all 0.2s ease;
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(74, 144, 226, 0.4);
}
```

**Secondary Button**:
- Outline style with primary color border
- Background transparent/white
- Same padding and typography as primary

**Icon Buttons**:
- Circular design for single actions
- Square design for toggle states
- Consistent 40px minimum touch target

### Card Components

**Step Card Container**:
```css
.step-card {
  background: var(--parchment-base);
  border: 2px solid var(--primary-blue);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  margin-bottom: 16px;
}
```

**Preview Card**:
- Adaptive sizing based on screen real estate
- Mobile: Full width with 16:9 aspect ratio
- Desktop: Fixed dimensions with centered positioning
- Drop shadow to emphasize importance

### Form Elements

**Input Fields**:
- Consistent padding (12px 16px)
- Border radius 8px
- Focus states with primary color
- Error states with validation messaging
- Floating labels for better UX

**Upload Areas**:
- Drag & drop visual feedback
- Progress indicators for uploads
- Preview thumbnails with removal options

## Layout Architecture

### Mobile-First Grid System

**Breakpoints**:
- `mobile`: < 768px
- `tablet`: 768px - 1024px  
- `desktop`: > 1024px

**Step 1: Text Description**
- **Mobile**: Single column, full-width form
- **Desktop**: Split layout - form left (60%), preview right (40%)

**Step 2: Core Image**
- **Mobile**: Stacked - upload area, then generated options
- **Desktop**: Side-by-side - upload left, gallery right

**Step 3: Border Generation**
- **Mobile**: Vertical flow - analysis preview, then border options
- **Desktop**: Three columns - analysis, options, preview

**Step 4: Card Back**
- **Mobile**: Stacked - controls, then preview
- **Desktop**: Split - controls left, preview right

**Step 5: Gallery**
- **Mobile**: Single column grid with large cards
- **Desktop**: 3-column masonry layout

### Progressive Enhancement

**Core Experience** (all devices):
- Text input and basic navigation
- Image upload functionality
- Basic card preview

**Enhanced Experience** (larger screens):
- Side-by-side previews
- Advanced animation
- Larger interaction targets

**Premium Experience** (desktop):
- Drag & drop everywhere
- Keyboard shortcuts
- Multi-panel layouts

## Interaction Design

### Micro-Interactions

**Loading States**:
- Skeleton screens for content loading
- Animated spinners for processing
- Progress bars for multi-step operations

**Success Feedback**:
- Subtle animations for completed actions
- Toast notifications for major state changes
- Checkmarks for validation success

**Error Handling**:
- Inline validation with immediate feedback
- Toast notifications for system errors
- Clear recovery actions

### Animation Strategy

**Page Transitions**:
- Slide transitions between steps (mobile)
- Fade transitions between content areas (desktop)
- Maintain spatial orientation

**Content Animations**:
- Fade-in for new content
- Scale animation for image previews
- Subtle hover states for interactive elements

## Accessibility Considerations

### Keyboard Navigation
- Tab order follows logical flow
- All interactive elements accessible via keyboard
- Clear focus indicators

### Visual Accessibility
- Minimum 4.5:1 contrast ratios
- Color not the only indicator of state
- Scalable text up to 200%

### Screen Reader Support
- Semantic HTML structure
- ARIA labels for complex interactions
- Live regions for dynamic content updates

## Implementation Priority

### Phase 1: Foundation
1. Establish new color palette and typography
2. Create base component library
3. Implement new navigation system
4. Mobile-responsive grid layout

### Phase 2: Enhanced UX
1. Advanced form components
2. Loading and error states
3. Animation system
4. Toast notification system

### Phase 3: Polish
1. Micro-interactions
2. Advanced accessibility features
3. Performance optimizations
4. Cross-platform testing

## Success Metrics

### User Experience
- Reduced time to complete card creation
- Decreased abandonment rate at each step
- Improved mobile usage analytics

### Technical Performance
- Page load times under 2 seconds
- Component reusability across platform
- Consistent design language adoption

### Platform Integration
- Design system adoption in other tools
- Component library documentation
- Developer productivity improvements

## Next Steps

1. Create high-fidelity mockups for each step
2. Build component library in Storybook
3. Implement mobile-first responsive layouts
4. User testing with existing users
5. Iterative refinement based on feedback

This visual refresh will establish the foundation for the entire DungeonMind platform's design evolution, starting with the CardGenerator as the flagship experience. 