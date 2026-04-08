#!/usr/bin/env python3
"""
Debug script: Shows raw text on pages with microscopic data
"""

import sys
import re


def extract_microscopic_universal_debug(file_path: str) -> list:
    """
    DEBUG VERSION: Shows exactly what text is on each page
    """
    import fitz
    
    print("\n" + "="*80)
    print("🔬🔬🔬 DEBUG MODE: Page Text Inspection 🔬🔬🔬")
    print("="*80 + "\n")

    try:
        doc = fitz.open(file_path)
        
        # Focus on pages that have microscopic keywords
        target_pages = [4, 5, 6, 7]  # Pages 5-8 (0-indexed)
        
        for page_num in target_pages:
            if page_num >= len(doc):
                continue
                
            page = doc[page_num]
            text = page.get_text()
            
            print(f"\n{'='*80}")
            print(f"📍 PAGE {page_num + 1} RAW TEXT:")
            print(f"{'='*80}\n")
            
            lines = text.split('\n')
            
            # Show ALL lines (this is key!)
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                
                # Highlight lines with microscopic keywords
                has_keyword = any(
                    kw in line_stripped.lower()
                    for kw in ['pus', 'epithelial', 'rbc', 'cast', 'crystal', 
                               'bacteria', 'microscopic', '/hpf', '/lpf']
                )
                
                if has_keyword or ('examination' in line_stripped.lower() and len(line_stripped) < 50):
                    print(f"  ⭐ [{i:3d}] {line_stripped[:120]}")
                elif line_stripped:  # Only show non-empty lines
                    print(f"      [{i:3d}] {line_stripped[:100]}")
            
        doc.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


# Add this to your test script and run it:
if __name__ == "__main__":
    pdf_file = sys.argv[1] if len(sys.argv) > 1 else "pathkinds.pdf"
    
    # Run diagnostic FIRST
    extract_microscopic_universal_debug(pdf_file)