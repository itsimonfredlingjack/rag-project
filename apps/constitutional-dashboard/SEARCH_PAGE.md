# Search Page - Complete Documentation

## Overview
Constitutional Dashboard search page provides advanced document retrieval with real-time filtering.

## Quick Start
Add the SearchPage component to your dashboard:
```tsx
import SearchPage from './SearchPage';
```

## Integration
Connect to backend API:
```typescript
const API_BASE = 'http://localhost:8900';
```

## Layout
Grid layout with:
- Search bar (top)
- Filters sidebar (left)
- Results grid (center)
- Source panel (right)

## Examples
See `examples/` directory for usage patterns.

## API Endpoints
- `GET /api/constitutional/search` - Search documents
- `POST /api/constitutional/agent/query` - AI-powered query
- `WS /ws/harvest` - Real-time harvest updates

## Implementation Status
✅ Phase 1 Complete - All features implemented

For detailed technical documentation, see:
- Layout specs: (historical)
- Integration guide: (historical)
- Examples: `examples/` directory

**Generated**: 2026-01-04
**Status**: Production Ready
