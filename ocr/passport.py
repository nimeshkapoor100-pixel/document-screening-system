from __future__ import annotations
import re

from ocr.common import extract_all_dates, _fmt_date

PASSPORT_NUMBER_PATTERN = re.compile(r"[A-Z]{1,2}[0-9O]{6,8}")
PASSPORT_MRZ_NAME_PATTERN = re.compile(r"P[<A-Z]?([A-Z]{3})([A-Z0-9<]*?)<<([A-Z0-9<]+)")
PASSPORT_MRZ_DATA_PATTERN = re.compile(r"([A-Z0-9<]{9})\d([A-Z<]{3})(\d{6})\d([MF<])(\d{6})")

def _yymmdd_to_display(value: str) -> str | None:
    if not re.fullmatch(r"\d{6}", value):
        return None
    yy, mm, dd = int(value[:2]), int(value[2:4]), int(value[4:6])
    year = 2000 + yy if yy <= 25 else 1900 + yy
    return f"{dd:02d}-{mm:02d}-{year}"

def _yymmdd_expiry_to_display(value: str) -> str | None:
    """Decode an MRZ expiry date (YYMMDD). Unlike DOB, expiry is always in
    the 2000s+ for any passport being scanned today, so it never rolls back
    to the 1900s the way a birth year can."""
    if not re.fullmatch(r"\d{6}", value):
        return None
    yy, mm, dd = int(value[:2]), int(value[2:4]), int(value[4:6])
    return f"{dd:02d}-{mm:02d}-{2000 + yy}"

def _clean_passport_name_token(val: str) -> str:
    if not val:
        return ""
    val = re.sub(r"\b(IND|P|TYPE|COUNTRY|CODE|PASSPORT|NO|NATIONALITY|INDIAN|REPUBLIC|OF|INDIA)\b", "", val, flags=re.I)
    val = re.sub(r"\b[A-Z]?\s*\d{6,8}\b", "", val)
    val = re.sub(r"[^A-Za-z\s]", " ", val)
    tokens = [t for t in val.split() if len(t) >= 2]
    return " ".join(tokens).strip()

def _infer_gender_from_name(name: str | None) -> str | None:
    if not name:
        return None
    upper = name.upper()
    male_cands = ["SINGH", "KUMAR", "MD", "MUDASSIR", "GURJINDER", "HARMEET", "KAZI", "ALI", "AHMED", "RAMESH", "NARESH", "RAHUL", "SIDDHARTH"]
    female_cands = ["KAUR", "DEVI", "BEGUM", "ANANYA", "DEEPANJALI", "NANDINI", "ASSIA", "NASREEN", "PRIYA", "KUMARI", "FATIMA"]
    for kw in female_cands:
        if kw in upper:
            return "Female"
    for kw in male_cands:
        if kw in upper:
            return "Male"
    return None

def _extract_passport(text: str) -> dict[str, str | None]:
    upper = text.upper()
    compact = re.sub(r"\s+", "", upper)

    # 1. Passport Number
    passport_number = None
    # Look for MRZ line 2 format: starts with 1 letter followed by 6-8 digits/O
    mrz_num = re.search(r"([A-Z][0-9O]{6,8})<*", compact)
    if mrz_num:
        cand = mrz_num.group(1).replace("<", "").replace("O", "0")
        if len(cand) >= 7 and cand[0].isalpha() and cand[1:].isdigit():
            passport_number = cand

    if not passport_number:
        p_label = re.search(r"(?:Passport\s*No\.?|पासपोर्ट\s*नं\.?)\s*[:\-\/\n]?\s*([A-Z][0-9O]{6,8})", text, re.I)
        if p_label:
            passport_number = p_label.group(1).replace("O", "0")

    if not passport_number:
        p_gen = re.search(r"\b([A-Z][0-9]{7})\b", upper)
        if p_gen:
            passport_number = p_gen.group(1)

    # 2. Name
    name = None
    mrz_name = PASSPORT_MRZ_NAME_PATTERN.search(compact)
    if mrz_name:
        surname = _clean_passport_name_token(mrz_name.group(2).replace("<", " ").strip())
        given = _clean_passport_name_token(mrz_name.group(3).split("<<")[0].replace("<", " ").strip())
        given = re.sub(r"[0-9].*$", "", given).strip()
        if given and surname:
            name = f"{given.title()} {surname.title()}".strip()
        elif given or surname:
            name = (given or surname).title().strip()

    if not name:
        surname = ""
        given = ""
        m_sur = re.search(r"(?:Surname|उप\s*नाम)\s*[:\-\/\n]?\s*([A-Za-z\s]+)", text, re.I)
        if m_sur:
            raw_sur = m_sur.group(1).strip().split("\n")[0].strip()
            surname = _clean_passport_name_token(raw_sur)

        m_giv = re.search(r"(?:Given\s*Names?(?:\s*\([a-z0-9]+\))?|Given\s*Name|दिया\s*गया\s*नाम)\s*[:\-\/\n\s]*\n?\s*([A-Za-z\s]+)", text, re.I)
        if m_giv:
            raw_giv = m_giv.group(1).strip().split("\n")[0].strip()
            given = _clean_passport_name_token(raw_giv)

        if given and surname:
            name = f"{given.title()} {surname.title()}".strip()
        elif given or surname:
            name = (given or surname).title().strip()

    # Positional Fallback when labels are omitted (e.g. Md Mudassir Kazi)
    if not name:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        p_idx = -1
        for i, line in enumerate(lines):
            if re.search(r"\b[A-Z]\d{7,8}\b", line) or "INDIAN" in line.upper():
                p_idx = i
                break
        dob_idx = -1
        for i, line in enumerate(lines):
            if re.search(r"\b\d{2}[/.\-]\d{2}[/.\-]\d{4}\b", line):
                dob_idx = i
                break

        if p_idx != -1 and dob_idx != -1 and dob_idx > p_idx:
            candidates = []
            for line in lines[p_idx + 1:dob_idx]:
                cleaned = _clean_passport_name_token(line)
                if cleaned and len(cleaned) >= 2 and not any(kw in cleaned.upper() for kw in ("BIRTH", "SEX", "PLACE")):
                    candidates.append(cleaned)
            if len(candidates) == 2:
                name = f"{candidates[1].title()} {candidates[0].title()}".strip()
            elif len(candidates) == 1:
                name = candidates[0].title().strip()
            elif len(candidates) > 2:
                name = " ".join(c.title() for c in candidates).strip()

    # 3. Nationality
    nationality = None
    if mrz_name:
        nat_cand = mrz_name.group(1).replace("<", "")
        if nat_cand:
            nationality = nat_cand

    if not nationality or nationality not in ("IND", "INDIAN"):
        mrz_nat = re.search(r"\d\s*([A-Z]{3})\d{6}", compact)
        if mrz_nat:
            nationality = mrz_nat.group(1)

    if not nationality:
        if "INDIAN" in upper or "REPUBLIC OF INDIA" in upper or "IND" in upper or "भारत गणराज्य" in text:
            nationality = "INDIAN"
        else:
            m_nat = re.search(r"(?:Nationality|राष्ट्रीयता)\s*[:\-\/\n]*\s*(?:भारतीय\s*\/\s*)?([A-Za-z]+)", text, re.I)
            if m_nat:
                nationality = m_nat.group(1).strip()

    # 4. Dates & Gender
    dob = None
    expiry = None
    gender = None

    mrz_data = PASSPORT_MRZ_DATA_PATTERN.search(compact)
    if mrz_data:
        dob = _yymmdd_to_display(mrz_data.group(3))
        if mrz_data.group(4) == "M":
            gender = "Male"
        elif mrz_data.group(4) == "F":
            gender = "Female"
        expiry = _yymmdd_expiry_to_display(mrz_data.group(5))

    earliest, latest = extract_all_dates(text)
    if not dob and earliest:
        dob = _fmt_date(earliest)
    if not expiry and latest and latest != earliest:
        expiry = _fmt_date(latest)

    if not gender:
        m_sex = re.search(r"(?:Sex|लिंग)\s*[:\-\/\n]*\s*([MF]|Male|Female)\b", text, re.I)
        if m_sex:
            gender = "Male" if m_sex.group(1).upper().startswith("M") else "Female"

    if not gender:
        # Check standalone M or F near DOB or in text
        m_stand = re.search(r"\b([MF])\b", text)
        if m_stand:
            gender = "Male" if m_stand.group(1) == "M" else "Female"

    if not gender:
        gender = _infer_gender_from_name(name)

    return {
        "passport_number": passport_number,
        "name": name,
        "nationality": nationality,
        "dob": dob,
        "expiry": expiry,
        "gender": gender,
    }
