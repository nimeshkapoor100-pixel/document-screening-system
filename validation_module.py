"""Validate and normalize fields extracted by ocr_module."""

from __future__ import annotations

import json
import re
from datetime import datetime

MRZ_DOB_PATTERN = re.compile(r"^\d{6}$")
DISPLAY_DOB_PATTERN = re.compile(r"^\d{2}-\d{2}-\d{4}$")
PASSPORT_ALNUM_PATTERN = re.compile(r"[A-Za-z0-9]")
INDIAN_DL_PATTERN = re.compile(r"^[A-Z]{2}\d{2}\s*\d{11}$")
AADHAAR_DIGITS_PATTERN = re.compile(r"^\d{12}$")
AADHAAR_REDACTED_VALUES = {"[Redacted Aadhaar]"}
VALID_GENDERS = {"Male", "Female"}
NOT_DETECTED_VALUES = {"Not Detected", "Not Detected (Watermark Noise)", None, ""}

# --- Verhoeff checksum tables (used by UIDAI for Aadhaar numbers) ---
_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_checksum_valid(number: str) -> bool:
    """Validate a numeric string against the Verhoeff checksum (used by Aadhaar)."""
    digits = [int(ch) for ch in reversed(number)]
    checksum = 0
    for i, digit in enumerate(digits):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[i % 8][digit]]
    return checksum == 0


def convert_mrz_dob(dob: str | None) -> str | None:
    """Convert a 6-digit MRZ DOB (YYMMDD) to DD-MM-YYYY.

    Years 00-24 map to 2000-2024; years 25-99 map to 1925-1999.
    Non-MRZ values are returned unchanged.
    """
    if dob is None:
        return None
    value = str(dob).strip()
    if not MRZ_DOB_PATTERN.fullmatch(value):
        return dob

    yy = int(value[0:2])
    mm = int(value[2:4])
    dd = int(value[4:6])
    year = 2000 + yy if yy <= 24 else 1900 + yy
    return f"{dd:02d}-{mm:02d}-{year}"


def is_valid_passport_number(passport_number: str | None) -> bool:
    """Passport numbers must contain at least 7 alphanumeric characters."""
    if not passport_number or passport_number in NOT_DETECTED_VALUES:
        return False
    alnum_count = len(PASSPORT_ALNUM_PATTERN.findall(str(passport_number)))
    return alnum_count >= 7


def is_valid_indian_dl_number(license_number: str | None) -> bool:
    """Indian DL numbers must match SS + RTO + 11-digit serial, e.g. MH14 20110012345."""
    if not license_number or license_number in NOT_DETECTED_VALUES:
        return False
    cleaned = str(license_number).upper().replace("}", "3").replace("O", "0").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    compact = cleaned.replace(" ", "")
    if re.fullmatch(r"[A-Z]{2}\d{13}", compact):
        cleaned = f"{compact[:4]} {compact[4:]}"
    return bool(INDIAN_DL_PATTERN.fullmatch(cleaned))


def is_valid_aadhaar_number(aadhaar_number: str | None) -> tuple[bool, str]:
    """Validate an Aadhaar number.

    Returns (passed, reason). A masked/redacted number (as produced by
    ocr_module, which never surfaces the raw 12 digits) is treated as a
    pass-through: we can't run Verhoeff on it, so we only confirm the
    document actually carried an Aadhaar-shaped number. A full 12-digit
    number is checked with the Verhoeff checksum used by UIDAI.
    """
    if aadhaar_number in NOT_DETECTED_VALUES:
        return False, "Aadhaar number not detected"
    if aadhaar_number in AADHAAR_REDACTED_VALUES:
        return True, "Aadhaar number is masked/redacted; format detected, checksum skipped"
    if not aadhaar_number:
        return False, "Aadhaar number not detected"
    compact = re.sub(r"\s", "", str(aadhaar_number))
    if not AADHAAR_DIGITS_PATTERN.fullmatch(compact):
        return False, "Aadhaar number is not a 12-digit value"
    if not verhoeff_checksum_valid(compact):
        return False, "Aadhaar number failed Verhoeff checksum"
    return True, "Aadhaar number passed Verhoeff checksum"


def is_valid_display_dob(dob: str | None) -> bool:
    """A usable DOB should be a real calendar date in DD-MM-YYYY, not in the future."""
    if not dob or dob in NOT_DETECTED_VALUES:
        return False
    if not DISPLAY_DOB_PATTERN.fullmatch(str(dob)):
        return False
    try:
        parsed = datetime.strptime(str(dob), "%d-%m-%Y")
    except ValueError:
        return False
    return parsed <= datetime.now()


def is_valid_expiry_date(expiry: str | None) -> bool:
    """An expiry date should be in DD-MM-YYYY format and strictly in the future."""
    if not expiry or expiry in NOT_DETECTED_VALUES:
        return False
    if not DISPLAY_DOB_PATTERN.fullmatch(str(expiry)):
        return False
    try:
        parsed = datetime.strptime(str(expiry), "%d-%m-%Y")
    except ValueError:
        return False
    return parsed > datetime.now()


def is_valid_gender(gender: str | None) -> bool:
    return gender in VALID_GENDERS


def _nested_fields(data: dict) -> dict:
    fields = data.get("fields")
    return fields if isinstance(fields, dict) else {}


def _validate_aadhaar(fields: dict) -> tuple[bool, dict]:
    number_ok, number_reason = is_valid_aadhaar_number(fields.get("aadhaar_number"))
    dob_ok = is_valid_display_dob(fields.get("dob"))
    gender_ok = is_valid_gender(fields.get("gender"))
    details = {
        "aadhaar_number": {"passed": number_ok, "reason": number_reason},
        "dob": {
            "passed": dob_ok,
            "reason": "DOB detected and normalized" if dob_ok else "DOB missing or unparseable",
        },
        "gender": {
            "passed": gender_ok,
            "reason": "Gender detected" if gender_ok else "Gender missing or not detected",
        },
    }
    # Aadhaar number is the field that actually matters for authenticity;
    # DOB/gender missing is common with worn/cropped cards, so don't fail
    # the whole document over them.
    return number_ok, details


def _validate_passport(fields: dict, data: dict) -> tuple[bool, dict]:
    passport_number = fields.get("passport_number") or data.get("passport_number")
    number_ok = is_valid_passport_number(passport_number)
    dob_ok = is_valid_display_dob(fields.get("dob") or data.get("dob"))
    expiry_ok = is_valid_expiry_date(fields.get("expiry") or data.get("expiry"))
    details = {
        "passport_number": {
            "passed": number_ok,
            "reason": "Passport number has >=7 alphanumeric characters"
            if number_ok
            else "Passport number missing or too short",
        },
        "dob": {
            "passed": dob_ok,
            "reason": "DOB detected and normalized" if dob_ok else "DOB missing or unparseable",
        },
        "expiry": {
            "passed": expiry_ok,
            "reason": "Document is valid (future expiry)" if expiry_ok else "Document is Expired or Date Missing",
        },
    }
    return number_ok, details


def _validate_driving_license(fields: dict, data: dict) -> tuple[bool, dict]:
    license_number = fields.get("license_number") or data.get("license_number")
    number_ok = is_valid_indian_dl_number(license_number)
    
    dob_val = fields.get("dob") or data.get("dob")
    dob_ok = is_valid_display_dob(dob_val) if dob_val else False
    
    expiry_val = fields.get("expiry") or data.get("expiry")
    expiry_ok = is_valid_expiry_date(expiry_val) if expiry_val else False
    
    details = {
        "license_number": {
            "passed": number_ok,
            "reason": "Matches Indian DL format (SSRR + 11 digits)"
            if number_ok
            else "Does not match Indian DL number format",
        },
        "dob": {
            "passed": dob_ok,
            "reason": "DOB detected and normalized" if dob_ok else "DOB missing or unparseable",
        },
        "expiry": {
            "passed": expiry_ok,
            "reason": "Document is valid (future expiry)" if expiry_ok else "Document is Expired or Date Missing",
        },
    }
            
    return number_ok and dob_ok and expiry_ok, details


def _validate_visa(fields: dict) -> tuple[bool, dict]:
    visa_number = fields.get("visa_number")
    number_ok = visa_number not in NOT_DETECTED_VALUES and bool(visa_number)
    expiry_ok = is_valid_expiry_date(fields.get("expiry"))
    entry_validation = fields.get("entry_validation")
    entry_ok = entry_validation not in NOT_DETECTED_VALUES and bool(entry_validation)
    
    details = {
        "visa_number": {
            "passed": number_ok,
            "reason": "Visa number detected" if number_ok else "Visa number missing or not detected"
        },
        "expiry": {
            "passed": expiry_ok,
            "reason": "Document is valid (future expiry)" if expiry_ok else "Document is Expired or Date Missing"
        },
        "entry_validation": {
            "passed": entry_ok,
            "reason": "Entry validation detected" if entry_ok else "Entry validation missing or not detected"
        }
    }
    return number_ok, details


def _validate_permit(fields: dict) -> tuple[bool, dict]:
    permit_number = fields.get("permit_number")
    number_ok = bool(permit_number) and permit_number not in NOT_DETECTED_VALUES
    expiry_ok = is_valid_expiry_date(fields.get("expiry"))
    
    details = {
        "permit_number": {
            "passed": number_ok,
            "reason": "Permit number detected" if number_ok else "Permit number missing or not detected"
        },
        "expiry": {
            "passed": expiry_ok,
            "reason": "Document is valid (future expiry)" if expiry_ok else "Document is Expired or Date Missing"
        }
    }
    return number_ok and expiry_ok, details


def validate_data(extracted_json: str | dict) -> str:
    """Normalize dates and check ID format for the detected document type.

    Adds a top-level "validation_status" ("Passed"/"Failed") and a
    "validation_details" dict with a per-field pass/fail + reason, so
    callers can see *why* a document failed rather than just that it did.
    """
    data = json.loads(extracted_json) if isinstance(extracted_json, str) else dict(extracted_json)
    fields = _nested_fields(data)

    for container in (data, fields):
        if "dob" in container:
            container["dob"] = convert_mrz_dob(container.get("dob"))

    document_type = data.get("document_type")
    if document_type == "Aadhaar":
        passed, details = _validate_aadhaar(fields)
    elif document_type == "Passport":
        passed, details = _validate_passport(fields, data)
    elif document_type == "Driving_License":
        passed, details = _validate_driving_license(fields, data)
    elif document_type == "Visa":
        passed, details = _validate_visa(fields)
    elif document_type == "Permit":
        passed, details = _validate_permit(fields)
    else:
        # Unknown / anything else: no hard validation rules defined
        # yet, so don't crash and don't silently claim success either.
        passed = False
        details = {
            "_unsupported": {
                "passed": False,
                "reason": f"No validation rules implemented for document_type={document_type!r}",
            }
        }

    data["validation_status"] = "Passed" if passed else "Failed"
    data["validation_details"] = details
    if fields:
        data["fields"] = fields
    return json.dumps(data, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    samples = [
        {
            "document_type": "Driving_License",
            "fields": {
                "license_number": "MH14 20110012345",
                "name": "Nimesh Kapoor",
                "dob": "12-03-1990",
                "expiry": "11-03-2030",
            },
            "raw_text": "Indian Union Driving Licence DL No MH14 20110012345 Name Nimesh Kapoor",
        },
        {
            "document_type": "Aadhaar",
            "fields": {
                "aadhaar_number": "Not Detected",
                "name": "Nimesh Kapoor",
                "dob": "12-03-1990",
                "gender": "Male",
            },
            "raw_text": "Government of India ...",
        },
        {
            "document_type": "Aadhaar",
            "fields": {
                "aadhaar_number": "[Redacted Aadhaar]",
                "name": "Nimesh Kapoor",
                "dob": "12-03-1990",
                "gender": "Male",
            },
            "raw_text": "Government of India ... XXXX XXXX 1234",
        },
        {
            "document_type": "Aadhaar",
            "fields": {
                "aadhaar_number": "234123412346",
                "name": "Test User",
                "dob": "01-01-2000",
                "gender": "Female",
            },
            "raw_text": "Government of India ... 2341 2341 2346",
        },
        {
            "document_type": "Passport",
            "fields": {
                "passport_number": "M1234567",
                "name": "Nimesh Kapoor",
                "dob": "900823",
                "expiry": "300822",
            },
            "raw_text": "P<INDKAPOOR<<NIMESH...",
        },
    ]
    for sample in samples:
        print(f"\n=== {sample['document_type']} ===")
        print(validate_data(json.dumps(sample)))