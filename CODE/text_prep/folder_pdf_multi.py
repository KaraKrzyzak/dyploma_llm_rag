from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from datetime import datetime
from CODE.text_prep.pdf_process import pdf_to_text
from CODE.text_prep.all_txt_from_folder import extract_texts_from_folder

def thread_pdf_processing(folder_path, num_workers, output_path, output_filename):
    
    folder = Path(folder_path)
    pdf_files = list(folder.glob('*.pdf'))
                     
    if pdf_files == []:
        print(f"No PDF files found in {folder_path}")
        return 
    
    print(f'{len(pdf_files)} files in path {folder_path}')
    
    results = []
    
    with ThreadPoolExecutor(max_workers=num_workers) as thread_multiprocessing:
        pdf_thread_line = {
            thread_multiprocessing.submit(pdf_to_text, str(pdf)): pdf for pdf in pdf_files
        }  ## creating a thread for each PDF file and mapping it to the file path
    
        for pdf_thread in as_completed(pdf_thread_line):
            result = pdf_thread.result()
            results.append(result)
            print(f"Processed: {result['file']} - Is success: {result['success']}")
    
    
    # Save to file 
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure the directory exists
        
        output_dir = output_path / 'seperated_texts'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for result in results:
            if result['success'] == True:
                text_file = output_dir / f"{Path(result['file']).stem}.txt"
                with open(text_file, 'w', encoding='utf-8') as f:
                    f.write(result['text'])
        
        def make_json_serializable(results):
            """delete dataframe before saving to json"""
            serializable = []
            for r in results:
                r_copy = r.copy()
                if 'tables' in r_copy:
                    r_copy['tables'] = [
                        {k: v for k, v in table.items() if k != 'dataframe'}
                         for table in r_copy['tables']
                    ]
                serializable.append(r_copy)
            return serializable
             
        # Report
        report_file = output_path / 'processing_report.json'
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'results': make_json_serializable(results),
            }, f, ensure_ascii=False, indent=2)
    
    if results:
        print(f"\n PDF processing completed. Now extracting texts and creating final training file...")
        extract_texts_from_folder(output_dir, output_path, output_filename)
       
    return results