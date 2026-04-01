from CODE.text_prep.folder_pdf_multi import thread_pdf_processing
from AB_normalization import normalize_text
from CODE.text_prep.www_txt import run_scraping

PDF_FOLDER = './PDF_medic_trials'
PDF_FOLDER_PROCESSED = './TEXT_medic_trials'
TXT_FOLDER_SEPARATED = './TEXT_medic_trials/seperated_texts'
NUM_WORKERS = 4
FINAL_TRAIN_FILE = 'final_train_data.txt'
NORMALIZED_TRAIN_FILE = 'final_train_data_normalized.txt'
TABLES_JSONL_FILE = f'{PDF_FOLDER_PROCESSED}/tables.jsonl' 

def data_preparation():
    
    scraped = run_scraping(TXT_FOLDER_SEPARATED)
    
    results = thread_pdf_processing(
        folder_path=PDF_FOLDER,
        num_workers=NUM_WORKERS,
        output_path=PDF_FOLDER_PROCESSED,
        output_filename=FINAL_TRAIN_FILE
    )
    
    if results:
        print(f"\n✅ DONE!")

    normal_results =normalize_text(
        input_file=f"{PDF_FOLDER_PROCESSED}/{FINAL_TRAIN_FILE}",
        output_file=f"{PDF_FOLDER_PROCESSED}/{NORMALIZED_TRAIN_FILE}",
        tables_jsonl_file=TABLES_JSONL_FILE,  
        source_label=FINAL_TRAIN_FILE,    
    )
    
    if normal_results:
        for result in normal_results:
            print(f"\n✅ {result}")

data_preparation()

