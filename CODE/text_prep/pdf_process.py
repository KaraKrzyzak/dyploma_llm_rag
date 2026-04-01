import fitz
from pathlib import Path
import pdfplumber
from CODE.text_prep.prep_clean_code import clean_code_text
from CODE.text_prep.prep_extract_validation import extract_validation

def pdf_to_text(pdf_path):
    
    filename = Path(pdf_path).name
    
    result = {
        'file': filename,
        'path': str(pdf_path),
        'text': '',
        'success': False,
        'validation': {},
        'error': None,
        'num_pages': 0,
        'tables': [] 
    }
    """
    try:
        pdf = fitz.open(pdf_path)
        pdf_text = ""
        all_tables = []
        
        for page in pdf:
            pdf_text = pdf_text + page.get_text()
            
            tabs = page.find_tables(strategy="text")   # search for tables on the page
            for tab in tabs:
                df = tab.to_pandas()
                df = df.dropna(how='all').dropna(axis=1, how='all')
                df = df.fillna('')
                
                if df.empty:
                    continue
                
                table_text = df.to_csv(sep='|', index=False)
                all_tables.append({
                    'page': page.number + 1,
                    'dataframe': df,
                    'text': table_text,        # text representation of the table
                    'rows': len(df),
                    'cols': len(df.columns)
                })

                pdf_text += f"\n\n[TABELA strona {page.number + 1}]\n{table_text}\n"
        
        
        nb_pages = len(pdf)
        pdf.close()
        
        cleaned_text = clean_code_text(pdf_text)
        validated_text = extract_validation(cleaned_text, filename)
        
        result['text'] = cleaned_text
        result['success'] = validated_text['good']
        result['num_pages'] = nb_pages
        result['validation'] = validated_text
        result['tables'] = all_tables 
        """
    
    try:
        # For text
        pdf_fitz = fitz.open(pdf_path)
        pages_text = {}
        for page in pdf_fitz:
            pages_text[page.number] = page.get_text()
        nb_pages = len(pdf_fitz)
        pdf_fitz.close()

        # For tables
        all_tables = []
        tables_by_page = {}

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                # Will not work for all but lines for tables
                tables = page.extract_tables({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 3,
                    "join_tolerance": 3,
                    "min_words_vertical": 3,
                    "min_words_horizontal": 1,
                })

                valid_tables = []
                for table in tables:
                    # Clean empty
                    clean = [
                        [cell.strip() if cell else "" for cell in row]
                        for row in table
                        if any(cell and cell.strip() for cell in row)
                    ]
                    if len(clean) < 2:
                        continue
                    cols = max(len(row) for row in clean)
                    if cols < 2:
                        continue

                    # Conditions min 3 lines
                    if len(clean) < 3:
                        continue

                    # 2. Count of not empty
                    total_cells = sum(len(row) for row in clean)
                    filled_cells = sum(1 for row in clean for cell in row if cell.strip())
                    fill_ratio = filled_cells / total_cells if total_cells > 0 else 0
                    if fill_ratio < 0.3:   # if not 30% fill then delete
                        continue

                    # 3.Check column counts for all
                    row_lengths = [len(row) for row in clean]
                    most_common_len = max(set(row_lengths), key=row_lengths.count)
                    consistent_rows = sum(1 for l in row_lengths if l == most_common_len)
                    consistency_ratio = consistent_rows / len(clean)
                    if consistency_ratio < 0.5:   # min 50 % should have
                        continue

                    # 4. Odrzuć tabele gdzie komórki są zbyt krótkie (pojedyncze litery = PDF artefakt)
                    all_cells_text = [cell for row in clean for cell in row if cell.strip()]
                    if all_cells_text:
                        avg_cell_len = sum(len(c) for c in all_cells_text) / len(all_cells_text)
                        if avg_cell_len < 1:   # średnia < 3 znaki = porozrywany tekst
                            continue

                    table_text = _table_to_text(clean)
                    valid_tables.append({
                        'page': page.page_number,
                        'text': table_text,
                        'rows': len(clean),
                        'cols': cols,
                        'data': clean
                    })

                if valid_tables:
                    tables_by_page[page.page_number - 1] = valid_tables

        #  concat text with tables 
        pdf_text = ""
        for page_num in sorted(pages_text.keys()):
            pdf_text += pages_text[page_num]

            if page_num in tables_by_page:
                for i, tab in enumerate(tables_by_page[page_num]):
                    pdf_text += f"\n\n[TABELA strona {page_num + 1}, nr {i+1}]\n"
                    pdf_text += tab['text']
                    pdf_text += "\n"
                    all_tables.append(tab)

        cleaned_text = clean_code_text(pdf_text)
        validated_text = extract_validation(cleaned_text, filename)

        result['text'] = cleaned_text
        result['success'] = validated_text['good']
        result['num_pages'] = nb_pages
        result['validation'] = validated_text
        result['tables'] = all_tables    
        
    except Exception as e:
        result['error'] = str(e)
        result['success'] = False
    return result

def _table_to_text(table: list[list[str]]) -> str:

    if not table:
        return ""

    # 
    col_widths = [0] * max(len(row) for row in table)
    for row in table:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    lines = []
    for row_idx, row in enumerate(table):
        cells = [str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)]
        lines.append(" | ".join(cells))
        if row_idx == 0:
            lines.append("-+-".join("-" * w for w in col_widths))

    return "\n".join(lines)