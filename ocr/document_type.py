import re

from ocr.aadhaar import AADHAAR_NUMBER_PATTERN
from ocr.driving_license import _extract_dl_number

def detect_document_type(text: str) -> str:
    blob = text.upper()
    compact = re.sub(r"\s+", "", blob)
    alpha_clean = re.sub(r"[^A-Z\s]", " ", blob)
    alpha_tokens = set(alpha_clean.split())

    # 1. Driving License check
    has_dl_keywords = (
        "DRIVING" in alpha_tokens or "LICENCE" in alpha_tokens or "LICENSE" in alpha_tokens or
        "DRIVING" in blob or "LICENCE" in blob or "LICENSE" in blob or
        "DL NO" in blob or "DL.NO" in blob or "D.L." in blob or "DLNO" in blob or
        bool(re.search(r"\bDR[IP]{1,2}V\w*", blob)) or
        ("VALIDITY" in blob and any(m in blob for m in ["NT", "TR", "NV", "TRANSPORT", "NON-TRANSPORT"])) or
        "DATE OF FIRST ISSUE" in blob or
        "SON/DAUGHTER" in blob or "SON / DAUGHTER" in blob or "HOLDER'S SIGNATURE" in blob or
        "AUTHORISATION TO DRIVE" in blob or "AUTHORIZATION TO DRIVE" in blob
    )
    dl_number = _extract_dl_number(text)
    if has_dl_keywords or dl_number:
        # Avoid false trigger if it's explicitly Aadhaar or Passport
        if not ("UNIQUE IDENTIFICATION" in blob or "AADHAAR" in blob or "PASSPORT" in blob or "P<" in compact):
            return "Driving_License"

    # 2. Aadhaar check
    has_aadhaar = "AADHAAR" in blob or "UNIQUE IDENTIFICATION" in blob
    has_gov_india = "GOVERNMENT OF INDIA" in blob
    has_dob_marker = bool(re.search(r"\bDOB\b", blob))
    has_aadhaar_number = bool(AADHAAR_NUMBER_PATTERN.search(text))
    has_aadhaar = has_aadhaar or (has_gov_india and (has_dob_marker or has_aadhaar_number))
    
    has_strict_aadhaar_number = bool(re.search(r"\b\d{4}\s\d{4}\s\d{4}\b", text))
    has_vid = "VID" in blob and bool(re.search(r"\d{4}\s?\d{4}\s?\d{4}\s?\d{4}", text))
    if has_aadhaar or has_strict_aadhaar_number or has_vid:
        return "Aadhaar"

    # If driving license wasn't matched above, check again
    if has_dl_keywords or dl_number:
        return "Driving_License"

    # 3. Specific Visa check (US Visa or international visas)
    has_visa_mrz = "V<" in compact or "VNUSA" in compact or bool(re.search(r"V<[A-Z]{3}", compact)) or bool(re.search(r"VN[A-Z0-9<]{8,}", compact))
    has_visa_keywords = ("UNITED STATES OF AMERICA" in blob or "ISSUING POST" in blob or 
                         "CONTROL NUMBER" in blob or "VISA TYPE" in blob or 
                         "PED-" in blob or "PETITION" in blob)
    
    if (has_visa_mrz or has_visa_keywords) and ("REPUBLIC OF INDIA" not in blob and "भारत गणराज्य" not in text):
        return "Visa"

    # 4. Passport check (Requires actual passport MRZ with chevrons OR explicit passport keywords)
    has_passport_mrz = "P<" in compact or bool(re.search(r"P<[A-Z]{3}", compact)) or bool(re.search(r"P<[A-Z0-9<]{10,}", compact))
    has_passport_keywords = ("PASSPORT" in blob or "पासपोर्ट" in text or 
                            "REPUBLIC OF INDIA" in blob or "REPUBLIC OF -INDIA" in blob or "भारत गणराज्य" in text or
                            "GIVEN NAME" in blob or "CODE / NATIONALITY" in blob or
                            ("SURNAME" in blob and "NATIONALITY" in blob))
    if has_passport_mrz or has_passport_keywords:
        return "Passport"

    if "VISA" in blob or has_visa_mrz:
        return "Visa"

    if "PERMIT" in blob:
        return "Permit"

    return "Unknown"
