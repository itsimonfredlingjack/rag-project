# Retrieval noise taxonomy (public BM25)

| Class | Meaning | Likely fix |
| --- | --- | --- |
| `hit` | Expected doc in top-5 or top-10 | None |
| `no_results` | Empty BM25 top-10 | Index missing, query norm, or corpus gap |
| `wrong_doc_right_terms_possible` | Hits exist but not golden IDs | Ranking, chunk boundaries, duplicate chunks |
| `partial_overlap` | Some overlap but miss@5 | Increase k or fix chunk granularity |
| `unknown_miss` | Unclassified | Manual row review |

## Fix priority

1. Corpus/manifest integrity (`rag-public-corpus-integrity-checker` — Fas 2)
2. `build_bm25_fts5.py` rebuild (explicit order only)
3. Query normalization in public BM25 path
4. Never default to LLM prompt changes for retrieval miss