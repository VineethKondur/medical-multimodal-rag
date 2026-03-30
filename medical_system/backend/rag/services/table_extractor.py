import gc
import camelot


def is_valid_lab_table(df):
    """
    Check if the table looks like a lab report table.
    Filters out metadata tables (patient info, hospital info, etc.)
    """
    try:
        text = " ".join(df.astype(str).values.flatten()).lower()

        keywords = [
            "hemoglobin", "wbc", "rbc", "platelet",
            "test", "value", "range", "result"
        ]

        return any(k in text for k in keywords)

    except Exception:
        return False


def get_headers(df):
    """
    Try to detect the correct header row dynamically.
    Searches first 5 rows for keywords indicating a header row.
    """
    header_keywords = ["test", "value", "range", "result", "unit", "name", "parameter"]
    
    for i in range(min(5, len(df))):
        row = [str(x).lower().strip() for x in df.iloc[i]]
        row_text = " ".join(row)
        
        # Check if this row contains header keywords
        keyword_count = sum(1 for keyword in header_keywords if keyword in row_text)
        
        if keyword_count >= 2:  # At least 2 keywords found
            return df.iloc[i], i

    # If no header found, assume first row or infer from data
    if len(df) > 0:
        return df.iloc[0], 0
    
    return None, 0


import json

def format_table(df):
    """
    Format extracted table into structured rows.
    Detects columns dynamically and handles various formats.
    """
    rows = []

    try:
        headers, start_idx = get_headers(df)
        
        if headers is None:
            return ""
        
        headers = [str(h).lower().strip() for h in headers]

        # Find column indices with better matching
        test_idx = None
        value_idx = None
        unit_idx = None
        range_idx = None

        for i, h in enumerate(headers):
            h_lower = h.lower()
            if test_idx is None and any(x in h_lower for x in ["test", "parameter", "name", "analyte"]):
                test_idx = i
            elif value_idx is None and any(x in h_lower for x in ["result", "value", "result value"]):
                value_idx = i
            elif unit_idx is None and any(x in h_lower for x in ["unit"]):
                unit_idx = i
            elif range_idx is None and any(x in h_lower for x in ["range", "reference", "ref", "normal"]):
                range_idx = i

        # Fallback to positional if not found
        if test_idx is None:
            test_idx = 0
        if value_idx is None and len(headers) > 1:
            value_idx = 1
        if unit_idx is None and len(headers) > 2:
            unit_idx = 2
        if range_idx is None and len(headers) > 3:
            range_idx = 3

        # Extract data rows
        for i in range(start_idx + 1, len(df)):
            row = df.iloc[i]

            test = str(row[test_idx]).strip() if test_idx < len(row) else ""
            value = str(row[value_idx]).strip() if value_idx is not None and value_idx < len(row) else ""
            unit = str(row[unit_idx]).strip() if unit_idx is not None and unit_idx < len(row) else ""
            ref = str(row[range_idx]).strip() if range_idx is not None and range_idx < len(row) else ""

            # Skip empty or invalid rows
            if not test or not value:
                continue
            
            if test.lower() in ["nan", "-", "", "none"]:
                continue
            if value.lower() in ["nan", "-", "", "none"]:
                continue

            # Format as structured row
            rows.append(f"TABLE ROW → Test: {test}, Value: {value}, Unit: {unit}, Range: {ref}")

    except Exception as e:
        print(f"⚠️ Table formatting failed: {e}")
        return ""

    return "\n".join(rows)


def extract_tables(file_path: str) -> str:
    """
    Extract and clean tables from PDF.
    """

    table_text_parts = []

    try:
        # Try lattice first
        tables = camelot.read_pdf(
            file_path,
            pages="all",
            flavor="lattice",
            suppress_stdout=True
        )

        # Fallback to stream
        if tables.n == 0:
            tables = camelot.read_pdf(
                file_path,
                pages="all",
                flavor="stream",
                suppress_stdout=True
            )

        if tables.n == 0:
            return ""

        print(f"Tables extracted: {tables.n}")

        for table in tables:
            df = table.df

            # 🔥 FILTER ONLY LAB TABLES
            if not is_valid_lab_table(df):
                continue

            structured_table = format_table(df)

            if structured_table:
                table_text_parts.append(structured_table)

        # spacing
        table_text_parts.append("")

    except Exception as e:
        print(f"⚠️ Table extraction failed: {e}")
        return ""

    finally:
        # Fix Windows file lock issue
        gc.collect()

    return "\n".join(table_text_parts).strip()