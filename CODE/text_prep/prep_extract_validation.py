
def extract_validation(text, filename):
    
    issues = []
    warnings = []
    
    if len(text) == 0 or not text:
        issues.append("No text extracted from the PDF.")
    if len(text) < 200:
        warnings.append(f'Extracted only {len(text)} letters')
    
    #Calculation of % of spaces in the text
    spaces_ratio = text.count(' ') / len(text) if len(text) > 0 else 0
    
    if spaces_ratio < 0.1:
        warnings.append(f'Spaces Ratio {spaces_ratio:.2%} - check if not concated words')
    
    return {
        'good': len(issues) == 0,
        'too check': len(issues) == 0 and len(warnings) > 0,
        'issues': issues,
        'warnings': warnings,
        'stats': {
            'length': len(text),
            'spaces_ratio': spaces_ratio,
            'words': len(text.split())
        }
    }