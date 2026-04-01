import re


def clean_code_text(text):

    text = re.sub(r'\.{2,}', '.', text)  # Replace multiple dots with single dot
    text = re.sub(r'\n+', '\n', text)  # Replace multiple newlines with single newline
    text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)  # Fix hyphenated words at line breaks
    
    text = text.replace('"', '"').replace('"', '"')  # Normalize quotes
    text = text.replace(''', "'").replace(''', "'") # Normalize single quotes
    text = text.replace('„', '"').replace('"', '"')  # Normalize German quotes
    
    text = re.sub(r'[^\S\n]+', ' ', text)   # wiele spacji/tabów → jedna spacja
    text = re.sub(r' \n', '\n', text)        # spacja przed newlinem → usuń
    text = re.sub(r'\n ', '\n', text)        # spacja po newlinie → usuń

    return text.strip()  # Remove leading and trailing whitespace