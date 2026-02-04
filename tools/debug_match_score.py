import sys
import os
from pathlib import Path

# Add src to sys.path
sys.path.append(os.path.abspath("src"))

try:
    from rapidfuzz import fuzz
    print(f"Rapidfuzz version: installed")
except ImportError:
    print("Rapidfuzz NOT installed, using difflib")
    fuzz = None

from difflib import SequenceMatcher
from ludiglot.core.text_builder import normalize_en

def test_score(query_raw, target_raw):
    query = normalize_en(query_raw)
    target = normalize_en(target_raw)
    
    print(f"\nQuery raw: '{query_raw}'")
    print(f"Target raw: '{target_raw}'")
    print(f"Query norm: '{query}'")
    print(f"Target norm: '{target}'")
    
    # Difflib
    s = SequenceMatcher(None, query, target)
    print(f"Difflib Ratio: {s.ratio():.4f}")
    
    # Rapidfuzz
    if fuzz:
        print(f"Rapidfuzz Ratio: {fuzz.ratio(query, target)/100.0:.4f}")
        print(f"Rapidfuzz Partial: {fuzz.partial_ratio(query, target)/100.0:.4f}")

# Case from user
ocr_text = "Mornye The New Solar Ceremony is nearly upon us. It's the culmination of ecades of work. Everyone at the Collective is giving their all to realize it."
db_entry = "The New Solar Ceremony is nearly upon us. It's the culmination of decades of work. Everyone at the Collective is giving their all to realize it."

test_score(ocr_text, db_entry)

# Without prefix
ocr_text_clean = "The New Solar Ceremony is nearly upon us. It's the culmination of ecades of work. Everyone at the Collective is giving their all to realize it."
test_score(ocr_text_clean, db_entry)
