"""Extract structured fields from Indian Aadhaar, Passport, Visa, and Driving License images.
This file now acts as a backward-compatible shim. All logic has been moved to the `ocr` package.
"""

from ocr import extract_document_info, extract_text, detect_document_type, extract_fields_for_type
import json
from pathlib import Path

SAMPLE_IMAGE = Path(__file__).resolve().parent / "sample_docs" / "passport_sample.jpg"

def main() -> None:
    print(f"Reading: {SAMPLE_IMAGE}")
    try:
        print(extract_document_info(SAMPLE_IMAGE))
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))

if __name__ == "__main__":
    main()