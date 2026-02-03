# Constitutional AI - Testing Guide

## Overview
Comprehensive testing guide for Constitutional AI RAG system.

## Quick Start

### Running Tests
```bash
cd backend
./venv/bin/pytest tests/ -v
```

### Coverage Report
```bash
./venv/bin/pytest --cov=app tests/ --cov-report=html
```

## Test Coverage Analysis

### Critical Path Tests (Priority P0)
1. **Retrieval Tests**
   - ChromaDB connection
   - Embedding dimension validation (768 dims)
   - Query execution
   - Result parsing

2. **RAG Pipeline Tests**
   - Orchestrator service initialization
   - Multi-phase retrieval (1-4)
   - Confidence signal calculation
   - LLM generation

3. **API Endpoint Tests**
   - `/api/constitutional/health`
   - `/api/constitutional/agent/query`
   - `/api/constitutional/agent/query/stream`

### Integration Tests (Priority P1)
- Frontend → Backend communication
- WebSocket connections
- SSE streaming
- Error handling

### Unit Tests (Priority P2)
- Individual service tests
- Model validation
- Configuration parsing

## Testing Roadmap

### Week 1: Critical Path
- [ ] Retrieval service tests
- [ ] RAG pipeline tests
- [ ] API endpoint tests

### Week 2: Integration
- [ ] Frontend integration tests
- [ ] WebSocket tests
- [ ] End-to-end tests

### Week 3: Coverage
- [ ] Unit tests for all services
- [ ] Edge case tests
- [ ] Performance tests

### Week 4: Automation
- [ ] CI/CD integration
- [ ] Automated coverage reports
- [ ] Regression testing

## Test Templates

### Retrieval Test Template
```python
async def test_retrieval_basic():
    retrieval = get_retrieval_service()
    result = await retrieval.search(query="grundlag", k=10)
    assert result.success
    assert len(result.results) > 0
```

### RAG Test Template
```python
async def test_rag_query():
    orchestrator = get_orchestrator_service()
    result = await orchestrator.process_query(
        question="Vad är GDPR?",
        mode="evidence"
    )
    assert len(result.sources) > 0
    assert len(result.answer) > 0
```

## Known Issues

### Embedding Dimension Mismatch (RESOLVED)
- **Issue**: Function expected enum but received string
- **Fix**: Added type check in `retrieval_service.py` lines 419, 457
- **Status**: ✅ Fixed in commit b07b288

### Backend Port Conflict (RESOLVED)
- **Issue**: Multiple backends on same port
- **Fix**: Moved active backend to port 8900
- **Status**: ✅ Fixed in commit b07b288

## Test Results Summary

| Component | Tests | Pass | Fail | Coverage |
|------------|--------|-------|-------|----------|
| Retrieval | - | - | - | - |
| RAG Pipeline | - | - | - | - |
| API Endpoints | - | - | - | - |
| Services | - | - | - | - |

**Note**: Test framework setup in progress

## References

### Historical Reports
- `TEST_COVERAGE_ANALYSIS.md` (deleted - migrated here)
- `TESTING_INDEX.md` (deleted - migrated here)
- `TESTING_QUICK_START.md` (deleted - migrated here)
- `TESTING_ROADMAP.md` (deleted - migrated here)
- `TEST_SUMMARY_REPORT.md` (deleted - migrated here)

### System Documentation
- `RAG_FIX_REPORT.md` - RAG system bug fixes
- `SYSTEM_STATUS_REPORT.md` - Current system status
- `README.md` - Main project documentation

---

**Created**: 2026-01-04
**Status**: Consolidated from 5 docs → 1
**Next Steps**: Implement test framework and run first tests
