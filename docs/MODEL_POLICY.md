# Model Policy

This project uses local LLMs for a Swedish public-document RAG portfolio demo.
Model selection is a runtime and governance decision, not an incidental config
detail.

## Current Local Demo Default

- Runtime: Ollama on `http://localhost:11434`
- Primary model: `gemma4:e2b`
- Fallback model: `gemma4:e2b`
- First-run context: `4096` tokens

On the local RTX 2060 6 GB test machine, Ollama loaded `gemma4:e2b` at 4K
context with a `74%/26% CPU/GPU` split and about 30-35 generated tokens/s
after cold load. Treat larger Gemma 4 variants, such as `gemma4:26b`, as
future benchmark candidates only after VRAM, RAM, and latency are verified on
the target machine.

## Repository Rule

Runtime model identifiers are validated by `backend/app/services/config_service.py`.
Model families listed in `EXCLUDED_MODEL_FAMILIES` are not valid choices for
generation, fallback, grading, or GGUF runtime configuration.

Use neutral wording in public docs:

- Prefer: "excluded model family" or "not approved by repository model policy".
- Avoid political or nationality-based wording.

## Change Process

1. Update `backend/app/services/config_service.py` defaults and policy tests.
2. Update `backend/.env`, startup scripts, and docs together.
3. Run `python3 scripts/check_docs_canonical.py`.
4. Run backend tests that cover config, docs, LLM service contracts, and
   response contracts.
5. Run live `/api/svensk-ragg/ready` after the local model and indexes are
   available.
