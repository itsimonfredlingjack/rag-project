#!/usr/bin/env bash
# Run public demo eval gate Level 1 or Level 2 with baseline comparison.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
LEVEL="${1:-1}"
BASELINE="${BASELINE:-$REPO/backend/evals/results/model_compare_verified_gemma4_e2b_20260609.json}"
PYTHON="${REPO}/backend/.venv/bin/python"
COMPARE="${REPO}/.cursor/skills/_shared/scripts/compare_eval_summary.py"
EVAL="${REPO}/backend/scripts/run_public_demo_eval.py"

if [[ "$LEVEL" == "1" ]]; then
  OUT="/tmp/rag-eval-l1.json"
  echo "=== Level 1: quick eval (5 questions) ==="
  (cd "$REPO/backend" && "$PYTHON" scripts/run_public_demo_eval.py --limit 5 --output "$OUT" --no-fail-on-critical)
  "$PYTHON" "$COMPARE" --baseline "$BASELINE" --candidate "$OUT" --quick-eval
elif [[ "$LEVEL" == "2" ]]; then
  OUT="/tmp/rag-eval-l2.json"
  echo "=== Level 2: full eval (30 questions) ==="
  (cd "$REPO/backend" && "$PYTHON" scripts/run_public_demo_eval.py --output "$OUT" --no-fail-on-critical)
  "$PYTHON" "$COMPARE" --baseline "$BASELINE" --candidate "$OUT"
else
  echo "Usage: $0 [1|2]"
  exit 2
fi
