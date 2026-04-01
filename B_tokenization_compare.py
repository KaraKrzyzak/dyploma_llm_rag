
#  ┌─────────────────────────┬────────────────────┬────────────────┬──────────┐
#  │ Model / Czat            │ Algorytm           │ Biblioteka     │ Vocab    │
#  ├─────────────────────────┼────────────────────┼────────────────┼──────────┤
#  │ GPT-2                   │ BPE                │ tiktoken       │  50 257  │
#  │ GPT-3.5 / GPT-4 / o1    │ BPE (cl100k_base)  │ tiktoken       │ 100 277  │
#  │ ChatGPT (wszystkie)     │ BPE (cl100k_base)  │ tiktoken       │ 100 277  │
#  │ Claude (Anthropic)      │ BPE-like           │ własny (SentPc)│ ~100 000 │
#  │ Gemini (Google)         │ SentencePiece BPE  │ własny         │ ~256 000 │
#  │ LLaMA 2 / 3             │ BPE                │ SentencePiece  │  32 000  │
#  │ Mistral / Mixtral       │ BPE                │ SentencePiece  │  32 000  │
#  │ BERT / DistilBERT       │ WordPiece          │ HuggingFace    │  30 522  │
#  │ RoBERTa                 │ BPE                │ HuggingFace    │  50 265  │
#  │ T5 / mT5                │ Unigram            │ SentencePiece  │  32 100  │
#  │ XLM-RoBERTa             │ Unigram            │ SentencePiece  │ 250 002  │
#  │ Falcon                  │ BPE                │ tiktoken-like  │  65 024  │
#  │ Command R (Cohere)      │ BPE                │ tiktoken-like  │ 256 000  │
#  └─────────────────────────┴────────────────────┴────────────────┴──────────┘


from pathlib import Path
import fitz
import argparse
import time
import re
import math
import collections
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import tiktoken
from transformers import BertTokenizerFast

from CODE.tokenize.toke_bert import tokenize_bert
from CODE.tokenize.toke_bpe_gpt2 import tokenize_bpe2
from CODE.tokenize.toke_bpe_gpt4 import tokenize_bpe4
from CODE.tokenize.toke_char import tokenize_char
from CODE.tokenize.toke_word import tokenize_word


TXT_FOLDER = './TEXT_data_engineering'
NORMALIZED_TRAIN_FILE = 'final_train_data_normalized.txt'


def tokenize_metrics(toke_results, text):
    
    encode = toke_results["encode"]
    decode = toke_results["decode"]
    name = toke_results["name"]
    
    sample_text = text[:3000]
    words = sample_text.split()
    t0  = time.perf_counter()
    ids = encode(sample_text)
    encode_ms = (time.perf_counter() - t0) * 1000

    n_tokens = len(ids)
    n_words  = len(words)
    n_chars  = len(sample_text)
    

    fertility = n_tokens / max(n_words, 1) # tokens per word 
    compression = n_chars / max(n_tokens, 1) # chars per token 
    
    unique_words = list(set(words))[:300]
    oov_count = 0
    for w in unique_words:
        try:
            n = len(encode(w))
            if n > 3:
                oov_count += 1
        except Exception:
            oov_count += 1
    oov_rate = oov_count / max(len(unique_words), 1) *  100 
    
    covered = sum(1 for w in unique_words if len(encode(w)) <= 2)
    vocab_coverage = covered / max(len(unique_words), 1) * 100  

    roundtrip = None
    if decode:
        try:
            reconstructed = decode(ids)
            min_len = min(len(sample_text), len(reconstructed), 300)
            if min_len > 0:
                matches   = sum(a == b for a, b in zip(
                    sample_text[:min_len], reconstructed[:min_len]))
                roundtrip = matches / min_len * 100
        except Exception:
            pass
        
    return {
        "name":           name,
        "vocab_size":     toke_results.get("vocab_size", "?"),
        "n_tokens":       n_tokens,
        "fertility":      round(fertility, 3),       # ↓ Better
        "compression":    round(compression, 3),     # ↑ Better
        "oov_rate":       round(oov_rate, 2),         # ↓ Better
        "vocab_coverage": round(vocab_coverage, 2),  # ↑ Better
        "roundtrip":      round(roundtrip, 1) if roundtrip is not None else None, # ↑ Better
        "encode_ms":      round(encode_ms, 1),
    }


def plot_tokenizer_metrics(metrics_list, output="tokenizer_metrics.png"):

    METRICS = [
        ("fertility",      "Fertility\n(tok/word) LOWER \n Tokeny na słowo",      False),  # ↓
        ("compression",    "Compression\n(chars/tok) HIGHER \n słowo na tokeny" ,   True),   # ↑
        ("oov_rate",       "OOV rate\n(%) LOWER \n ile niezależnych słów",              False),  # ↓
        ("vocab_coverage", "Vocab\ncoverage (%) HIGHER \n ile tokenizer zna słów",        True),   # ↑
        ("roundtrip",      "Roundtrip\n(%) HIGHER \n ile się odtworzyło po tokenizacji",             True),   # ↑
        ("encode_ms",      "Encode time\n(ms) LOWER \n Czas kodowania",          False),  # ↓
    ]

    names   = [m["name"] for m in metrics_list]
    palette = plt.cm.Set2(np.linspace(0, 0.8, len(names)))
    color_map = {name: palette[i] for i, name in enumerate(names)}

    n_metrics = len(METRICS)
    n_toks    = len(names)
    x         = np.arange(n_metrics)
    width     = 0.8 / n_toks       

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor("#f8f9fa")
    ax.set_facecolor("#fdfdfd")

    for i, m in enumerate(metrics_list):
        offsets = (i - n_toks / 2 + 0.5) * width
        vals = []
        for key, _, _ in METRICS:
            v = m.get(key)
            vals.append(v if v is not None else 0)

        bars = ax.bar(
            x + offsets, vals,
            width=width * 0.9,
            color=color_map[m["name"]],
            edgecolor="white",
            linewidth=0.8,
            label=m["name"],
        )

        for bar_, val in zip(bars, vals):
            if val == 0:
                continue
            ax.text(
                bar_.get_x() + bar_.get_width() / 2,
                bar_.get_height() + ax.get_ylim()[1] * 0.005,
                f"{val:.1f}",
                ha="center", va="bottom", fontsize=6.5, color="#333",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [label for _, label, _ in METRICS],
        fontsize=9,
    )
    for xi in x[:-1]:
        ax.axvline(xi + 0.5, color="#ccc", linewidth=0.8, linestyle="--")

    ax.legend(
        handles=[mpatches.Patch(color=color_map[n], label=n) for n in names],
        title="Tokenizer", title_fontsize=9,
        fontsize=8, loc="upper right",
        framealpha=0.9, edgecolor="#ccc",
    )
    ax.set_title(
        "Tokenizer comparison — proxy metrics (no training needed)",
        fontsize=12, fontweight="bold", pad=12,
    )
    ax.set_ylabel("Value", fontsize=9)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    ax.spines[["top", "right"]].set_visible(False)

    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.show()



def tokenization():
    
    results = []
    
    txt_file = f"{TXT_FOLDER}/{NORMALIZED_TRAIN_FILE}"
    with open(txt_file, 'r', encoding='utf-8') as f:
        text = f.read()
    results.append(tokenize_bpe2(text))
    results.append(tokenize_bpe4(text))
    results.append(tokenize_bert(text))
    results.append(tokenize_char(text))
    results.append(tokenize_word(text))
    
    metrics = []
    for toke in results:
        metrics.append(tokenize_metrics(toke, text))
    
    plot_tokenizer_metrics(metrics)
           
    
tokenization()


