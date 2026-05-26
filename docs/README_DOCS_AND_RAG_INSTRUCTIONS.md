# Dokumentationskarta

Det här dokumentet pekar ut vilka docs som är lämpliga att läsa först när repot
delas offentligt som portföljcase.

## Publik Förstaläsning

- `README.md` - huvudpresentation, arkitektur, begränsningar och kom igång.
- `docs/PORTFOLIO_CASE.md` - kortare case-sida för snabb överblick.
- `docs/QUICK_START.md` - lokal snabbstart utan privat ChromaDB-data.
- `docs/ARCHITECTURE.md` - teknisk arkitektur.
- `docs/TESTING_GUIDE.md` - testkommandon och vad som kräver lokal runtime.

## Historiskt Och Internt Material

- `docs/internal/` innehåller historiska drift- och forskningsanteckningar.
- Filer där kan vara tekniskt användbara, men de är inte verifierade som
  aktuellt körstatusläge och ska inte användas som publik första presentation.
- Lokala corpusstorlekar, runtimevärden och modellrekommendationer i historiska
  anteckningar ska re-verifieras innan de citeras.

## Kontroll

Kör gärna docs-checken innan publicering:

```bash
python scripts/check_docs_canonical.py
```

Publika docs ska inte innehålla secrets, privata absoluta servervägar eller
påståenden om benchmark/resultat som inte kan verifieras lokalt.
