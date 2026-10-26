import json
from pathlib import Path
from typing import Any

from ocr.common import _or_missing, NOT_DETECTED
from ocr.engine import extract_text
from ocr.document_type import detect_document_type
from ocr.aadhaar import _extract_aadhaar
from ocr.visa import _extract_visa
from ocr.driving_license import _extract_driving_license
from ocr.passport import _extract_passport
from ocr.permit import _extract_permit

__all__ = ["extract_document_info", "extract_text", "detect_document_type", "extract_fields_for_type"]

def extract_fields_for_type(document_type: str, text: str) -> dict[str, Any]:
    extractors = {
        "Aadhaar": _extract_aadhaar,
        "Visa": _extract_visa,
        "Driving_License": _extract_driving_license,
        "Passport": _extract_passport,
        "Permit": _extract_permit,
    }
    extractor = extractors.get(document_type)
    raw_fields = extractor(text) if extractor else {"note": "Unsupported or unknown document type"}
    # Handle passing through dicts or lists if present (e.g., confidence flags)
    return {key: (_or_missing(value) if isinstance(value, str) or value is None else value) for key, value in raw_fields.items()}

def extract_document_info(image_path: str | Path) -> str:
    """OCR an image and return document_type, fields, and raw_text as JSON."""
    source = Path(image_path)
    
    # Run the default (CLAHE) preprocessing and extraction
    text1 = extract_text(source, method="clahe") if source.is_file() else str(image_path)
    document_type1 = detect_document_type(text1)
    fields1 = extract_fields_for_type(document_type1, text1)
    
    # Score for method 1: Count non-empty, non-NOT_DETECTED fields (ignore confidence strings for scoring)
    score1 = sum(1 for k, v in fields1.items() if not k.endswith("_confidence") and v and v != NOT_DETECTED)
    
    if source.is_file():
        try:
            text2 = extract_text(source, method="adaptive_deskew")
            document_type2 = detect_document_type(text2)
            fields2 = extract_fields_for_type(document_type2, text2)
            score2 = sum(1 for k, v in fields2.items() if not k.endswith("_confidence") and v and v != NOT_DETECTED)
            
            if score2 > score1:
                text1 = text2
                document_type1 = document_type2
                fields1 = fields2
        except Exception:
            pass

    return json.dumps(
        {
            "document_type": document_type1,
            "fields": fields1,
            "raw_text": text1,
        },
        indent=2,
        ensure_ascii=False,
    )
