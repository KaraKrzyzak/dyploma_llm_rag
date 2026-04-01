import tiktoken

def tokenize_bpe4(text):
    
    bpe4 = tiktoken.get_encoding("cl100k_base")  # Get the BPE encoding for GPT-4
    
    encode = lambda e: bpe4.encode(e, allowed_special={"<|endoftext|>"})  # Function to encode text to BPE tokens, allowing special tokens like  end-of-text token 

    decode = lambda d: bpe4.decode(d)  # Function to decode BPE tokens back to text
    
    sample_bpe4 = encode(text[:300])
    
    return {
        "name": "bpe4",
        "vocab_size": bpe4.n_vocab,
        "encode": encode,
        "decode": decode,
        "sample": [bpe4.decode([i]) for i in sample_bpe4[:30]]
    }