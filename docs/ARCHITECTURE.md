# Svensk RAG Architecture

Detta dokument är en navigeringssida. Arkitekturens källa till sanning finns här:

1. [`docs/SYSTEM_SNAPSHOT.md`](SYSTEM_SNAPSHOT.md)
2. [`docs/architecture/current-system.mmd`](architecture/current-system.mmd)
3. [`docs/architecture/intended-system.mmd`](architecture/intended-system.mmd)

## Regler

- Uppdatera snapshot med `python scripts/generate_system_snapshot.py` vid större backend/frontend/RAG-förändringar.
- Uppdatera Mermaid-diagrammen när arkitekturflödet eller tjänstegränser ändras.
- Legacy API-prefix `/api/constitutional/*` är kvar för kompatibilitet; ny publik dokumentation ska använda `/api/svensk-rag/*`.

## Migrationsnotering

Interna namn som `constitutional_routes.py`, `CONST_` miljövariabler och vissa klass-/fältnamn är kvar tills vidare för att undvika brytande ändringar.
