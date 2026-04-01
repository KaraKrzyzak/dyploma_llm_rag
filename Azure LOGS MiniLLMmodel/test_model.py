"""
test3.py
========
Problem: model saved with Keras 2.15.0, we have Keras 3.8.0.
Solution: rebuild architecture manually, extract weights from zip, load by name.

Architecture matches Minillm.py exactly:
  input (128,) int32
  -> token Embedding(100277, 128)
  -> position Embedding(128, 128)   <-- THIS WAS MISSING BEFORE
  -> x = token_emb + position_emb
  -> Dropout
  -> 4x transformer block
  -> LayerNorm
  -> Dense(100277)

Each transformer block (from transformer() function in Minillm.py):
  savedX = x
  x = LayerNorm -> MultiHeadAttention(causal) -> Dropout
  x = x + savedX
  savedX = x
  x = LayerNorm -> Dense(512, gelu) -> Dense(128) -> Dropout
  x = x + savedX
"""

import numpy as np
import sys
import os
import zipfile
import tempfile

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

print("Loading TensorFlow...", flush=True)
import tensorflow as tf
tf.get_logger().setLevel('ERROR')
import tiktoken

MODEL_PATH = sys.argv[1] if len(sys.argv) > 1 else "./minillm_final.keras"
BLOCK_SIZE = 128
VOCAB_SIZE = 100277
EMBED_DIM  = 128
NUM_HEADS  = 4
FF_DIM     = 4 * EMBED_DIM   # 512, matches "4 * embedd_size" in training code
DROPOUT    = 0.1


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Rebuild model architecture matching Minillm.py exactly
# Key difference from before: position embedding added and combined with token embedding
# ══════════════════════════════════════════════════════════════════════════════

def build_model():
    inputs = tf.keras.Input(shape=(BLOCK_SIZE,), dtype='int32', name='input_1')

    # Token embeddings - maps each token ID to a vector
    token_emb = tf.keras.layers.Embedding(
        VOCAB_SIZE, EMBED_DIM, name='embedding'
    )(inputs)

    # Position embeddings - tells the model WHERE each token is in the sequence
    # We pass fixed positions [0, 1, 2, ..., 127] through a learned embedding
    positions = tf.range(start=0, limit=BLOCK_SIZE, delta=1)
    pos_emb = tf.keras.layers.Embedding(
        BLOCK_SIZE, EMBED_DIM, name='embedding_1'
    )(positions)

    # Combine token meaning + position information
    x = token_emb + pos_emb
    x = tf.keras.layers.Dropout(DROPOUT, name='dropout')(x)

    # ── Transformer block 0 ───────────────────────────────────────────────────
    # Self-attention sub-block
    x0 = tf.keras.layers.LayerNormalization(epsilon=1e-6, name='layer_normalization')(x)
    x0 = tf.keras.layers.MultiHeadAttention(
        num_heads=NUM_HEADS, key_dim=EMBED_DIM//NUM_HEADS,
        dropout=DROPOUT, use_bias=False,
        name='multi_head_attention'
    )(x0, x0, use_causal_mask=True)
    x0 = tf.keras.layers.Dropout(DROPOUT, name='dropout_1')(x0)
    x  = x + x0
    # Feed-forward sub-block
    x0 = tf.keras.layers.LayerNormalization(epsilon=1e-6, name='layer_normalization_1')(x)
    x0 = tf.keras.layers.Dense(FF_DIM, activation='gelu', name='dense')(x0)
    x0 = tf.keras.layers.Dense(EMBED_DIM, name='dense_1')(x0)
    x0 = tf.keras.layers.Dropout(DROPOUT, name='dropout_2')(x0)
    x  = x + x0

    # ── Transformer block 1 ───────────────────────────────────────────────────
    x0 = tf.keras.layers.LayerNormalization(epsilon=1e-6, name='layer_normalization_2')(x)
    x0 = tf.keras.layers.MultiHeadAttention(
        num_heads=NUM_HEADS, key_dim=EMBED_DIM//NUM_HEADS,
        dropout=DROPOUT, use_bias=False,
        name='multi_head_attention_1'
    )(x0, x0, use_causal_mask=True)
    x0 = tf.keras.layers.Dropout(DROPOUT, name='dropout_3')(x0)
    x  = x + x0
    x0 = tf.keras.layers.LayerNormalization(epsilon=1e-6, name='layer_normalization_3')(x)
    x0 = tf.keras.layers.Dense(FF_DIM, activation='gelu', name='dense_2')(x0)
    x0 = tf.keras.layers.Dense(EMBED_DIM, name='dense_3')(x0)
    x0 = tf.keras.layers.Dropout(DROPOUT, name='dropout_4')(x0)
    x  = x + x0

    # ── Transformer block 2 ───────────────────────────────────────────────────
    x0 = tf.keras.layers.LayerNormalization(epsilon=1e-6, name='layer_normalization_4')(x)
    x0 = tf.keras.layers.MultiHeadAttention(
        num_heads=NUM_HEADS, key_dim=EMBED_DIM//NUM_HEADS,
        dropout=DROPOUT, use_bias=False,
        name='multi_head_attention_2'
    )(x0, x0, use_causal_mask=True)
    x0 = tf.keras.layers.Dropout(DROPOUT, name='dropout_5')(x0)
    x  = x + x0
    x0 = tf.keras.layers.LayerNormalization(epsilon=1e-6, name='layer_normalization_5')(x)
    x0 = tf.keras.layers.Dense(FF_DIM, activation='gelu', name='dense_4')(x0)
    x0 = tf.keras.layers.Dense(EMBED_DIM, name='dense_5')(x0)
    x0 = tf.keras.layers.Dropout(DROPOUT, name='dropout_6')(x0)
    x  = x + x0

    # ── Transformer block 3 ───────────────────────────────────────────────────
    x0 = tf.keras.layers.LayerNormalization(epsilon=1e-6, name='layer_normalization_6')(x)
    x0 = tf.keras.layers.MultiHeadAttention(
        num_heads=NUM_HEADS, key_dim=EMBED_DIM//NUM_HEADS,
        dropout=DROPOUT, use_bias=False,
        name='multi_head_attention_3'
    )(x0, x0, use_causal_mask=True)
    x0 = tf.keras.layers.Dropout(DROPOUT, name='dropout_7')(x0)
    x  = x + x0
    x0 = tf.keras.layers.LayerNormalization(epsilon=1e-6, name='layer_normalization_7')(x)
    x0 = tf.keras.layers.Dense(FF_DIM, activation='gelu', name='dense_6')(x0)
    x0 = tf.keras.layers.Dense(EMBED_DIM, name='dense_7')(x0)
    x0 = tf.keras.layers.Dropout(DROPOUT, name='dropout_8')(x0)
    x  = x + x0

    # ── Final LayerNorm + output projection ───────────────────────────────────
    x = tf.keras.layers.LayerNormalization(epsilon=1e-6, name='layer_normalization_8')(x)
    outputs = tf.keras.layers.Dense(VOCAB_SIZE, use_bias=False, name='dense_8')(x)

    return tf.keras.Model(inputs=inputs, outputs=outputs, name='model')


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Extract weights.h5 from .keras zip and load by layer name
# ══════════════════════════════════════════════════════════════════════════════

def load_weights(model, keras_path):
    print("Extracting weights from archive...", flush=True)

    with zipfile.ZipFile(keras_path, 'r') as zf:
        with tempfile.NamedTemporaryFile(suffix='.h5', delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(zf.read('model.weights.h5'))

    print(f"Extracted {os.path.getsize(tmp_path)/1024/1024:.1f} MB, loading...", flush=True)

    try:
        model.load_weights(tmp_path, by_name=True, skip_mismatch=True)
        print("Weights loaded OK!", flush=True)
        ok = True
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        ok = False

    os.unlink(tmp_path)
    return ok


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Generate text token by token
# ══════════════════════════════════════════════════════════════════════════════

def pick_token(logits, temperature=0.8, top_k=50):
    """Sample next token with temperature scaling and top-k filtering."""
    logits = logits / max(temperature, 1e-8)
    if top_k > 0:
        threshold = np.sort(logits)[-min(top_k, len(logits))]
        logits[logits < threshold] = -1e10
    logits -= np.max(logits)
    probs = np.exp(logits) / np.sum(np.exp(logits))
    return int(np.random.choice(len(probs), p=probs))


def generate(model, enc, prompt, max_new_tokens=100, temperature=0.8, top_k=50):
    tokens = enc.encode(prompt)
    if not tokens:
        print("Empty prompt!")
        return
    if len(tokens) > BLOCK_SIZE:
        tokens = tokens[-BLOCK_SIZE:]

    print(f"\n[prompt: {len(tokens)} tokens | generating up to {max_new_tokens} more]")
    print("-" * 50, flush=True)
    print(prompt, end="", flush=True)

    for _ in range(max_new_tokens):
        # Pad context to BLOCK_SIZE from the left with zeros
        ctx = tokens[-BLOCK_SIZE:]
        if len(ctx) < BLOCK_SIZE:
            ctx = [0] * (BLOCK_SIZE - len(ctx)) + ctx

        x = np.array([ctx], dtype=np.int32)
        # Output: (1, BLOCK_SIZE, VOCAB_SIZE) — we want last position
        logits = model(x, training=False).numpy()[0, -1, :]

        next_tok = pick_token(logits, temperature, top_k)
        tokens.append(next_tok)

        try:
            print(enc.decode([next_tok]), end="", flush=True)
        except Exception:
            pass

        if next_tok == 100257:  # <|endoftext|>
            break

    print("\n" + "-" * 50, flush=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("Building model architecture...", flush=True)
    model = build_model()
    print(f"Architecture OK | {model.count_params():,} parameters", flush=True)

    if not os.path.exists(MODEL_PATH):
        print(f"ERROR: file not found: {MODEL_PATH}")
        sys.exit(1)

    if not load_weights(model, MODEL_PATH):
        sys.exit(1)

    print("Loading tokenizer...", flush=True)
    enc = tiktoken.get_encoding("cl100k_base")
    print("Ready!\n", flush=True)

    temperature = 0.8
    top_k       = 50
    max_tokens  = 100

    print(f"temperature={temperature}  top_k={top_k}  max_tokens={max_tokens}")
    print("Commands: 'q' = quit, 'settings' = change params\n")

    while True:
        try:
            prompt = input("Prompt: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not prompt:
            continue
        if prompt.lower() == 'q':
            print("Bye!")
            break

        if prompt.lower() == 'settings':
            try:
                temperature = float(input(f"  temperature [{temperature}]: ") or temperature)
                top_k       = int(input(f"  top_k [{top_k}]: ") or top_k)
                max_tokens  = int(input(f"  max_tokens [{max_tokens}]: ") or max_tokens)
                print(f"  -> temperature={temperature}, top_k={top_k}, max_tokens={max_tokens}")
            except ValueError:
                print("  Invalid value, keeping previous settings.")
            continue

        generate(model, enc, prompt,
                 max_new_tokens=max_tokens,
                 temperature=temperature,
                 top_k=top_k)