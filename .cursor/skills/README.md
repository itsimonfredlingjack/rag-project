# RAG Optimization Skill Pack (Fas 1)

Project-local Agent Skills for **public-riksdag-demo** — smala, mätbara workflows.

Runtime truth: `config_service.py` → `/api/svensk-ragg/ready` → logs/tests (see `_shared/references/runtime_truth.md`).

## Skills (build order)

| Skill | Purpose |
| --- | --- |
| [`rag-profile-drift-guardian`](rag-profile-drift-guardian/SKILL.md) | Config/startup/docs/ready drift |
| [`rag-vram-context-tuner`](rag-vram-context-tuner/SKILL.md) | num_ctx sweep + recommendation |
| [`rag-eval-regression-bouncer`](rag-eval-regression-bouncer/SKILL.md) | L1/L2 eval gates |
| [`rag-coldstart-warmup-sentinel`](rag-coldstart-warmup-sentinel/SKILL.md) | Warmup vs config, cold/warm |
| [`rag-token-budget-profiler`](rag-token-budget-profiler/SKILL.md) | Token/latency breakdown |
| [`rag-retrieval-noise-miner`](rag-retrieval-noise-miner/SKILL.md) | BM25 miss taxonomy |

Shared: [`_shared/`](_shared/) — `compare_eval_summary.py`, eval gates, metrics schema.

## Legacy

Global [`~/.cursor/skills/rag-public-optimizer/`](../../../.cursor/skills/rag-public-optimizer/) is superseded by this pack. Use drift-guardian + bouncer + vram-tuner instead of `diagnose_public.sh`.

## Typical optimization flow

```text
1. rag-profile-drift-guardian
2. rag-vram-context-tuner (or token-profiler)
3. propose patch + rollback (no auto-commit)
4. rag-eval-regression-bouncer Level 1
5. rag-eval-regression-bouncer Level 2 before merge
6. rag-profile-drift-guardian again
```

## Trigger examples (should invoke)

| Skill | Example prompt |
| --- | --- |
| drift-guardian | "kolla config drift innan commit" |
| vram-tuner | "jämför 2048 och 4096 num_ctx" |
| bouncer | "får den här ändringen mergas?" |
| warmup-sentinel | "första frågan är långsam efter start" |
| token-profiler | "för många tokens i svaren" |
| noise-miner | "retrieval hit är låg på BM25" |

## Non-triggers (should NOT invoke pack)

- "förklara vad context window betyder" (generic explanation)
- Private lab Chroma/CRAG tuning (out of scope)
- Full orchestrator refactor

## Fas 2 backlog

- rag-citation-faithfulness-auditor
- rag-query-path-profiler
- rag-public-corpus-integrity-checker
- rag-model-policy-enforcer
- rag-answer-mode-slimmer
- rag-optimization-decision-log
- rag-skill-trigger-optimizer

## Quick commands

```bash
python3 .cursor/skills/rag-profile-drift-guardian/scripts/check_public_profile_drift.py
python3 .cursor/skills/rag-vram-context-tuner/scripts/run_context_sweep.py --dry-run
bash .cursor/skills/rag-eval-regression-bouncer/scripts/run_eval_gate.sh 1
bash .cursor/skills/rag-coldstart-warmup-sentinel/scripts/check_warmup_alignment.sh
```