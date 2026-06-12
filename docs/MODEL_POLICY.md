# Model Policy

This project uses local LLMs for a Swedish public-document RAG portfolio demo.
Model selection is a runtime and governance decision, not an incidental config
detail.

## Current Local Demo Default

- Runtime: Ollama on `http://localhost:11434`
- Primary model: `gemma4:e2b`
- Fallback model: `gemma4:e2b`
- First-run context: `4096` tokens (private lab default)
- Public profile context: `2048` tokens (`CONST_OLLAMA_NUM_CTX` override)

On the local RTX 2060 6 GB test machine, Ollama loaded `gemma4:e2b` at 4K
context with a `74%/26% CPU/GPU` split and about 30-35 generated tokens/s
after cold load. Treat larger Gemma 4 variants, such as `gemma4:26b`, as
future benchmark candidates only after VRAM, RAM, and latency are verified on
the target machine.

## VRAM Budget (RTX 2060 6 GB)

Embeddings (`jinaai/jina-embeddings-v3`) default to CPU via
`CONST_EMBEDDING_DEVICE=cpu`, so the full GPU budget is available to Ollama.
The public profile uses `CONST_OLLAMA_NUM_CTX=2048` to reduce KV-cache pressure on 6 GB VRAM.

Runtime VRAM = quantized weights + KV cache + CUDA overhead. Ollama file size
is not the same as peak VRAM.

| Model | Ollama size | Fits 6 GB VRAM | Notes |
| --- | --- | --- | --- |
| `gemma4:e2b` | 7.2 GB | Yes (CPU/GPU mix) | Approved default; best in 30-question eval |
| `gemma3:4b` | 3.3 GB | Yes (100% GPU) | Works but slower and more verbose in eval |
| `mistral:7b` | 4.4 GB | Likely yes | Not benchmarked in this repo |
| `llama3.1:8b` | 4.9 GB | Tight | Not benchmarked in this repo |
| `gemma4:e4b` | 9.6 GB | Heavy CPU offload | Benchmark before adopting |
| `gemma4:12b` | 7.6 GB | No | Weights alone exceed 6 GB VRAM |
| `gemma3:12b` | 8.1 GB | No | Weights alone exceed 6 GB VRAM |
| `gemma4:26b` / `gemma4:31b` | 18-20 GB | No | Workstation-only |
| `gemma3:27b` | 17 GB | No | Workstation-only |
| `llama3.1:70b` / `405b` | 43-243 GB | No | Cloud/workstation-only |

Do not adopt new generation models without running the same 30-question public
eval used on 2026-06-09.

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
