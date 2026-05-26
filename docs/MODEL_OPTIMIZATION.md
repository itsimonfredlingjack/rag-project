# Modelloptimering - Constitutional AI

> Dokumentation av modellparametrar, system prompts och best practices för prompt engineering

**Senast uppdaterad:** 2026-03-12

---

## Översikt

Projektet använder lokala modeller för att svara på frågor baserat på källor från en lokal dokumentkorpus. Korpusstorlek och modellruntime är miljöberoende och ingår inte i repot.

### Modeller

- **Primär modell:** Gemma 3 12B (Q4_K_M, ~8GB) via Ollama (port 11434)
- **Fallback modell:** Samma som primär (ingen separat fallback-modell)
- **Grader-modell:** Gemma 3 12B (GBNF-styrd 3-vägs JSON-gradering: RELEVANT/AMBIGUOUS/IRRELEVANT)
- **Draft-modell:** Ingen separat draft-modell
- **Embedding modell:** jinaai/jina-embeddings-v3 (1024 dim, asymmetric LoRA, CC-BY-NC-4.0)
- **Reranker:** jinaai/jina-reranker-v2-base-multilingual (XLM-RoBERTa, 278M params, CC-BY-NC-4.0)
- **Vector DB:** ChromaDB
- **CRAG:** Enabled (grading active, self-reflection disabled)
- **Collections:** All suffixed with `_jina_v3_1024`
- **Context window:** 16384 tokens (Gemma 3 supports 128K natively, capped for VRAM)
- **Timeout:** 60 sekunder (Ollama timeout)

---

## Migration 2026 - Optimeringar

| Optimering | Flagga/Setting | Effekt |
|---|---|---|
| N-gram speculation | `--spec-type ngram-simple --draft-max 64` | ~57-70% acceptance i kompatibla llama-server builds, låg extra kostnad |
| KV cache quant | `-ctk q8_0 -ctv q8_0` | Sparar ~1-2 GB VRAM jämfört med högre precision |
| Flash Attention | `-fa` / `--flash-attn on` | Snabbare attention och lägre minnestryck på GPU |
| GBNF grading | `grammar` parameter i graderingsanrop | Deterministisk JSON (`{"relevance":"yes/no"}`), färre parse-fel |
| Asymmetrisk embedding | `retrieval.query` vs `retrieval.passage` | Bättre retrieval-precision än symmetrisk embedding |
| Hybrid search | Dense + BM25 + RRF | Fångar både semantisk och lexikal matchning |
| Query expansion | 3 LLM-reformuleringar i BM25-väg | Bredare lexikal recall för juridiska formuleringar |
| Cross-encoder reranking | Jina Reranker v2 (CPU) | Typiskt bättre top-k ordning (nDCG@10 förbättras) |

---

## Modellparametrar

### Per Response Mode

#### EVIDENCE Mode (Juridisk expert, formell)
```python
{
    "temperature": 0.15,     # Mycket låg - fokuserat och exakt
    "top_p": 0.9,            # Fokuserad sampling
    "repeat_penalty": 1.1,   # Undviker repetitioner
    "num_predict": 1024      # Längre svar för detaljerade citationer
}
```

**Användning:** När användaren ber om specifika lagreferenser eller formella svar med citationer.

#### ASSIST Mode (Hjälpsam assistent, balanserad)
```python
{
    "temperature": 0.4,      # Låg-mellan - balanserat
    "top_p": 0.9,            # Fokuserad sampling
    "repeat_penalty": 1.1,   # Undviker repetitioner
    "num_predict": 1024      # Längre svar för detaljerade förklaringar
}
```

**Användning:** Standardläge för de flesta juridiska frågor. Balanserar exakthet med läsbarhet.

#### CHAT Mode (Smalltalk, avslappnad)
```python
{
    "temperature": 0.7,      # Högre - mer kreativt och varierat
    "top_p": 0.9,            # Fokuserad sampling
    "repeat_penalty": 1.1,   # Undviker repetitioner
    "num_predict": 512       # Kortare svar för smalltalk
}
```

**Användning:** För hälsningar, meta-frågor och smalltalk som inte kräver RAG.

---

## System Prompts

### ASSIST Mode Prompt

```
Du är Constitutional AI, en expert på svensk lag och myndighetsförvaltning.

KUNSKAPSBAS:
Du har tillgång till en lokal dokumentkorpus från ChromaDB, inklusive källor som kan omfatta:
- SFS-lagtext (Svensk författningssamling)
- Propositioner från Riksdagen
- SOU-rapporter (Statens offentliga utredningar)
- Motioner, betänkanden och andra riksdagsdokument

ARBETSSÄTT:
1. Använd ALLTID källorna som tillhandahålls i kontexten när de finns
2. Citera källor i formatet [Källa X] när du refererar till dem
3. Prioritera SFS-källor (lagtext) över prop/sou när båda finns
4. Om källor saknas eller är lågkvalitativa, säg tydligt att du saknar specifik information
5. Var kortfattat men exakt - MAX 150 ord
6. INGEN MARKDOWN - skriv ren text utan *, **, #, - eller formatering
7. Inga rubriker, inga punktlistor, inga asterisker
8. Gå rakt på sak och var hjälpsam
```

**Fil:** `backend/app/services/orchestrator_service.py`

### EVIDENCE Mode Prompt

```
Du är en juridisk expert specialiserad på svensk lag och förvaltningsrätt.

KUNSKAPSBAS:
Du har tillgång till en lokal dokumentkorpus från ChromaDB, inklusive källor som kan omfatta:
- SFS-lagtext (Svensk författningssamling) - PRIORITERA DETTA
- Propositioner från Riksdagen
- SOU-rapporter (Statens offentliga utredningar)
- Motioner, betänkanden och andra riksdagsdokument
- DiVA forskningspublikationer

ARBETSSÄTT FÖR EVIDENCE-MODE:
1. Använd ENDAST källor från korpusen - hitta på ingenting
2. Citera ALLTID exakta SFS-nummer och paragrafer när de finns i källorna
3. PRIORITERA SFS-källor (lagtext) över prop/sou/bet när flera källor finns
4. Om källor saknas eller är lågkvalitativa, säg tydligt: "Jag saknar specifik information i korpusen"
5. Var formell, exakt och saklig - MAX 200 ord
6. INGEN MARKDOWN - skriv ren text utan *, **, #, - eller formatering
7. Citera källor med [Källa X] och inkludera SFS-nummer/paragraf när tillgängligt
```

**Fil:** `backend/app/services/orchestrator_service.py`

### CHAT Mode Prompt

```
Avslappnad AI-assistent. Svara kort på svenska.
MAX 2-3 meningar. INGEN MARKDOWN - skriv ren text utan *, **, #, -, eller listor.

Om frågan handlar om svensk lag eller myndighetsförvaltning, kan du hänvisa till att du kan använda lokala källor när de finns tillgängliga, men svara kortfattat.
```

**Fil:** `backend/app/services/orchestrator_service.py`

---

## User Prompt Struktur

### ASSIST/EVIDENCE Mode User Prompt

```
Fråga: {question}

Källor från korpusen:
{Källa 1: titel} ⭐ PRIORITET (SFS) | Relevans: 0.85
{full_text}

{Källa 2: titel} Typ: PROP | Relevans: 0.72
{full_text}

...

Instruktioner:
- Använd källorna ovan för att svara på frågan
- Citera källor med [Källa X] när du refererar till dem
- Om källor saknas, säg tydligt att du saknar specifik information
- Prioritera SFS-källor (lagtext) om flera källor finns

Svara i ren text utan formatering.
```

**Viktiga detaljer:**
- Källor formateras med doc_type och score
- SFS-källor markeras med ⭐ PRIORITET
- Instruktioner om källanvändning ingår explicit

---

## Best Practices för Prompt Engineering

### 1. Referera till korpusen

**BRA:**
- "Du har tillgång till en lokal dokumentkorpus när källor finns tillgängliga"
- "Använd källorna från korpusen när de finns"

**DÅLIGT:**
- "Svara på frågan" (ingen referens till korpusen)
- Generiska prompts utan kontext

### 2. Instruera om källanvändning

**BRA:**
- "Använd ALLTID källorna som tillhandahålls i kontexten när de finns"
- "Citera källor i formatet [Källa X] när du refererar till dem"

**DÅLIGT:**
- Ingen instruktion om hur källor ska användas
- Antagande att modellen automatiskt använder källor

### 3. Hantera saknade källor

**BRA:**
- "Om källor saknas eller är lågkvalitativa, säg tydligt att du saknar specifik information"
- "Jag saknar specifik information i korpusen"

**DÅLIGT:**
- Ingen instruktion om vad man ska göra när källor saknas
- Modellen hittar på svar när källor saknas

### 4. Prioritera källor

**BRA:**
- "Prioritera SFS-källor (lagtext) över prop/sou när båda finns"
- "PRIORITERA SFS-källor (lagtext) över prop/sou/bet"

**DÅLIGT:**
- Ingen instruktion om källprioritering
- Alla källor behandlas lika

### 5. Var tydlig om format

**BRA:**
- "INGEN MARKDOWN - skriv ren text utan *, **, #, - eller formatering"
- "Citera källor med [Källa X]"

**DÅLIGT:**
- Otydliga instruktioner om format
- Antagande att modellen vet formatet

---

## Testning av Modelloptimeringar

### Testfrågor per Mode

#### ASSIST Mode
```bash
curl -X POST http://localhost:8900/api/constitutional/agent/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Vad säger GDPR om personuppgifter?",
    "mode": "assist"
  }' | jq .
```

**Förväntat:**
- Svar baserat på källor från korpusen
- Citationer med [Källa X]
- Prioritering av SFS-källor om de finns
- Max 150 ord

#### EVIDENCE Mode
```bash
curl -X POST http://localhost:8900/api/constitutional/agent/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Vad säger förvaltningslagen 2017:900 om beslut?",
    "mode": "evidence"
  }' | jq .
```

**Förväntat:**
- Exakta SFS-nummer och paragrafer
- Formellt språk
- Prioritering av SFS-källor
- Max 200 ord

#### CHAT Mode
```bash
curl -X POST http://localhost:8900/api/constitutional/agent/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Hej, vad kan du hjälpa mig med?",
    "mode": "chat"
  }' | jq .
```

**Förväntat:**
- Kortfattat svar (2-3 meningar)
- Avslappnad ton
- Eventuell hänvisning till korpusen om relevant

### Verifiering

**Kontrollera att:**
1. Modellen använder källor när de finns
2. Citationer ingår i formatet [Källa X]
3. SFS-källor prioriteras när flera källor finns
4. Modellen säger tydligt när källor saknas
5. Formatet är ren text utan markdown

---

## Ändringshistorik

### 2026-03-12 - Gemma 3 12B migration + quality/performance tuning

**Model migration:** Qwen 3.5 9B → Gemma 3 12B (Q4_K_M, ~8GB via Ollama)

| Change | Before | After | Rationale |
|--------|--------|-------|-----------|
| Primary model | Qwen 3.5 9B | Gemma 3 12B | Better Swedish, larger context |
| Grader model | Qwen 3.5 9B | Gemma 3 12B | Single-model setup |
| Runtime | llama-server | Ollama | Simpler deployment |
| Context window | 8192 | 16384 | Gemma 3 128K native |
| Source budget cap | 3000 tokens | 5000 tokens | More source context |
| default_search_limit | 15 | 20 | More retrieval candidates |
| reranking_top_n | 8 | 10 | More docs in final context |
| rrf_bm25_weight | 1.2 | 1.5 | Favor exact legal term matches |
| critic_max_revisions | 2 | 1 | Reduce latency |
| anti-truncation retries | 3 | 1 | Gemma 3 produces longer outputs |

**EVIDENCE mode fixes:**
- CRAG soft pass: when grader finds 0 relevant + 0 ambiguous docs, pass top 3 reranked docs through instead of hard-refusing
- Grading prompt: bias toward AMBIGUOUS over IRRELEVANT when uncertain; accept background info
- Quality gate threshold: 0.15 → 0.05 (removed double-filter before CRAG)

**Quality tuning:**
- Strengthened verbatim citation rules in EVIDENCE prompt
- Added completeness instruction: "Inkludera ALL relevant information"
- Added negative example for paraphrase detection

**Performance tuning:**
- Grading num_predict: 32 → 24 (GBNF constrains to ~15-20 tokens)
- Retry backoff: 1-3s → 0.3-0.5s
- Critic max revisions: 2 → 1

**Baseline eval (Qwen era, 2026-03-11):**

| Metric | Value |
|--------|-------|
| Composite | 0.37 |
| Faithfulness | 0.29 |
| EVIDENCE composite | 0.22 |
| EVIDENCE refusals | 16/30 |
| Avg latency | 39s/query |

### 2025-12-15 - Första optimering
- Förbättrade system prompts med referenser till korpusen
- Lade till top_p och repeat_penalty parametrar
- Ökade num_predict för ASSIST/EVIDENCE modes
- Förbättrade källformatering med doc_type och score
- Justerade temperature per mode (EVIDENCE: 0.15, ASSIST: 0.4, CHAT: 0.7)

---

## Referenser

- Ollama: https://ollama.ai/
- Gemma 3: https://ai.google.dev/gemma
- ChromaDB: https://www.trychroma.com/
