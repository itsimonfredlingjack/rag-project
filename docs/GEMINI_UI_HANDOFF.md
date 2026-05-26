# Gemini chat-first UI/UX handoff

This brief is for using Gemini as a visual UI/UX implementation assistant on the
constitutional RAG project. Keep its task narrow. Do not ask it to redesign the
backend, indexing, retrieval logic, runtime config or data pipeline.

## Current Status

- Branch: `portfolio-presentation-pass`.
- Worktree should be clean before giving Gemini a task.
- Frontend app: `apps/konstitutionell-frontend`.
- Frontend stack: React 19, TypeScript, Vite, Tailwind CSS, Zustand, Lucide,
  Framer Motion, optional Electron shell.
- Backend API: FastAPI under `backend/`.
- Main query stream endpoint:
  `/api/constitutional/agent/query/stream`.
- Runtime readiness truth:
  `backend/app/services/config_service.py`, then
  `/api/constitutional/ready`.
- ChromaDB, BM25 indexes and local model runtime are not bundled in the repo.

## Recommended Target

Use the web frontend first, not a separate desktop app.

Reason:

- Vite/React is already the primary UI surface.
- Electron already wraps the same frontend for local desktop use.
- A new standalone app would duplicate state, API contracts and styling.
- UI/UX iteration is faster in the browser with `npm run dev`.

Electron should only be touched for shell/runtime behavior, not visual design.

## Product Shape

This is not a marketing landing page and not a dashboard-first tool. It is a
chat-first research application for Swedish public-document RAG.

The primary object is the conversation. The first screen should immediately feel
like a serious research chat where the user can ask a question, see whether the
system is ready, and understand that answers will be grounded in public-document
sources.

The chat should be the center of gravity:

- initial chat/search state with strong prompt affordance
- active conversation with streaming answer
- visible citation/source affordances directly on answers
- compact readiness/model/runtime status where it matters
- recent questions or history available without dominating the screen

Cool supporting features should exist around the chat, not replace it:

- source and citation drawer
- document reader or source detail panel
- pipeline/status timeline
- filters/facets for narrowing sources
- technical inspector as an advanced secondary view
- keyboard-friendly controls for repeated research queries

## Hard Constraints

- Do not modify backend Python files.
- Do not modify indexing, scraper, systemd or startup scripts.
- Do not change API endpoint paths or response contracts.
- Do not remove SSE streaming behavior.
- Do not fake live data, source scores, citations or readiness.
- Do not present the system as a public product or legal advice tool.
- Do not add new design frameworks unless explicitly approved.
- Keep `nodeIntegration: false` and `contextIsolation: true` in Electron.
- Keep Swedish domain terminology accurate.

Allowed write scope for visual UI work:

- `apps/konstitutionell-frontend/src/**`
- `apps/konstitutionell-frontend/index.html`
- `apps/konstitutionell-frontend/README.md`
- `apps/konstitutionell-frontend/PRODUCTION_BUILD.md`
- `apps/konstitutionell-frontend/package.json` only if a dependency is truly
  needed and justified

Ask before touching:

- `backend/**`
- `scripts/**`
- `scrapers/**`
- `indexers/**`
- `systemd/**`
- root operational docs outside frontend UI documentation

## Visual Direction

Prefer a calm, professional chat-first research workspace:

- dense but readable layout
- strong information hierarchy
- chat as the primary first impression
- clear source review
- less decorative motion
- restrained dark theme or polished neutral theme
- accessible contrast
- predictable controls
- no large marketing hero
- no decorative 3D canvas unless it directly supports source inspection

Avoid:

- generic SaaS landing page
- vague consumer AI chatbot look
- dashboard-first layouts that make the query feel secondary
- oversized gradients and glowing decoration
- hiding citations behind pretty cards
- UI text that claims the system is production-ready

## Current Frontend Files To Inspect First

- `apps/konstitutionell-frontend/src/App.tsx`
- `apps/konstitutionell-frontend/src/stores/useAppStore.ts`
- `apps/konstitutionell-frontend/src/components/ui/HeroSection.tsx`
- `apps/konstitutionell-frontend/src/components/ui/ChatView.tsx`
- `apps/konstitutionell-frontend/src/components/ui/ChatInput.tsx`
- `apps/konstitutionell-frontend/src/components/ui/ChatMessage.tsx`
- `apps/konstitutionell-frontend/src/components/ui/AnswerWithCitations.tsx`
- `apps/konstitutionell-frontend/src/components/ui/PipelineVisualizer.tsx`
- `apps/konstitutionell-frontend/src/components/ui/HistorySidebar.tsx`
- `apps/konstitutionell-frontend/src/components/ui/FacetFilters.tsx`
- `apps/konstitutionell-frontend/src/components/ui/SearchInspector.tsx`
- `apps/konstitutionell-frontend/src/components/ui/DocumentReader.tsx`
- `apps/konstitutionell-frontend/src/index.css`

## Required Checks

Run from `apps/konstitutionell-frontend` after changes:

```bash
npm run lint
npm run build
npm audit
```

If Electron files or runtime scripts changed:

```bash
npm run electron:compile
timeout 18s npm run electron:dev
```

Known current lint state: lint passes, but React hook warnings may remain in
existing pipeline/result components. Do not hide warnings by disabling rules
unless there is a narrow, justified reason.

## Suggested Gemini Prompt

Use this as the starting prompt:

```text
You are working only on the React/Vite frontend of a Swedish public-document RAG application.

Repo path: apps/konstitutionell-frontend

Read docs/GEMINI_UI_HANDOFF.md and apps/konstitutionell-frontend/README.md first.

Goal:
Improve the visual UI/UX of the existing app as a chat-first research experience without changing backend contracts, SSE behavior, data models, or runtime scripts.

Make chat the center of gravity. Cool features should support the chat, not replace it.

Primary screens:
- initial chat/search state
- active conversation state with streaming answer
- source/citation review attached to answers
- document reader or source drawer
- history/sidebar
- filters/facets
- technical inspector as a secondary advanced view

Design direction:
Professional research chat, dense but readable, source-first, calm, high-trust Swedish public-document tooling. Do not make a marketing landing page or a dashboard-first layout. Do not fake readiness, citations or live data.

Allowed write scope:
- apps/konstitutionell-frontend/src/**
- apps/konstitutionell-frontend/index.html
- frontend README/docs only if needed

Do not touch:
- backend/**
- scripts/**
- scrapers/**
- indexers/**
- systemd/**
- API endpoint paths or response contracts

Before final answer run:
npm run lint
npm run build
npm audit

Return:
- files changed
- what visual/UX problem each change solves
- commands run and results
- any remaining warnings
```
