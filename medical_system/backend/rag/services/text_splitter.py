# from langchain_text_splitters import RecursiveCharacterTextSplitter
# from langchain_core.documents import Document

# def split_text(text: str):
#     """
#     Splits clean text into chunks for the vectorstore.
    
#     Pipeline Updates:
#     1. Adds metadata (chunk_type) to enable filtered search later.
#     2. Prioritizes newline separators to keep test result rows intact.
#     3. No longer needs to separate 'Clinical Significance' (handled by pdf_loader.py).
#     """
#     # Define separators to prioritize splitting on lines/paragraphs
#     # This prevents cutting a single test result (Test Name | Result | Unit) in half
#     separators = ["\n\n", "\n", " ", ""]

#     splitter = RecursiveCharacterTextSplitter(
#         chunk_size=1400,  # Keeps context manageable
#         chunk_overlap=250,  # Ensures we don't miss data at chunk boundaries
#         separators=separators,
#     )

#     chunks = splitter.split_text(text)
    
#     # Return Documents with metadata.
#     # This is required for the "Store with metadata" step in the pipeline.
#     return [
#         Document(
#             page_content=chunk, 
#             metadata={"chunk_type": "test_data"}  # Critical for downstream filtering
#         ) 
#         for chunk in chunks
#     ]
    
# # from langchain_text_splitters import RecursiveCharacterTextSplitter
# # from langchain_core.documents import Document

# # def split_text(text: str):
# #     """
# #     Split text into chunks for vector search.
# #     Using a balanced chunk size to improve retrieval precision.
# #     """
# #     splitter = RecursiveCharacterTextSplitter(
# #         chunk_size=1400,  # Balanced chunk size for precision and context
# #         chunk_overlap=250,  # Overlap to maintain context between chunks
# #     )

# #     chunks = splitter.split_text(text)
# #     return [Document(page_content=c) for c in chunks]

import json
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


def split_text(text: str, table_json: str = None):
    """
    Split text and structured table data into Documents for vectorstore.
    
    CRITICAL: table_json is structured JSON from extract_tables(), NOT raw text.
    Each lab test becomes its own Document with metadata for filtering.
    
    Args:
        text: Raw narrative text from PDF (clinical notes, etc.)
        table_json: JSON string of structured table data [{"test": ..., "value": ..., ...}]
    
    Returns:
        List of Document objects with proper metadata
    """
    docs = []
    
    # ================================================================
    # PART 1: Process raw narrative text (clinical notes, etc.)
    # ================================================================
    if text and len(text.strip()) > 50:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=150,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        chunks = splitter.split_text(text)
        for chunk in chunks:
            docs.append(Document(
                page_content=chunk.strip(),
                metadata={"chunk_type": "clinical_text"}
            ))
    
    # ================================================================
    # PART 2: Process structured lab data - ONE DOCUMENT PER TEST
    # ================================================================
    if table_json:
        try:
            table_rows = json.loads(table_json)
            
            if isinstance(table_rows, list):
                for row in table_rows:
                    test_name = row.get("test", "").strip()
                    value = row.get("value", "").strip()
                    unit = row.get("unit", "").strip()
                    ref_range = row.get("range", "").strip()
                    flag = row.get("flag", "").strip().upper()
                    
                    if not test_name or not value:
                        continue
                    
                    # Build readable content for embedding
                    # Format: "Haemoglobin: 9.1 gm/dl (Reference: 13.0-17.0) - LOW"
                    content_parts = [f"{test_name}: {value}"]
                    if unit:
                        content_parts[0] += f" {unit}"
                    if ref_range:
                        content_parts[0] += f" (Reference: {ref_range})"
                    if flag in ["HIGH", "LOW"]:
                        flag_label = "High" if flag == "HIGH" else "Low"
                        content_parts[0] += f" - Abnormal ({flag_label})"
                    
                    docs.append(Document(
                        page_content=content_parts[0],
                        metadata={
                            "chunk_type": "lab_test",
                            "test_name": test_name.lower(),
                            "value": value,
                            "unit": unit,
                            "range": ref_range,
                            "flag": flag  # "HIGH", "LOW", or ""
                        }
                    ))
                    
        except json.JSONDecodeError as e:
            print(f"⚠️ Failed to parse table JSON in split_text: {e}")
            # Fallback: if it's not valid JSON, treat as raw text
            if table_json and len(table_json.strip()) > 50:
                docs.append(Document(
                    page_content=table_json[:2000],  # Truncate to avoid giant chunks
                    metadata={"chunk_type": "raw_table_text"}
                ))
    
    # ================================================================
    # FALLBACK: If nothing extracted, create placeholder
    # ================================================================
    if not docs:
        docs.append(Document(
            page_content="No structured content extracted from document.",
            metadata={"chunk_type": "empty"}
        ))
    
    print(f"📄 Created {len(docs)} documents: "
          f"{sum(1 for d in docs if d.metadata.get('chunk_type') == 'lab_test')} lab tests, "
          f"{sum(1 for d in docs if d.metadata.get('chunk_type') == 'clinical_text')} text chunks")
    
    return docs