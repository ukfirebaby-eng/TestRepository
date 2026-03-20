"""
train.py — Agent-modifiable nanoGPT-style training script.

The agent may change ANYTHING in this file: architecture, optimizer,
hyperparameters, data loading strategy, etc.

Fixed contract (DO NOT break these):
  - Training runs for exactly TRAIN_SECONDS wall-clock seconds.
  - The final line of stdout must be:  FINAL_VAL_BPB=<float>
  - Data is loaded from train.bin / val.bin (uint16 numpy arrays).
  - Tokenizer metadata is in meta.pkl (keys: vocab_size, stoi, itos).
"""

import math
import os
import pickle
import time
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
from torch.nn import functional as F

# ---------------------------------------------------------------------------
# Hyperparameters — agent should tune these
# ---------------------------------------------------------------------------

@dataclass
class Config:
    # Model architecture
    vocab_size: int = 0          # filled from meta.pkl
    block_size: int = 256        # context length
    n_layer: int = 4
    n_head: int = 4
    n_embd: int = 128
    dropout: float = 0.0

    # Training
    batch_size: int = 32
    learning_rate: float = 1e-3
    weight_decay: float = 0.0
    grad_clip: float = 1.0

    # Fixed — do not change
    train_seconds: int = 300
    eval_interval: int = 60      # seconds between val evaluations
    eval_iters: int = 50         # batches to average for val loss
    device: str = "cuda" if torch.cuda.is_available() else "cpu"


cfg = Config()

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

script_dir = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(script_dir, "meta.pkl"), "rb") as f:
    meta = pickle.load(f)
cfg.vocab_size = meta["vocab_size"]

train_data = np.memmap(os.path.join(script_dir, "train.bin"), dtype=np.uint16, mode="r")
val_data = np.memmap(os.path.join(script_dir, "val.bin"), dtype=np.uint16, mode="r")


def get_batch(split):
    data = train_data if split == "train" else val_data
    ix = torch.randint(len(data) - cfg.block_size, (cfg.batch_size,))
    x = torch.stack([torch.from_numpy(data[i : i + cfg.block_size].astype(np.int64)) for i in ix])
    y = torch.stack([torch.from_numpy(data[i + 1 : i + 1 + cfg.block_size].astype(np.int64)) for i in ix])
    return x.to(cfg.device), y.to(cfg.device)


@torch.no_grad()
def estimate_val_loss():
    losses = []
    for _ in range(cfg.eval_iters):
        x, y = get_batch("val")
        _, loss = model(x, y)
        losses.append(loss.item())
    return float(np.mean(losses))


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class CausalSelfAttention(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        assert cfg.n_embd % cfg.n_head == 0
        self.c_attn = nn.Linear(cfg.n_embd, 3 * cfg.n_embd)
        self.c_proj = nn.Linear(cfg.n_embd, cfg.n_embd)
        self.attn_drop = nn.Dropout(cfg.dropout)
        self.resid_drop = nn.Dropout(cfg.dropout)
        self.n_head = cfg.n_head
        self.n_embd = cfg.n_embd
        self.register_buffer(
            "bias",
            torch.tril(torch.ones(cfg.block_size, cfg.block_size)).view(
                1, 1, cfg.block_size, cfg.block_size
            ),
        )

    def forward(self, x):
        B, T, C = x.size()
        q, k, v = self.c_attn(x).split(self.n_embd, dim=2)
        k = k.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
        q = q.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
        v = v.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
        att = (q @ k.transpose(-2, -1)) * (1.0 / math.sqrt(k.size(-1)))
        att = att.masked_fill(self.bias[:, :, :T, :T] == 0, float("-inf"))
        att = F.softmax(att, dim=-1)
        att = self.attn_drop(att)
        y = att @ v
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        return self.resid_drop(self.c_proj(y))


class MLP(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.c_fc = nn.Linear(cfg.n_embd, 4 * cfg.n_embd)
        self.c_proj = nn.Linear(4 * cfg.n_embd, cfg.n_embd)
        self.drop = nn.Dropout(cfg.dropout)

    def forward(self, x):
        return self.drop(self.c_proj(F.gelu(self.c_fc(x))))


class Block(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.ln1 = nn.LayerNorm(cfg.n_embd)
        self.ln2 = nn.LayerNorm(cfg.n_embd)
        self.attn = CausalSelfAttention(cfg)
        self.mlp = MLP(cfg)

    def forward(self, x):
        x = x + self.attn(self.ln1(x))
        x = x + self.mlp(self.ln2(x))
        return x


class GPT(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.tok_emb = nn.Embedding(cfg.vocab_size, cfg.n_embd)
        self.pos_emb = nn.Embedding(cfg.block_size, cfg.n_embd)
        self.drop = nn.Dropout(cfg.dropout)
        self.blocks = nn.Sequential(*[Block(cfg) for _ in range(cfg.n_layer)])
        self.ln_f = nn.LayerNorm(cfg.n_embd)
        self.head = nn.Linear(cfg.n_embd, cfg.vocab_size, bias=False)
        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if isinstance(module, nn.Linear) and module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.LayerNorm):
            nn.init.zeros_(module.bias)
            nn.init.ones_(module.weight)

    def forward(self, idx, targets=None):
        B, T = idx.size()
        pos = torch.arange(T, device=idx.device)
        x = self.drop(self.tok_emb(idx) + self.pos_emb(pos))
        x = self.blocks(x)
        x = self.ln_f(x)
        logits = self.head(x)
        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1))
        return logits, loss


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

model = GPT(cfg).to(cfg.device)
optimizer = torch.optim.AdamW(
    model.parameters(), lr=cfg.learning_rate, weight_decay=cfg.weight_decay
)

n_params = sum(p.numel() for p in model.parameters())
print(f"Model parameters: {n_params:,}")
print(f"Device: {cfg.device}")
print(f"Training for {cfg.train_seconds}s ...")

start_time = time.time()
last_eval_time = start_time - cfg.eval_interval  # trigger eval on first step
step = 0
last_val_bpb = float("inf")

while True:
    elapsed = time.time() - start_time
    if elapsed >= cfg.train_seconds:
        break

    # Periodic validation
    if (time.time() - last_eval_time) >= cfg.eval_interval:
        model.eval()
        val_loss = estimate_val_loss()
        val_bpb = val_loss / math.log(2)
        last_val_bpb = val_bpb

        # Quick train loss estimate
        model.train()
        x, y = get_batch("train")
        _, train_loss = model(x, y)

        print(
            f"STEP={step} TRAIN_LOSS={train_loss.item():.4f} "
            f"VAL_LOSS={val_loss:.4f} VAL_BPB={val_bpb:.4f} TIME={elapsed:.1f}s"
        )
        last_eval_time = time.time()

    # Training step
    model.train()
    x, y = get_batch("train")
    _, loss = model(x, y)
    optimizer.zero_grad()
    loss.backward()
    if cfg.grad_clip > 0:
        nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip)
    optimizer.step()
    step += 1

# Final validation
model.eval()
val_loss = estimate_val_loss()
final_bpb = val_loss / math.log(2)
print(f"FINAL_VAL_BPB={final_bpb:.6f}")
