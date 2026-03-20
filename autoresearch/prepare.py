"""
prepare.py — Fixed data preparation infrastructure.

Downloads TinyShakespeare, builds a character-level tokenizer, and saves
train.bin / val.bin as numpy memory-mapped uint16 arrays plus meta.pkl.

THIS FILE IS READ-ONLY to the agent. Do not modify.
"""

import os
import pickle
import numpy as np

DATA_URL = "https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt"
DATA_FILE = "input.txt"
TRAIN_SPLIT = 0.9


def download_dataset():
    if os.path.exists(DATA_FILE):
        print(f"Dataset already exists: {DATA_FILE}")
        return
    print(f"Downloading TinyShakespeare from {DATA_URL} ...")
    import urllib.request
    urllib.request.urlretrieve(DATA_URL, DATA_FILE)
    print(f"Saved to {DATA_FILE}")


def build_tokenizer(text):
    chars = sorted(set(text))
    vocab_size = len(chars)
    stoi = {ch: i for i, ch in enumerate(chars)}
    itos = {i: ch for i, ch in enumerate(chars)}
    print(f"Vocabulary size: {vocab_size} characters")
    return stoi, itos, vocab_size


def encode(text, stoi):
    return [stoi[c] for c in text]


def main():
    # Change to script directory so relative paths work
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    download_dataset()

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    print(f"Dataset length: {len(text):,} characters")

    stoi, itos, vocab_size = build_tokenizer(text)

    # Encode entire dataset
    data = np.array(encode(text, stoi), dtype=np.uint16)
    print(f"Encoded length: {len(data):,} tokens")

    # Train / val split
    n = int(TRAIN_SPLIT * len(data))
    train_data = data[:n]
    val_data = data[n:]
    print(f"Train tokens: {len(train_data):,}  |  Val tokens: {len(val_data):,}")

    # Save binary files
    train_data.tofile("train.bin")
    val_data.tofile("val.bin")
    print("Saved train.bin and val.bin")

    # Save tokenizer metadata
    meta = {"vocab_size": vocab_size, "stoi": stoi, "itos": itos}
    with open("meta.pkl", "wb") as f:
        pickle.dump(meta, f)
    print("Saved meta.pkl")
    print("Data preparation complete.")


if __name__ == "__main__":
    main()
