#!/usr/bin/env bash
# run_agent_loop.sh — Autoresearch main orchestration loop.
#
# Usage:
#   cd autoresearch/
#   ANTHROPIC_API_KEY=sk-... bash run_agent_loop.sh [MAX_ITERATIONS]
#
# Requires: python3, torch, anthropic SDK, datasets
# Run prepare.py first to create train.bin / val.bin / meta.pkl.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_ITERATIONS=${1:-50}
IMPROVEMENT_THRESHOLD=0.995   # new_bpb must be < best_bpb * this value (0.5% improvement)
TRAIN_TIMEOUT=360              # seconds — 1 min over the 300s training budget
RESULTS_FILE="results.tsv"
LOG_FILE="run.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Initialise results.tsv
# ---------------------------------------------------------------------------

if [[ ! -f "$RESULTS_FILE" ]]; then
    echo -e "iteration\ttimestamp\tbpb\tdelta\tkept\tcommit\tnotes" > "$RESULTS_FILE"
fi

# ---------------------------------------------------------------------------
# Determine initial best BPB from results.tsv (last kept experiment)
# ---------------------------------------------------------------------------

BEST_BPB=$(awk -F'\t' 'NR>1 && $5=="yes" {bpb=$3} END {print (bpb=="" ? "999999" : bpb)}' "$RESULTS_FILE")
echo "Starting loop | best BPB so far: $BEST_BPB | max iterations: $MAX_ITERATIONS"

# ---------------------------------------------------------------------------
# Cleanup on SIGINT / SIGTERM
# ---------------------------------------------------------------------------

CURRENT_BRANCH=""

cleanup() {
    echo ""
    echo "[autoresearch] Interrupted. Cleaning up ..."
    if [[ -n "$CURRENT_BRANCH" ]]; then
        BASE_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "")
        if [[ "$BASE_BRANCH" == "$CURRENT_BRANCH" ]]; then
            git checkout - 2>/dev/null || true
        fi
        git branch -D "$CURRENT_BRANCH" 2>/dev/null || true
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM

# ---------------------------------------------------------------------------
# Helper: parse FINAL_VAL_BPB from log
# ---------------------------------------------------------------------------

parse_bpb() {
    grep -oP 'FINAL_VAL_BPB=\K[\d.]+' "$LOG_FILE" | tail -1
}

# ---------------------------------------------------------------------------
# Helper: python bc-style float comparison
# ---------------------------------------------------------------------------

float_lt() {
    python3 -c "import sys; sys.exit(0 if float('$1') < float('$2') else 1)"
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

for ((ITER=1; ITER<=MAX_ITERATIONS; ITER++)); do
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    EXP_BRANCH="exp/${TIMESTAMP//:/}-${ITER}"
    CURRENT_BRANCH="$EXP_BRANCH"

    echo ""
    echo "=========================================="
    echo " Iteration $ITER / $MAX_ITERATIONS"
    echo " Branch: $EXP_BRANCH"
    echo " Best BPB: $BEST_BPB"
    echo " Time: $TIMESTAMP"
    echo "=========================================="

    # ------------------------------------------------------------------
    # Step 1: Create experiment branch
    # ------------------------------------------------------------------
    git checkout -b "$EXP_BRANCH"

    # ------------------------------------------------------------------
    # Step 2: Ask agent to propose a new train.py
    # ------------------------------------------------------------------
    echo "[step 2] Calling agent to propose changes ..."
    if ! python3 agent_propose.py \
            --program program.md \
            --code train.py \
            --log "$RESULTS_FILE" \
            > train.py.new 2>agent.log; then
        echo "[step 2] Agent call FAILED. See agent.log"
        git checkout - && git branch -D "$EXP_BRANCH"
        CURRENT_BRANCH=""
        echo -e "${ITER}\t${TIMESTAMP}\t\t\tno\t\tagent-call-failed" >> "$RESULTS_FILE"
        continue
    fi

    # Validate the proposed file has the required final line
    if ! grep -q "FINAL_VAL_BPB" train.py.new; then
        echo "[step 2] Proposed train.py missing FINAL_VAL_BPB output — rejecting."
        git checkout - && git branch -D "$EXP_BRANCH"
        CURRENT_BRANCH=""
        echo -e "${ITER}\t${TIMESTAMP}\t\t\tno\t\tmissing-final-bpb-line" >> "$RESULTS_FILE"
        continue
    fi

    mv train.py.new train.py

    # ------------------------------------------------------------------
    # Step 3: Commit the proposed change
    # ------------------------------------------------------------------
    git add train.py
    COMMIT_HASH=$(git commit -m "exp(${ITER}): agent proposal" --quiet && git rev-parse --short HEAD)
    echo "[step 3] Committed as $COMMIT_HASH"

    # ------------------------------------------------------------------
    # Step 4: Run training with a timeout
    # ------------------------------------------------------------------
    echo "[step 4] Running train.py (timeout ${TRAIN_TIMEOUT}s) ..."
    EXIT_CODE=0
    timeout "$TRAIN_TIMEOUT" python3 train.py > "$LOG_FILE" 2>&1 || EXIT_CODE=$?

    # ------------------------------------------------------------------
    # Step 5: Handle crash / timeout
    # ------------------------------------------------------------------
    if [[ $EXIT_CODE -ne 0 ]]; then
        echo "[step 5] Training FAILED (exit $EXIT_CODE). Attempting self-repair ..."

        # One self-repair attempt
        if python3 agent_propose.py \
                --program program.md \
                --code train.py \
                --log "$RESULTS_FILE" \
                --error-log "$LOG_FILE" \
                > train.py.fix 2>agent_fix.log; then

            if grep -q "FINAL_VAL_BPB" train.py.fix; then
                mv train.py.fix train.py
                git add train.py
                git commit -m "exp(${ITER}): self-repair attempt" --quiet
                EXIT_CODE=0
                timeout "$TRAIN_TIMEOUT" python3 train.py > "$LOG_FILE" 2>&1 || EXIT_CODE=$?
            else
                rm -f train.py.fix
            fi
        fi

        if [[ $EXIT_CODE -ne 0 ]]; then
            echo "[step 5] Self-repair failed. Reverting."
            git checkout - && git branch -D "$EXP_BRANCH"
            CURRENT_BRANCH=""
            echo -e "${ITER}\t${TIMESTAMP}\t\t\tno\t${COMMIT_HASH}\tcrash-exit-${EXIT_CODE}" >> "$RESULTS_FILE"
            continue
        fi
    fi

    # ------------------------------------------------------------------
    # Step 6: Parse BPB from log
    # ------------------------------------------------------------------
    BPB=$(parse_bpb)
    if [[ -z "$BPB" ]]; then
        echo "[step 6] Could not parse FINAL_VAL_BPB from log. Reverting."
        git checkout - && git branch -D "$EXP_BRANCH"
        CURRENT_BRANCH=""
        echo -e "${ITER}\t${TIMESTAMP}\t\t\tno\t${COMMIT_HASH}\tno-bpb-in-log" >> "$RESULTS_FILE"
        continue
    fi

    echo "[step 6] BPB = $BPB  (best = $BEST_BPB)"

    # ------------------------------------------------------------------
    # Step 7: Accept or revert
    # ------------------------------------------------------------------
    THRESHOLD_BPB=$(python3 -c "print(float('$BEST_BPB') * $IMPROVEMENT_THRESHOLD)")

    if float_lt "$BPB" "$THRESHOLD_BPB"; then
        DELTA=$(python3 -c "print(f'{float(\"$BPB\") - float(\"$BEST_BPB\"):.6f}')")
        echo "[step 7] IMPROVED! $BEST_BPB -> $BPB (delta $DELTA). Merging."

        # Merge back to main branch
        git checkout -
        git merge --squash "$EXP_BRANCH" --no-commit
        git commit -m "keep(${ITER}): BPB ${BPB} was ${BEST_BPB}" --quiet

        BEST_BPB="$BPB"

        # Update program.md with new best BPB
        python3 - <<PYEOF
import re, pathlib
p = pathlib.Path("program.md")
text = p.read_text()
text = re.sub(r"(## Current Best BPB\n\n).*", rf"\1\`{BEST_BPB}\`", text)
p.write_text(text)
PYEOF
        git add program.md
        git commit -m "update best BPB to ${BEST_BPB}" --quiet

        git branch -D "$EXP_BRANCH"
        KEPT="yes"
        DELTA_LOG="$DELTA"
    else
        echo "[step 7] No improvement ($BPB >= threshold $THRESHOLD_BPB). Reverting."
        DELTA=$(python3 -c "print(f'{float(\"$BPB\") - float(\"$BEST_BPB\"):.6f}')")
        git checkout - && git branch -D "$EXP_BRANCH"
        KEPT="no"
        DELTA_LOG="$DELTA"
    fi

    CURRENT_BRANCH=""

    # ------------------------------------------------------------------
    # Step 8: Log to results.tsv
    # ------------------------------------------------------------------
    echo -e "${ITER}\t${TIMESTAMP}\t${BPB}\t${DELTA_LOG}\t${KEPT}\t${COMMIT_HASH}\t" >> "$RESULTS_FILE"
    echo "[step 8] Logged to $RESULTS_FILE"

done

echo ""
echo "=========================================="
echo " Autoresearch loop complete."
echo " Iterations: $MAX_ITERATIONS"
echo " Best BPB achieved: $BEST_BPB"
echo "=========================================="
