"""
diagnose.py
===========
Step 1: Let's look INSIDE the .keras file to understand its structure.
A .keras file is just a ZIP archive containing:
  - config.json  -> model architecture
  - model.weights.h5 (or similar) -> the actual weights

This script unzips it and tells us what's inside,
so we know exactly how to load it correctly.
"""

import zipfile
import sys
import os

# ── Get model path from command line or use default ───────────────────────────
MODEL_PATH = sys.argv[1] if len(sys.argv) > 1 else "./minillm_final.keras"

print(f"Inspecting: {MODEL_PATH}")
print("=" * 60)

# ── Check if file exists ──────────────────────────────────────────────────────
if not os.path.exists(MODEL_PATH):
    print(f"ERROR: File not found: {MODEL_PATH}")
    sys.exit(1)

print(f"File size: {os.path.getsize(MODEL_PATH) / 1024 / 1024:.1f} MB")

# ── Open as ZIP and list contents ─────────────────────────────────────────────
# .keras files are ZIP archives - we can peek inside without extracting
try:
    with zipfile.ZipFile(MODEL_PATH, 'r') as zf:
        files = zf.namelist()
        print(f"\nFiles inside the .keras archive ({len(files)} total):")
        for f in files[:30]:  # show first 30 files
            info = zf.getinfo(f)
            size_kb = info.file_size / 1024
            print(f"  {f:50s}  ({size_kb:.1f} KB)")
        
        if len(files) > 30:
            print(f"  ... and {len(files) - 30} more files")
        
        # ── Try to read config.json if it exists ──────────────────────────────
        config_candidates = [f for f in files if 'config' in f.lower() and f.endswith('.json')]
        print(f"\nConfig files found: {config_candidates}")
        
        if config_candidates:
            with zf.open(config_candidates[0]) as cf:
                content = cf.read().decode('utf-8')
                # Show first 500 chars to understand format
                print(f"\nFirst 500 chars of {config_candidates[0]}:")
                print(content[:500])
        
        # ── Check for weights files ───────────────────────────────────────────
        weight_files = [f for f in files if '.h5' in f or 'weights' in f.lower()]
        print(f"\nWeight files found: {weight_files}")
        
        # ── Check Keras version info ──────────────────────────────────────────
        version_files = [f for f in files if 'version' in f.lower() or 'metadata' in f.lower()]
        print(f"Version/metadata files: {version_files}")
        
        for vf in version_files:
            with zf.open(vf) as vfile:
                print(f"\nContent of {vf}:")
                print(vfile.read().decode('utf-8')[:300])

except zipfile.BadZipFile:
    print("ERROR: File is not a valid ZIP/keras archive!")
    print("It might be a SavedModel format or corrupted file.")
    
    # Check if it's a directory (SavedModel)
    if os.path.isdir(MODEL_PATH):
        print("It's actually a directory - might be SavedModel format")
        print("Contents:", os.listdir(MODEL_PATH))

print("\n" + "=" * 60)
print("Diagnosis complete!")