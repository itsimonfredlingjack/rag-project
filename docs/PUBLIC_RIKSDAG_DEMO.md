# Svensk Ragg Public Riksdagen Demo

This is a public-facing demo README for a small, local Swedish RAG system over
Riksdagens öppna data.

The thesis is simple: a modest local machine can answer bounded questions over a
clearly named public corpus, show the retrieved source IDs, and refuse when the
question asks for legal advice or tries to cross the public corpus boundary.

Data source attribution: Sveriges riksdag / Riksdagens öppna data.

## What This Demo Is

The public demo is the Riksdagen-only profile of the Svensk Ragg project. It uses
BM25 over a public JSONL split derived from Riksdagen open data, then asks a local
model to answer in Swedish with source IDs.

The public profile is intentionally smaller and stricter than the private lab:

| Area | Public Riksdagen demo | Private lab |
| --- | --- | --- |
| Corpus | Riksdagens öppna data only | Non-public local experiments outside this demo |
| Source guard | Allows only `source=riksdagen` and `source_scope=riksdagen_open_data_only` | Private research/runtime experiments |
| Retrieval | BM25-only public path | Broader experimental retrieval stack |
| Demo claim | Bounded public Riksdagen Q&A | Not part of the public demo |

The public demo is not legal advice, not all Swedish law, not a DiVA source
demo, and not the full private corpus.

## Local Profile

The current public runtime profile is designed for a small local GPU setup:

- GPU target used for the demo: RTX 2060 6GB.
- Public default model: `gemma3:4b`.
- Public retrieval mode: `public_bm25_only`.
- Public profile: `public-riksdag-demo`.
- Public corpus scope: `riksdagen_open_data_only`.
- Chroma, reranking, CRAG, and critic-revise are disabled in the public profile.
- The public profile hard-overrides model env aliases to `gemma3:4b`.

## What It Can Answer

It can answer questions that are grounded in the public Riksdagen corpus, such as:

- Riksdagen documents that mention offentlighetsprincipen, yttrandefrihet, budget
  proposals, committees, motions, interpellations, or named public Riksdagen
  documents.
- Short summaries of retrieved Riksdagen material.
- Source-backed explanations where the answer can cite document IDs returned by
  the public BM25 path.

Every factual answer should be checked against the displayed sources.

## What It Refuses

The public profile refuses when the question is outside the safe public demo
contract, including:

- Personalized legal advice, legal strategy, appeal instructions, or drafting
  legal claims.
- Requests to use DiVA, private PDFs, research articles, private full text, or
  any mixed/private source.
- Cases where readiness says the system cannot answer.
- Cases where the retrieved public Riksdagen context is missing or too weak.

Refusals expose `refusal_reason` in the API/UI so the behavior can be inspected.

## Measured Smoke/Eval Result

AIS-155 added a 30-question public demo smoke/eval suite. In this 30-question
public demo eval, the current run produced:

| Metric | Current smoke/eval run |
| --- | ---: |
| questions | 30 |
| retrieval_hit@5 | 0.900 |
| retrieval_hit@10 | 0.900 |
| citation_present_rate | 1.000 |
| unsupported_answer_rate | 0.000 |
| refusal_correctness | 1.000 |
| latency_p50 | 7606.47 ms |
| latency_p95 | 11436.80 ms |
| leakage_count | 0 |
| uncited_public_answer_count | 0 |
| answer_when_not_ready_count | 0 |
| critical_failure_count | 0 |

These numbers describe the current smoke/eval run only. They are not general
product guarantees.

Result artifact:
`backend/evals/results/public_demo_eval_ais155_20260530.json`

## Restore Released Public Corpus

The generated public JSONL and BM25/FTS5 index are published outside Git as a
GitHub Release asset. They are intentionally not committed to the repository.

| Field | Value |
| --- | --- |
| Release tag | `public-riksdag-corpus-20260602` |
| Asset | `public-riksdag-corpus-20260602.tar.zst` |
| Bundle SHA256 | `e2f9154e122b01cd93133888fa0476f274cd8f00b6a3fbce822bb946e8b0bbac` |
| Extracted size | `4120238080` bytes |

Restore the corpus to the runtime default path:

```bash
curl -L \
  -o /tmp/public-riksdag-corpus-20260602.tar.zst \
  https://github.com/itsimonfredlingjack/rag-project/releases/download/public-riksdag-corpus-20260602/public-riksdag-corpus-20260602.tar.zst

echo "e2f9154e122b01cd93133888fa0476f274cd8f00b6a3fbce822bb946e8b0bbac  /tmp/public-riksdag-corpus-20260602.tar.zst" \
  | sha256sum -c -

mkdir -p /home/ai-server2/rag/local-data-public
tar -I zstd -xf /tmp/public-riksdag-corpus-20260602.tar.zst \
  -C /home/ai-server2/rag/local-data-public
```

The archive contains:

- `riksdag/docs.jsonl`
- `riksdag/bm25_fts5/bm25.db`
- `riksdag/manifest.json`
- `riksdag/docs.checkpoint.json`
- `SHA256SUMS`
- `README.md`

## Build The Public JSONL

Run from the repository root. The default input path falls back to the recovered
transfer JSONL when the requested private input path is missing.

```bash
python3 scripts/build_public_riksdag_jsonl.py \
  --output /home/ai-server2/rag/local-data-public/riksdag/docs.jsonl
```

Useful explicit form:

```bash
python3 scripts/build_public_riksdag_jsonl.py \
  --input /path/to/recovered-riksdag-source/docs.jsonl \
  --output /home/ai-server2/rag/local-data-public/riksdag/docs.jsonl \
  --start-row 7842 \
  --end-row 237984
```

The builder writes:

- `docs.jsonl`
- `manifest.json`
- `docs.checkpoint.json`

All rows are validated by the public source guard.

## Build The Public BM25 Index

Run from the repository root after the public JSONL exists:

```bash
python3 scripts/build_bm25_fts5.py \
  --input /home/ai-server2/rag/local-data-public/riksdag/docs.jsonl \
  --output /home/ai-server2/rag/local-data-public/riksdag/bm25_fts5/bm25.db \
  --public-root /home/ai-server2/rag/local-data-public/riksdag
```

The public readiness check expects the BM25 DB path to match the public manifest.

## Run The Public Backend

Set the public profile and start the backend:

```bash
export CONST_PROFILE=public-riksdag-demo
cd backend
../backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8900
```

If you already activated `backend/.venv`, the shorter command is:

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8900
```

## Check Readiness

```bash
curl -s http://127.0.0.1:8900/api/svensk-ragg/ready | python3 -m json.tool
```

For the public profile with Chroma disabled and the public BM25 corpus ready, the
expected demo-ready state is:

```json
{
  "status": "degraded_but_usable",
  "can_answer": true,
  "profile": "public-riksdag-demo",
  "corpus_scope": "riksdagen_open_data_only"
}
```

`degraded_but_usable` is expected here because the public demo deliberately runs
without Chroma. `can_answer=true` also requires the local LLM service to be
reachable and the configured public model to be available.

## Public Route Surface

The public profile exposes only the branded read/query surface by default:

- `GET /`
- `GET /api/svensk-ragg/health`
- `GET /api/svensk-ragg/ready`
- `POST /api/svensk-ragg/agent/query`
- `POST /api/svensk-ragg/agent/query/stream`
- `POST /api/svensk-ragg/agent/query/stream/resume`
- `GET /api/documents/facets` with Riksdagen-only facets

Document writes always return 403 in public profile, even with an API key.
Chroma document listing, document lookup, parent-store lookup, metrics, stats,
and collection listing return 404 in public profile because they are
private/operator surfaces. `/mcp`, legacy `/sse`, `/sse/message`,
`/ws/harvest`, `/docs`, `/redoc`, and `/openapi.json` are not registered by
default in public profile. For local API review only, docs can be enabled with
`CONST_API_DOCS_ENABLED=true`.

## Run The Public Demo Eval

```bash
backend/.venv/bin/python backend/scripts/run_public_demo_eval.py \
  --output backend/evals/results/public_demo_eval_latest.json
```

The runner prints a human-readable summary, writes a JSON artifact with
per-question rows, and exits non-zero if critical invariants fail:

- non-public source leakage
- uncited successful public answers
- successful answers when readiness says `can_answer=false`
- refusal reason mismatches
- runtime errors

## Frontend Behavior To Show

AIS-156 verified the public UI contract:

- Banner: `Svensk Ragg - demo över Riksdagens öppna data.`
- Reminder: `Svar genereras lokalt och ska alltid kontrolleras mot källorna.`
- Answer card metadata: data source attribution, source IDs, latency, and
  `refusal_reason` for refusals.
- Source inspector control: `Visa hämtade källor`.
- Source inspector metadata: `document_id`, `source_scope`, `retriever_source`,
  and source URL.

## Known Limitations

- The public demo covers only the prepared Riksdagen open-data subset.
- It does not cover all Swedish law.
- It does not provide legal advice.
- It does not use DiVA, private PDFs, or the broader private lab corpus.
- BM25 lexical retrieval can miss relevant documents when the wording differs.
- The local model can still phrase things imperfectly; sources remain the ground
  truth for the demo.
- Latency depends on local hardware and current model/runtime load.

## Next Phase

The next phase is to keep the public demo evidence-driven:

- Expand the public eval set with more realistic Riksdagen tasks.
- Add more source-boundary and refusal tests.
- Improve retrieval-hit coverage without changing the public source boundary.
- Record a short demo that shows readiness, a grounded answer, a refusal, and
  the source inspector.
