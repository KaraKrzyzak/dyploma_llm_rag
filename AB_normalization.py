import unicodedata
import re
from pathlib import Path
import json


def normalize_accent_code(text):

    text = unicodedata.normalize('NFC', text)

    replacements = {
        '™': 'TM',
        '©': '(c)',
        '®': '(R)',
        '…': '...',
        '–': '-',
        '—': '-',
        '\u2018': "'",  # '
        '\u2019': "'",  # '
        '\u201c': '"',  # "
        '\u201d': '"',  # "
        '\u201e': '"',  # „
        '\u201a': "'",  # ‚
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def normalize_remove_urls(text):

    text = re.sub(r'https?://\S+', '<URL>', text)
    text = re.sub(r'www\.\S+', '<URL>', text)
    return text


def normalize_remove_emails(text):

    email = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
    text = re.sub(email, '<EMAIL>', text)
    return text


def normalize_fix_line_breaks(text):

    text = re.sub(r'\n{2,}', '\n\n', text)

    text = re.sub(
        r'(?<![.!?])\n(?!\n)(?=[a-ząćęłńóśźż,;)])',
        ' ',
        text
    )

    text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)

    return text


def normalize_dots(text):

    text = re.sub(r'\.{3,}', ' ', text)
    text = re.sub(r'(\.\s+){3,}', ' ', text)

    return text


def normalize_spaced_letters(text):

    spaced = r'\b([A-Za-z])([ \t][A-Za-z]){2,}\b'

    def remove_spaces(match):
        return match.group(0).replace(' ', '').replace('\t', '')

    text = re.sub(spaced, remove_spaces, text, flags=re.IGNORECASE)
    return text


def normalize_whitespace(text):
    text = re.sub(r'[^\S\n]+', ' ', text)   
    text = re.sub(r' \n', '\n', text)      
    text = re.sub(r'\n ', '\n', text)        
    return text


def normalize_random(text):

    text = re.sub('e b o o k :  t h e  b i g  b o o k  o f  d ata  e n g i n e e r i n g    3 r d  e d i t i o n', ' ', text)

    return text


def normalize_pdf_artifacts(text):

    text = re.sub(r'([a-ząćęłńóśźż])\d{1,3}(\n|$)', r'\1\2', text)


    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^[a-zA-Z]$', stripped):     
            continue
        if re.match(r'^\d{1,4}$', stripped):    
            continue
        clean_lines.append(line)
    text = '\n'.join(clean_lines)

    text = re.sub(r'(?m)^[a-z]\s+(?=[a-ząćęłńóśźż]{4})', '', text)

    text = re.sub(r'(issn\s+[\d-]+)\s+(?=[a-ząćęłńóśźżA-Z])', r'\1\n', text)

    return text


def normalize_table_artifacts(text):

    lines = text.split('\n')
    clean_lines = []

    for line in lines:
        stripped = line.strip()

        if re.match(r'^[-+|=\s]{3,}$', stripped) and ('|' in stripped or '---' in stripped):
            continue

        if '|' in stripped:
            pipe_count = stripped.count('|')
            total_len = len(stripped)

            if pipe_count >= 2 and total_len > 0:
                pipe_ratio = pipe_count / total_len
                if pipe_ratio > 0.08:   
                    continue

                segments = [s.strip() for s in stripped.split('|') if s.strip()]
                if segments:
                    avg_seg = sum(len(s) for s in segments) / len(segments)
                    if avg_seg < 15 and pipe_count >= 3:
                        continue

        clean_lines.append(line)

    return '\n'.join(clean_lines)



TABLE_HEADER = re.compile(r'\[TABELA strona (\d+)(?:, nr (\d+))?\]')
TABLE_MAX_CHARS = 2000


def extract_tables(text):
    tables = []
    positions_to_remove = []

    for header_match in TABLE_HEADER.finditer(text):
        start = header_match.start()
        content_start = header_match.end()

        page = int(header_match.group(1))
        table_num = int(header_match.group(2)) if header_match.group(2) else 1

        chunk = text[content_start: content_start + TABLE_MAX_CHARS]

        next_header = TABLE_HEADER.search(chunk)
        double_newline = chunk.find('\n\n')

        if next_header and (double_newline == -1 or next_header.start() < double_newline):
            end = content_start + next_header.start()
        elif double_newline != -1:
            end = content_start + double_newline
        else:
            end = content_start + len(chunk)

        content = text[content_start:end].strip()

        if len(content) < 20:
            positions_to_remove.append((start, end))
            continue

        tables.append({
            'page': page,
            'table_num': table_num,
            'raw_text': content,
        })
        positions_to_remove.append((start, end))

    text_no_tables = text
    for start, end in sorted(positions_to_remove, reverse=True):
        text_no_tables = text_no_tables[:start] + '\n\n' + text_no_tables[end:]

    return text_no_tables, tables


def _is_garbled(text):
    alpha_words = re.findall(r'\b[a-ząćęłńóśźż]{4,}\b', text.lower())
    if len(alpha_words) < 5:
        return False  

    reversed_endings = re.compile(r'(margorp|awzan|abzcil|remun|orykat|amnrof|olkzs)$')
    reversed_pattern = re.compile(r'(ajc|ain|wod|acin|orps|orts|ejn)$')

    hits = sum(1 for w in alpha_words
               if reversed_endings.search(w) or reversed_pattern.search(w))
    ratio = hits / len(alpha_words)

    return ratio > 0.25 


def save_tables_to_jsonl(tables, source_file, output_path):
    if not tables:
        return 0

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    saved = 0
    skipped = 0
    with open(output_path, 'a', encoding='utf-8') as f:
        for table in tables:
            content = unicodedata.normalize('NFC', table['raw_text'])
            content = re.sub(r'[^\S\n]+', ' ', content)
            content = content.lower().strip()

            if not content:
                continue

            if _is_garbled(content):
                skipped += 1
                continue

            record = {
                'source': source_file,
                'page': table['page'],
                'table_num': table['table_num'],
                'content': content,
                'type': 'table',
            }
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
            saved += 1

    return saved, skipped

def normalize_text(input_file, output_file, tables_jsonl_file=None, source_label=None):

    results = []

    with open(input_file, 'r', encoding='utf-8') as f:
        text = f.read()

    text, tables = extract_tables(text)
    results.append(f'📊 Znaleziono tabel: {len(tables)}')

    if tables_jsonl_file:
        label = source_label or Path(input_file).name
        saved, skipped = save_tables_to_jsonl(tables, label, tables_jsonl_file)
        results.append(f'💾 Zapisano tabel do JSONL: {saved}, pominięto (porozrywanych): {skipped} → {tables_jsonl_file}')

    # Pipeline normalizacji tekstu
    text = normalize_accent_code(text)
    text = normalize_remove_urls(text)
    text = normalize_remove_emails(text)
    text = normalize_pdf_artifacts(text)       
    text = normalize_fix_line_breaks(text)
    text = normalize_dots(text)
    text = normalize_spaced_letters(text)
    text = normalize_table_artifacts(text)   
    text = normalize_whitespace(text)
    text = normalize_random(text)
    text = text.lower()

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(text.strip())  

    if text:
        results.append('✅ Normalization completed successfully.')
    else:
        results.append('⚠️ Normalization resulted in empty text.')

    return results