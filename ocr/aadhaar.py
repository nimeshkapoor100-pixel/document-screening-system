from __future__ import annotations
import re

from ocr.common import extract_all_dates, DATE_PATTERN, LOOSE_DATE_PATTERN, _collapse_digit_gaps, _fmt_date, _sanitize_name, AADHAAR_REDACTED

AADHAAR_NUMBER_PATTERN = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
AADHAAR_YOB_PATTERN = re.compile(r"\b(?:YOB|Year of Birth)[:\s]*(\d{4})\b", re.IGNORECASE)

AADHAAR_NAME_SKIP = {
    "GOVERNMENT",
    "INDIA",
    "OF",
    "THE",
    "GOVT",
    "DOB",
    "DATE",
    "BIRTH",
    "YEAR",
    "YOB",
    "GENDER",
    "SEX",
    "MALE",
    "FEMALE",
}

def _extract_aadhaar(text: str) -> dict[str, str | None]:
    number_match = AADHAAR_NUMBER_PATTERN.search(text)
    aadhaar_number = None
    if number_match:
        digits = re.sub(r"\D", "", number_match.group(0))
        if len(digits) == 12:
            aadhaar_number = f"{digits[0:4]} {digits[4:8]} {digits[8:12]}"

    earliest, _latest = extract_all_dates(text)
    dob = _fmt_date(earliest)
    if not dob:
        yob = AADHAAR_YOB_PATTERN.search(text)
        if yob:
            dob = yob.group(1)

    upper = text.upper()
    gender = None
    if re.search(r"\bFEMALE\b", upper):
        gender = "Female"
    elif re.search(r"\bMALE\b", upper):
        gender = "Male"

    name = None
    lines = [line.strip() for line in text.split("\n")]
    dob_index = next(
        (
            index
            for index, line in enumerate(lines)
            if DATE_PATTERN.search(_collapse_digit_gaps(line))
            or LOOSE_DATE_PATTERN.search(_collapse_digit_gaps(line))
            or AADHAAR_YOB_PATTERN.search(line)
        ),
        None,
    )
    if dob_index:
        for prior in reversed(lines[:dob_index]):
            # Skip lines with too many numbers (like phone numbers)
            if sum(c.isdigit() for c in prior) >= 3:
                continue
            
            # Clean non-alphabetic characters
            cleaned = re.sub(r"[^A-Za-z ]", " ", prior)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            
            tokens = cleaned.split()
            if not tokens:
                continue
                
            if any(token.upper() in AADHAAR_NAME_SKIP for token in tokens):
                continue
                
            candidate = _sanitize_name(" ".join(tokens))
            if len(candidate) <= 3:
                continue
                
            # The closest valid text line above DOB is usually the English name
            name = candidate
            break

    return {
        "aadhaar_number": aadhaar_number,
        "name": name,
        "dob": dob,
        "gender": gender,
    }
