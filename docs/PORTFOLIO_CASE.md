# Portfolio Case: RAG-system för svenska offentliga dokument

## Problem

Svenska offentliga dokument är ofta utspridda över myndigheter, riksdagsmaterial, lagtext, rapporter och akademiska metadata. Ett vanligt RAG-problem är därför inte bara att generera text, utan att hitta rätt underlag, visa källor och hantera när systemet inte har tillräckligt stöd.

Det här projektet byggdes som ett personligt lärande- och portföljcase för att utforska hur långt man kan nå med stora svenska dokumentmängder på vanlig konsumenthårdvara (specifikt en konsument-GPU med 12 GB VRAM). Det belyser hela den praktiska kedjan från dokumentinsamling och indexering till retrieval, backend, frontend, testning och driftbarhet.

## Lösning

Systemet tar en fråga på svenska, hämtar möjliga källor från lokala index, rankar och väger dem, och streamar ett svar till frontend tillsammans med pipeline-status och källpanel.

Projektet visar särskilt:

- Hybrid retrieval: ChromaDB-vektorsökning och BM25/SQLite FTS5.
- Lokal LLM-integration via backendkonfiguration.
- Reranking och confidence-/graderingssteg (CRAG-inspirerat) före svarsgenerering.
- RAG-Fusion och Reciprocal Rank Fusion (RRF).
- React-frontend med fråga, svar, pipelinevy och källpanel.
- Eval- och testfrågor för att resonera om retrievalkvalitet och regressionsrisk.

## Teknik

| Lager | Huvudkomponenter |
|-------|------------------|
| Frontend | React 19, TypeScript, Vite, Tailwind, Three.js |
| API | FastAPI, Pydantic, SSE-streaming |
| Retrieval | ChromaDB, BM25/SQLite FTS5, RAG-Fusion/RRF |
| ML | Jina embeddings, Jina reranker, lokal LLM-runtime |
| Test/CI | pytest, ruff, eslint, TypeScript build, GitHub Actions |

## Vad Som Går Att Verifiera I Repot

- Backendens API-kontrakt, servicestruktur och en stor del av testsviten.
- Frontendens byggbarhet, lintning och koppling mot `VITE_BACKEND_URL`.
- RAG-pipelinekomponenter som retrieval orchestration, BM25-service, reranking- och promptlager.
- Evalstruktur, testfrågor och tidigare eval-resultat som projektartefakter.
- GitHub Actions för docs-check, backendtester och frontend build/lint.

Full retrieval med verkliga svar kräver däremot lokala modeller och databaser.

## Datakorpus och Begränsningar

Projektets skala skiljer sig mellan den publika distributionen och den historiska privata miljön:

- **Publik Demo:** Den distribuerade dataversionen är baserad enbart på säker öppen data, för närvarande riksdagsmaterial (verifierat till ca 230 143 rader från release-manifestet).
- **Historisk Privat Miljö:** Systemet utvecklades initialt mot en databas på ca 1,37 miljoner rader, vilket inkluderade DiVA-metadata och annat material. **DiVA-data och privata experimentindex ingår inte i detta repo.**

Övriga begränsningar:
- Repot är inte en publik tjänst och ska inte behandlas som en färdig produkt. Juridiska svar från systemet ska aldrig betraktas som auktoritativ rådgivning.
- Projektet innehåller experimentella delar för gradering, guardrails och critic/revise-flöden. De ska läsas som implementationer att lära av, inte som garanterat hallucinationsskydd.
- Fokus har legat på iterativ optimering (prompt engineering, kontextlängd, retrieval), inte fine-tuning av modellvikter.

## Screenshots

![Källpanel från tidigare lokal körning](assets/portfolio-query-with-sources.png)

![Pipelinevy från tidigare lokal körning](assets/portfolio-pipeline-view.png)

Screenshots ovan kommer från tidigare lokal körning. De visar frontendens sätt att presentera källor och pipeline-status, men repot innehåller inte den lokala databas som krävs för att reproducera samma fråga direkt efter klon.

## Lärdomar

Det viktigaste lärandet var att RAG-kvalitet inte sitter i en enda modell, speciellt inte under begränsade minneskrav (12 GB VRAM). Retrievalstrategi, dokumentstruktur, metadata, källurval, fallbackbeteende, evalfrågor och ärlig osäkerhet avgör lika mycket som själva LLM:en.
