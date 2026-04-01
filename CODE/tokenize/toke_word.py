import re
import collections

def tokenize_word(text):
    
    words = re.findall(r"\w+|[^\w\s]", text.lower())  # Use regex to find words and punctuation, and convert to lowercase
    counter = collections.Counter(words)  # Count the frequency of each word
    
    vocab = sorted(counter.keys())  # Get unique words and sort them
    word_idx = {word: i for i, word in enumerate(vocab)}  # Create a mapping from word to index
    idx_word = {i: word for word, i in word_idx.items()}  # Create a mapping from index to word
    
    encode = lambda e: [word_idx[word] for word in words if word in word_idx]
    """ Function to encode text to indices. It takes a string 'e' 
        and returns a list of indices corresponding to the words in 'e' 
        based on the 'word_idx' mapping. 
        It also checks if the word is in the mapping before encoding to avoid errors."""
    decode = lambda d: ' '.join([idx_word[idx] for idx in d if idx in idx_word])
    """ Function to decode indices back to text. It takes a list of indices 'd' 
        and returns a string by joining the words corresponding to the indices in 'd' 
        based on the 'idx_word' mapping. 
        It also checks if the index is in the mapping before decoding to avoid errors."""
        
    return {
        "name": "word",
        "vocab_size": len(vocab),
        "encode": encode,
        "decode": decode,
        "sample": vocab[:30]
    }