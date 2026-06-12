# Eval gates (public profile)

## Baseline artifact

`backend/evals/results/model_compare_verified_gemma4_e2b_20260609.json`

## Level 1 — quick gate (5 questions)

```bash
cd backend
.venv/bin/python scripts/run_public_demo_eval.py --limit 5 --output /tmp/rag-eval-l1.json
```

- **BLOCK** on invariant failure
- **WARN** on latency regression (sample too small for hard latency gate)
- Use `--quick-eval` with `compare_eval_summary.py`

## Level 2 — merge gate (30 questions)

```bash
cd backend
.venv/bin/python scripts/run_public_demo_eval.py --output /tmp/rag-eval-l2.json
```

Required before merging: model change, `ollama_num_ctx`, `mode_evidence_num_predict`, warmup alignment.

## Invariants (must pass)

| Metric | Expected |
| --- | --- |
| `citation_present_rate` | 1.0 |
| `unsupported_answer_rate` | 0.0 |
| `refusal_correctness` | 1.0 (full eval only; null OK in L1 if no refusal rows) |
| `critical_invariants_passed` | true |
| `leakage_count` | 0 |

## Latency reference (30Q baseline)

- p50: ~2566 ms
- p95: ~11757 ms

## Compare command

```bash
python3 .cursor/skills/_shared/scripts/compare_eval_summary.py \
  --baseline backend/evals/results/model_compare_verified_gemma4_e2b_20260609.json \
  --candidate /tmp/rag-eval-l2.json
```

Public eval entrypoint: `backend/scripts/run_public_demo_eval.py` — not root `eval/run_eval.py` (private HTTP path).