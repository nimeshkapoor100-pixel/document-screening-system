"""Run OCR extraction and validation on an Aadhaar, Passport, or Driving
License image.

Usage:
    python main.py [path/to/image.jpg]

If no path is given, falls back to sample_docs/passport_sample.jpg.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ocr_module import extract_document_info
from validation_module import validate_data

DEFAULT_IMAGE = "sample_docs/passport_sample.jpg"


def run(image_path: str) -> str:
    """Extract + validate a document image. Returns pretty JSON either way."""
    path = Path(image_path)
    if not path.is_file():
        return json.dumps(
            {"error": f"Image not found: {path}", "validation_status": "Failed"},
            indent=2,
            ensure_ascii=False,
        )

    try:
        extracted_json = extract_document_info(path)
    except Exception as exc:  # noqa: BLE001 - surface any OCR failure as clean JSON
        return json.dumps(
            {
                "error": f"OCR extraction failed: {exc}",
                "validation_status": "Failed",
            },
            indent=2,
            ensure_ascii=False,
        )

    try:
        validated_json = validate_data(extracted_json)
    except Exception as exc:  # noqa: BLE001 - surface any validation failure as clean JSON
        return json.dumps(
            {
                "error": f"Validation failed: {exc}",
                "extracted": json.loads(extracted_json),
                "validation_status": "Failed",
            },
            indent=2,
            ensure_ascii=False,
        )

    return validated_json


def main() -> None:
    image_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IMAGE
    print(f"Processing: {image_path}")
    print(run(image_path))


if __name__ == "__main__":
    main()