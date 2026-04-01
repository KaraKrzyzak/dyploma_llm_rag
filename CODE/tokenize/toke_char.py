
def tokenize_char(text):
    char_list = sorted(set(text))  # Get unique characters and sort them
    char_idx = {char: i for i, char in enumerate(char_list)}  # Create a mapping from character to index
    idx_char = {i: char for char, i in char_idx.items()}  # Create a mapping from index to character
    
    encode = lambda e: [char_idx[char] for char in e if char in char_idx]  # Function to encode text to indices
    """ Function to encode text to indices. It takes a string 'e' 
        and returns a list of indices corresponding to the characters in 'e' 
        based on the 'char_idx' mapping. 
        It also checks if the character is in the mapping before encoding to avoid errors."""
        
    decode = lambda d: ''.join([idx_char[idx] for idx in d if idx in idx_char])  # Function to decode indices back to text
    """ Function to decode indices back to text. It takes a list of indices 'd' 
        and returns a string by joining the characters corresponding to the indices in 'd' 
        based on the 'idx_char' mapping. 
        It also checks if the index is in the mapping before decoding to avoid errors."""
        
    return {
        "name": "char",
        "vocab_size": len(char_list),
        "encode": encode,
        "decode": decode,
        "sample": char_list[:30]
    }