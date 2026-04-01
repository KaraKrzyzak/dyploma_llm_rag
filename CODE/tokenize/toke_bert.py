from transformers import BertTokenizerFast


def tokenize_bert(text):
    
    bert = BertTokenizerFast.from_pretrained('bert-base-uncased')  # Load the BERT tokenizer
    
    encode = lambda e: bert.encode(e, add_special_tokens=True)
    
    decode = lambda d: bert.decode(d, skip_special_tokens=True)
    
    sample_bert = encode(text[:300])  # Encode a sample text to get the token IDs
    
    return {
        "name": "bert",
        "vocab_size": bert.vocab_size,
        "encode": encode,
        "decode": decode,
        "sample": [bert.convert_ids_to_tokens(sample_bert[:30])]
    }