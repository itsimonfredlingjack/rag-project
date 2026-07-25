# Metrics schema

## Ollama benchmark (`scripts/benchmark_ollama_models.py` CSV)

| Field | Meaning |
| --- | --- |
| `model` | Ollama model tag |
| `prompt` | `short_sv` or `rag_sv` |
| `wall_s` | Total wall time |
| `load_s` | Model load time |
| `gen_tok_s` | Generation tokens/sec |
| `processor` | CPU/GPU split from `ollama ps` |
| `context` | `num_ctx` used |

## Public eval summary (`run_public_demo_eval.py`)

| Field | Meaning |
| --- | --- |
| `latency_p50` / `latency_p95` | Pipeline ms |
| `tokens_generated` | Total output tokens |
| `citation_present_rate` | Answers with citations |
| `retrieval_hit@5` / `@10` | Golden doc in top-k |
| `critical_invariants_passed` | Safety gate |

## Per-row eval fields (token / retrieval profiling)

| Field | Meaning |
| --- | --- |
| `tokens_generated` | Output tokens per question |
| `citation_count` | Citations in answer |
| `source_count` | Sources attached |
| `latency_ms` | End-to-end ms |
| `retrieved_document_ids_top10` | BM25 hits |
| `retrieval_hit_5` / `retrieval_hit_10` | Per-question hit |

## Readiness (`/api/svensk-ragg/ready`)

| Path | Meaning |
| --- | --- |
| `checks.llm_service.details.model` | Active LLM |
| `checks.bm25.details.documents_count` | Index size |
| `can_answer` | Safe to answer public queries |
