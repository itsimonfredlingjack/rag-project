---
name: rag-eval-regression-bouncer
description: Run public Riksdagen demo eval gates (Level 1 quick 5Q, Level 2 full 30Q) and block merges when citation, refusal, or critical invariants fail. Use after RAG config, model, num_ctx, num_predict, BM25, warmup, or retrieval changes; when the user asks if a change may merge or pass regression.
---

# RAG Eval Regression Bouncer

Commit gate for `public-riksdag-demo`. Public eval only: `backend/scripts/run_public_demo_eval.py`.

## Level 1 — quick (required after any tuning)

```bash
cd backend
.venv/bin/python scripts/run_public_demo_eval.py --limit 5 --output /tmp/rag-eval-l1.json

python3 ../.cursor/skills/_shared/scripts/compare_eval_summary.py \
  --baseline evals/results/model_compare_verified_gemma4_e2b_20260609.json \
  --candidate /tmp/rag-eval-l1.json \
  --quick-eval
```

- **FAIL** on invariant breach → stop, no commit
- Latency on L1 is indicative only

## Level 2 — merge (required for ctx/model/budget changes)

```bash
cd backend
.venv/bin/python scripts/run_public_demo_eval.py --output /tmp/rag-eval-l2.json

python3 ../.cursor/skills/_shared/scripts/compare_eval_summary.py \
  --baseline evals/results/model_compare_verified_gemma4_e2b_20260609.json \
  --candidate /tmp/rag-eval-l2.json
```

- **FAIL** if invariants break or p50 regression > 50% vs baseline
- **WARN** if p50 regression > 25%

## Invariants

See `_shared/references/eval_gates.md`.

## Output format

```text
Gate: Level 1 | Level 2
Verdict: PASS | WARN | FAIL
Invariants: ...
Latency p50 delta: ...
Merge allowed: yes | no
```

## Do not use

- Root `eval/run_eval.py` for public profile gate (private HTTP path)
- Skip L2 before merging model or `ollama_num_ctx` changes