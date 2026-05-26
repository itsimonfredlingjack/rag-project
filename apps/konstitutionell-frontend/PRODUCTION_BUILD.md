# Frontend Build Notes

Historisk build-notering för frontendprojektet. Den här filen beskriver vilka kommandon som används för lokal verifiering, men ska inte läsas som ett påstående om att projektet är en publik produktionstjänst.

## Lokal Verifiering

```bash
npm ci
npm run lint
npm run build
npm run preview
```

## Teknik

- React 19
- TypeScript 5.9
- Vite 7
- Three.js / React Three Fiber
- Tailwind CSS 4

## Miljö

| Variabel | Syfte |
|----------|-------|
| `VITE_BACKEND_URL` | Bas-URL till lokal FastAPI-backend |
| `VITE_SCORE_THRESHOLD_GOOD` | Visuell scoregräns för hög relevans |
| `VITE_SCORE_THRESHOLD_OK` | Visuell scoregräns för medel relevans |

Full fråga-till-svar kräver lokal backend, corpusindex och LLM-runtime. Se [README.md](README.md) för frontendens aktuella körinstruktioner.
