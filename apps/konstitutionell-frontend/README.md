# Frontend: RAG-system för svenska offentliga dokument

React/TypeScript-frontend för portföljprojektet. Gränssnittet låter användaren skriva en fråga, följa pipeline-status och se svar, källor och källdetaljer från FastAPI-backenden.

Det här är inte en fristående publik tjänst. Frontenden kräver en körande backend för verkliga RAG-svar.

## Teknik

- React 19
- TypeScript 5.9
- Vite 7
- Tailwind CSS 4
- Zustand
- Three.js via React Three Fiber och Drei
- Framer Motion
- Lucide React

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
src/
├── App.tsx                    Root med 3D-bakgrund och UI-overlay
├── components/3d/             Substrate, source viewer och connector logic
├── components/ui/             Frågefält, chatvy, pipeline, källor och citations
├── stores/useAppStore.ts      Zustand-store och SSE-hantering
├── types/queryResult.ts       UI-typer för svar, källor och pipeline
├── constants.ts               Timing, historik och UI-konstanter
└── theme/colors.ts            Färgtema
```

## Backendkoppling

Frontendens store (`src/stores/useAppStore.ts`) öppnar en streaming request mot backend och uppdaterar UI:t med inkommande SSE-events. Utan backend visas inga verkliga källor eller svar.

För full lokal verifiering krävs därför:

- FastAPI-backend på `VITE_BACKEND_URL`.
- ChromaDB-/BM25-data i backendmiljön.
- Lokal LLM-runtime som backenden kan nå via `CONST_LLM_BASE_URL`.

## Screenshot-Notis

Screenshots i `docs/assets/` kan komma från tidigare lokal körning. De ska inte tolkas som en färdig publik demo, eftersom lokal corpusdata och modellruntime inte ingår i repot.
