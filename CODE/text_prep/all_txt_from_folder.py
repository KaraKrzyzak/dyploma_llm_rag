from pathlib import Path
import json

def extract_texts_from_folder(folder_path, output_path, output_filename):
    
    folder = Path(folder_path)
    
    all_txt = []
    
    for txt_file in folder.glob('*.txt'):
        with open(txt_file, 'r', encoding='utf-8') as i:
            text = i.read()
            all_txt.append(text)
    
    if not all_txt:
        print("No text concated")
        return None    
    
    test_data = '\n\n<|endoftext|>\n\n'.join(all_txt)
    
    output_dir = Path(output_path)
    final_path = output_dir / output_filename
    
    with open(final_path, 'w', encoding='utf-8') as o:
        o.write(test_data)
        
    print(f"Done - files {len(all_txt)}, characters {len(test_data):,}, words {len(test_data.split()):,}")
    
    return test_data
        