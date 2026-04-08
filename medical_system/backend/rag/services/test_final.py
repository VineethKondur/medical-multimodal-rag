#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from table_extractor import extract_tables, extract_microscopic_universal

pdf_file = sys.argv[1] if len(sys.argv) > 1 else "pathkinds.pdf"

print("="*80)
print("FINAL TEST: Microscopic Extraction v5.0")
print("="*80 + "\n")

# Test 1: Just microscopic extraction
print("TEST 1: Standalone Microscopic Extraction\n")
micro = extract_microscopic_universal(pdf_file)

if micro:
    print(f"\n✅ SUCCESS! Got {len(micro)} tests:\n")
    for m in micro:
        print(f"  ★ {m['test']:<25} {m['value']:<15} {m.get('unit','')}")
else:
    print("\n❌ No tests found")

# Test 2: Full extraction with automatic fallback
print("\n" + "="*80)
print("TEST 2: Full Table Extraction (with emergency fallback)")
print("="*80 + "\n")

all_results = extract_tables(pdf_file)

micro_from_all = [
    r for r in all_results 
    if any(kw in r['test'].lower() for kw in 
           ['pus cells', 'epithelial', 'casts', 'crystals', 'bacteria'])
]

print(f"\n📊 FINAL SUMMARY:")
print(f"   Total tests extracted: {len(all_results)}")
print(f"   Microscopic tests: {len(micro_from_all)}")

if micro_from_all:
    print(f"\n🔬🔬🔬 MICROSCOPIC TESTS IN OUTPUT:")
    for m in micro_from_all:
        print(f"  ✓ {m['test']:<25} {m['value']:<15} {m.get('unit','')}")
    
    print(f"\n🎉🎉🎉 SUCCESS! All microscopic data extracted!")
else:
    print(f"\n⚠️  Still missing microscopic data")

print("\n" + "="*80)