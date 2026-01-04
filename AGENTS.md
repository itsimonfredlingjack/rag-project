# AGENTS.md - Guide for AI Coding Agents

This guide is for agentic coding assistants working in this Constitutional AI repository.

## Project Overview

Swedish government document RAG system with 521K+ ChromaDB documents.
- **Backend**: FastAPI (port 8000) in `/` and `backend/`
- **Frontend**: React/Vite apps in `apps/constitutional-gpt` (port 3000) and `apps/constitutional-dashboard`
- **Vector DB**: ChromaDB in `chromadb_data/`
- **LLM**: Ollama (port 11434) with `ministral-3:14b` primary, `gpt-sw3:6.7b` fallback

## Build, Lint, and Test Commands

### Python (Backend, Scrapers, Juridik-AI)

```bash
# Install dependencies
pip install -r requirements.txt
pip install -e backend/

# Linting with Ruff
ruff check .                    # Check for issues
ruff check --fix .              # Auto-fix issues
ruff format .                   # Format code

# Type checking (optional)
mypy .

# Run tests
pytest                          # All tests
pytest tests/ -v                # Tests in tests/
pytest juridik-ai/tests/ -v     # Tests in juridik-ai/
pytest tests/test_adaptive_retrieval.py -v  # Single test file
pytest -k "test_search"         # Tests matching pattern

# Pre-commit hooks (install first with: pre-commit install)
pre-commit run --all-files
```

### TypeScript (Frontend Apps)

```bash
# In apps/constitutional-gpt or apps/constitutional-dashboard
npm install                     # Install dependencies
npm run dev                     # Dev server
npm run build                   # Production build
npm run lint                    # ESLint
npm run preview                 # Preview production build
```

## Code Style Guidelines

### Python

**Imports** (enforced by Ruff):
```python
# Standard library
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Third-party
import requests
from bs4 import BeautifulSoup
import chromadb

# Local
from utils.rate_limiter import RateLimiter
from scrapers.base import BaseScraper
```

**Type Hints** (Required):
```python
def fetch_document(url: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
    """Fetches a document from the given URL."""
    ...
```

**Naming Conventions**:
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

**Error Handling**:
```python
try:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
except requests.Timeout:
    logger.warning(f"Timeout for {url}")
    return None
except requests.HTTPError as e:
    logger.error(f"HTTP error for {url}: {e}")
    return None
```

**Formatting**: Double quotes, line length 100, f-strings for formatting

### TypeScript/React

**Components**: Function components with hooks only
```typescript
export function SearchResults({ query, limit = 10 }: SearchResultsProps) {
  const [results, setResults] = useState<SearchResult[]>([]);
  return <div>...</div>;
}
```

**Imports**:
```typescript
// React/Next
import { useState, useEffect } from 'react';

// External
import { motion } from 'framer-motion';

// Internal
import { cn } from '@/lib/utils';

// Types
import type { SearchResult } from '@/types';
```

**Styling**: Tailwind CSS with `cn()` utility for conditional classes

## Critical Guardrails

1. **NEVER delete files** without explicit user permission - especially `gemmis-os-ui`, ChromaDB data, or backups
2. **NEVER start services** without checking ports first:
   - `lsof -i :8000` (backend), `:3000` (frontend), `:11434` (Ollama)
3. **ALWAYS read code** before modifying - use `grep` to find related code
4. **ALWAYS check endpoints** before claiming they don't exist: `curl http://localhost:8000/docs`

## Configuration Files

- `pyproject.toml` - Ruff, pytest, mypy settings (line length: 100)
- `.pre-commit-config.yaml` - Pre-commit hooks (ruff, ruff-format, eslint)
- `.cursorrules` - Additional project rules (Swedish/English mix)
- `CONTRIBUTING.md` - Detailed contribution guidelines

## Testing Notes

- Python tests in `tests/` and `juridik-ai/tests/`
- Frontend tests in `apps/constitutional-gpt/` (using Vitest)
- Run single test: `pytest tests/test_specific.py::test_function_name -v`
- Test coverage currently ~15-20%, goal is 75%+

## Service Management

```bash
# Backend (simons-ai-backend)
systemctl --user status simons-ai-backend
journalctl -u simons-ai-backend -f

# Frontend (constitutional-gpt)
systemctl --user status constitutional-gpt

# Ollama
ollama ps
ollama list
```
