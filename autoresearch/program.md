# Research Agenda

## Goal

Minimize the **validation bits-per-byte (BPB)** on the TinyShakespeare character-level language modeling task.

Lower BPB = better compression = better language model.

## Current Best BPB

`BASELINE` (run `prepare.py` then `train.py` once to establish the baseline)

## Rules (must not be broken)

1. You may only modify `train.py`. Do NOT touch `prepare.py`, `program.md`, `results.tsv`, or any other file.
2. Training must complete within **300 seconds** of wall-clock time. Do not change `cfg.train_seconds`.
3. The final stdout line must remain `FINAL_VAL_BPB=<float>` — the evaluation harness parses this.
4. Data sources must stay as `train.bin` / `val.bin` (created by `prepare.py`).
5. Propose **one focused change per iteration**. Do not rewrite everything at once.

## Improvement Threshold

A change is accepted only if the new BPB is **≥ 0.5% lower** than the current best.

## Suggested Exploration Directions

The following are ideas — the agent is free to explore any direction:

### Architecture
- Increase model depth (`n_layer`) or width (`n_embd`)
- Experiment with `n_head` (more or fewer heads)
- Add weight tying between token embedding and output head
- Try larger or smaller `block_size`
- Replace absolute positional embeddings with learned relative or RoPE embeddings

### Regularization
- Increase `dropout` (e.g., 0.1 or 0.2) to reduce overfitting
- Experiment with `weight_decay` in AdamW

### Optimizer
- Tune `learning_rate` (try 3e-4, 5e-4, 2e-3)
- Add a cosine learning rate schedule
- Try SGD with momentum instead of AdamW

### Data
- Increase `batch_size` (memory permitting)
- Increase `block_size` for longer context

### Efficiency
- Use mixed precision (torch.autocast) to train more steps in the same time

## Experiment History

See `results.tsv` for a record of all experiments (kept and discarded).
