# Frontend: RAG-system för svenska offentliga dokument

React/TypeScript-frontend för portföljprojektet. Frontenden använder FastAPI-backenden för streaming-svar, källor, pipeline-status och källdetaljer.

## Teknik

- React 19
- TypeScript 5.9
- Vite 7
- Tailwind CSS 4
- Zustand
- Framer Motion
- Lucide React
- Electron development shell

## Miljövariabler

Kopiera exempelkonfigurationen vid behov:

```bash
cp .env.example .env
```

| Variabel | Default | Syfte |
|----------|---------|-------|
| `VITE_BACKEND_URL` | `http://localhost:8900` | Bas-URL till FastAPI-backend |
| `VITE_SCORE_THRESHOLD_GOOD` | `0.7` | Visuell gräns för hög källscore |
| `VITE_SCORE_THRESHOLD_OK` | `0.5` | Visuell gräns för medel källscore |

Frontenden skickar RAG-frågor till:

```text
${VITE_BACKEND_URL}/api/constitutional/agent/query/stream
```

## Kör Lokalt

```bash
npm ci
npm run dev
```

Vite kör normalt på `http://localhost:3003`.

## Lint Och Build

```bash
npm run lint
npm run build
```

Preview av produktionsbuild:

```bash
npm run preview
```

## Viktiga Mappar

```text
electron/
├── main.ts                    Electron main process for desktop dev/runtime
└── preload.ts                 Minimal context-isolated bridge

src/
├── App.tsx                    Shell: sidebar, header, chat/search and split results layout
├── components/ui/             Chat, pipeline, facets, document reader, inspector and citations
├── stores/useAppStore.ts      Zustand-store, SSE handling and query history
├── types/queryResult.ts       UI types for answers, sources and pipeline state
├── constants.ts               Timing, history and UI constants
└── theme/colors.ts            Color theme
```

## Backendkoppling

Frontendens store (`src/stores/useAppStore.ts`) öppnar en streaming request mot backend och uppdaterar UI:t med inkommande SSE-events. Utan backend visas inga verkliga källor eller svar.

För full lokal verifiering krävs därför:

- FastAPI-backend på `VITE_BACKEND_URL`.
- ChromaDB-/BM25-data i backendmiljön.
- Lokal LLM-runtime som backenden kan nå via `CONST_LLM_BASE_URL`.

## Screenshot-Notis

Screenshots i `docs/assets/` kan komma från tidigare lokal körning. De ska inte tolkas som en färdig publik demo, eftersom lokal corpusdata och modellruntime inte ingår i repot.
