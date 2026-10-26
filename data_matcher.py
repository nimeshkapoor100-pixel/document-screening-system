import logging
from thefuzz import fuzz

logger = logging.getLogger(__name__)

def match_demographics(ocr_data: dict, db_data: dict) -> float:
    """
    Compares the OCR-extracted data (Name, DOB, Address) with the central database data.
    Uses fuzzy matching for strings to account for OCR typos.
    Returns a text-match confidence score (0.0 to 1.0).
    """
    if not ocr_data or not db_data:
        return 0.0

    scores = []

    # 1. Name Match (Fuzzy)
    ocr_name = ocr_data.get('name', '').lower()
    db_name = db_data.get('name', '').lower()
    if ocr_name and db_name:
        name_score = fuzz.token_sort_ratio(ocr_name, db_name) / 100.0
        scores.append(name_score)
    else:
        scores.append(0.0)

    # 2. DOB Match (Exact)
    ocr_dob = ocr_data.get('dob')
    db_dob = db_data.get('dob')
    if ocr_dob and db_dob:
        if ocr_dob == db_dob:
            scores.append(1.0)
        else:
            scores.append(0.0)

    # 3. Address Match (Fuzzy)
    ocr_address = ocr_data.get('address', '').lower()
    db_address = db_data.get('address', '').lower()
    if ocr_address and db_address:
        addr_score = fuzz.token_set_ratio(ocr_address, db_address) / 100.0
        scores.append(addr_score)

    if not scores:
        return 0.0

    # Average the scores
    final_score = sum(scores) / len(scores)
    logger.info(f"Demographics match score: {final_score:.2f}")
    return final_score
