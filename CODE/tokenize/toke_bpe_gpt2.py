import tiktoken


def tokenize_bpe2(text):
    
    bpe2 = tiktoken.get_encoding("gpt2")  # Get the BPE encoding for GPT-2
    
    encode = lambda e: bpe2.encode(e, allowed_special={"<|endoftext|>"})  # Function to encode text to BPE tokens, allowing special tokens like  end-of-text token 

    decode = lambda d: bpe2.decode(d)  # Function to decode BPE tokens back to text
    
    sample_bpe2 = encode(text[:300])
    
    return {
        "name": "bpe2",
        "vocab_size": bpe2.n_vocab,
        "encode": encode,
        "decode": decode,
        "sample": [bpe2.decode([i]) for i in sample_bpe2[:30]]
    }