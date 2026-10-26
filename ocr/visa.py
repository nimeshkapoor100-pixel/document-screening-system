from __future__ import annotations
import re

from ocr.common import extract_all_dates, _fmt_date, NOT_DETECTED, VISA_NOT_DETECTED

VISA_MRZ_NAME_PATTERN = re.compile(r"V[<A-Z]([A-Z]{3})([A-Z0-9<]*?)<<([A-Z0-9<]+)")
VISA_MRZ_DATA_PATTERN = re.compile(
    r"([A-Z0-9<]{9})[\d<]?([A-Z<]{3})(\d{6})[\d<]?([MF<])(\d{6})"
)

VISA_TYPE_KEYWORDS = ("TOURIST", "BUSINESS", "MEDICAL", "STUDENT")

def _extract_visa_name(text: str) -> str | None:
    for line in text.split("\n"):
        if "<<" not in line:
            continue
        line_upper = line.upper()
        line_upper = re.sub(r"^V(?:<|TIND|[T<A-Z0-9]{3,4})", "", line_upper)
        cleaned = re.sub(r"\s+", " ", line_upper.replace("<", " ")).strip()
        if cleaned:
            return cleaned
    return None

def _extract_visa(text: str) -> dict[str, str | None]:
    upper = text.upper()
    compact = re.sub(r"\s+", "", upper)

    # 1. Visa Number
    visa_number = None
    # Red foil number: 1 letter + 7 or 8 digits e.g. C6149107, U4809419
    foil_match = re.search(r"\b([A-Z]\d{7,8})\b", text)
    if foil_match:
        visa_number = foil_match.group(1)
    if not visa_number:
        # MRZ line 2 start (e.g. H8150402<91ND... or Y9036838<7IND...)
        mrz_v = re.search(r"\b([A-Z0-9<]{8,10})<", text)
        if mrz_v:
            visa_number = mrz_v.group(1).replace("<", "")
    if not visa_number:
        # Control number fallback
        ctrl = re.search(r"Control\s*Number\s*[:\-\/\n]?\s*(\d+)", text, re.I)
        if ctrl:
            visa_number = ctrl.group(1)

    # 2. Name
    name = None
    name_match = VISA_MRZ_NAME_PATTERN.search(compact)
    if name_match:
        surname = name_match.group(2).replace("<", " ").strip()
        given = name_match.group(3).split("<<")[0].replace("<", " ").strip()
        given = re.sub(r"[0-9].*$", "", given).strip()
        if given and surname:
            name = f"{given.title()} {surname.title()}".strip()
        elif given or surname:
            name = (given or surname).title().strip()

    if not name:
        surname = ""
        given = ""
        m_sur = re.search(r"Surname\s*[:\-\/\n]?\s*([A-Za-z\s]+)", text, re.I)
        if m_sur:
            surname = m_sur.group(1).strip().split("\n")[0].strip()
        m_giv = re.search(r"Given\s*(?:Name|Narne|Names?)\s*[:\-\/\n]?\s*([A-Za-z\s]+)", text, re.I)
        if m_giv:
            raw_giv = m_giv.group(1).strip().split("\n")[0].strip()
            given = re.sub(r"\s*(?:Visa\s*Type|Class|\./).*$", "", raw_giv, flags=re.I).strip()

        if given and surname:
            if given.upper() == "FNU":
                name = surname.title()
            else:
                name = f"{given.title()} {surname.title()}".strip()
        elif given or surname:
            name = (given or surname).title().strip()

    # 3. Dates
    issue_date = None
    expiry = None

    m_iss = re.search(r"Issue\s*Date\s*[:\-\/\n]?\s*([0-9A-Za-z\s\/\.\-]+)", text, re.I)
    if m_iss:
        d_iss, _ = extract_all_dates(m_iss.group(1))
        if d_iss:
            issue_date = _fmt_date(d_iss)

    m_exp = re.search(r"(?:Expir(?:y|ation)\s*Date|PED)\s*[:\-\/\n]?\s*([0-9A-Za-z\s\/\.\-]+)", text, re.I)
    if m_exp:
        _, d_exp = extract_all_dates(m_exp.group(1))
        if d_exp:
            expiry = _fmt_date(d_exp)

    # MRZ dates fallback
    mrz_data = re.search(r"([A-Z0-9<]{9})[\d<]?\s*([A-Z0-9<]{3})\s*(\d{6})[\d<]?\s*([MF<])\s*(\d{6})", compact)
    if mrz_data and not expiry:
        yymmdd_exp = mrz_data.group(5)
        yy, mm, dd = int(yymmdd_exp[:2]), int(yymmdd_exp[2:4]), int(yymmdd_exp[4:6])
        expiry = f"{dd:02d}-{mm:02d}-{2000 + yy}"

    earliest, latest = extract_all_dates(text)
    if not expiry and latest:
        expiry = _fmt_date(latest)
    if not issue_date and earliest and earliest != latest:
        # Check if earliest is birth date
        m_birth = re.search(r"Birth\s*Date\s*[:\-\/\n]?\s*([0-9A-Za-z\s\/\.\-]+)", text, re.I)
        if m_birth:
            d_birth, _ = extract_all_dates(m_birth.group(1))
            if d_birth == earliest:
                # Issue date should not be birth date
                pass
            else:
                issue_date = _fmt_date(earliest)
        else:
            issue_date = _fmt_date(earliest)

    # 4. Gender
    gender = None
    m_sex = re.search(r"(?:Sex|लिंग)\s*[:\-\/\n]*\s*([MF]|Male|Female)\b", text, re.I)
    if m_sex:
        val = m_sex.group(1).upper()
        gender = "Male" if val.startswith("M") else "Female"
    elif mrz_data:
        g_char = mrz_data.group(4)
        if g_char == "M":
            gender = "Male"
        elif g_char == "F":
            gender = "Female"

    # 5. Visa Type
    visa_type = None
    vtype_match = re.search(r"(?:Visa\s*Type\s*(?:\/Class)?|Class)\s*[:\-\/\n]?\s*([A-Za-z0-9\/\.\-\s]+)", text, re.I)
    if vtype_match:
        vt_raw = vtype_match.group(1).split("\n")[0].upper()
        if "B" in vt_raw and ("1" in vt_raw or "I" in vt_raw or "L" in vt_raw) and "2" in vt_raw:
            visa_type = "B1/B2"
        elif "L2" in vt_raw:
            visa_type = "L2"
        elif "L1" in vt_raw:
            visa_type = "L1"
        elif "H1" in vt_raw:
            visa_type = "H1B"
        else:
            m_code = re.search(r"\b(B1\/B2|B1|B2|L1|L2|H1B|F1|J1|TOURIST|BUSINESS)\b", vt_raw)
            if m_code:
                visa_type = m_code.group(1)

    if not visa_type:
        for kw in ("B1/B2", "B1", "B2", "L2", "L1", "H1B", "TOURIST", "BUSINESS", "MEDICAL", "STUDENT"):
            if kw in upper:
                visa_type = kw.title()
                break

    # 6. Entry Validation
    entry_validation = None
    m_ent = re.search(r"Entries\s*[:\-\/\n]*\s*([MS\d]|MULTIPLE|SINGLE)", text, re.I)
    if m_ent:
        val = m_ent.group(1).upper()
        if val in ("M", "MULTIPLE"):
            entry_validation = "Multiple"
        elif val in ("S", "1", "SINGLE"):
            entry_validation = "Single"
    if not entry_validation:
        for kw in ("MULTIPLE ENTRY", "SINGLE ENTRY", "DOUBLE ENTRY"):
            if kw in upper:
                entry_validation = kw.title()
                break
    if not entry_validation:
        entry_validation = "Multiple"

    # 7. Stay Duration
    stay_duration = "As per I-94 / Valid"
    m_dur = re.search(r"(\d+)\s*(DAYS|MONTHS|YEARS)", upper)
    if m_dur and ("DURATION" in upper or "STAY" in upper):
        stay_duration = f"{m_dur.group(1)} {m_dur.group(2).title()}"

    return {
        "visa_number": visa_number or VISA_NOT_DETECTED,
        "name": name or NOT_DETECTED,
        "issue_date": issue_date or NOT_DETECTED,
        "expiry": expiry or NOT_DETECTED,
        "gender": gender or VISA_NOT_DETECTED,
        "visa_type": visa_type or "Tourist / Business",
        "entry_validation": entry_validation,
        "stay_duration": stay_duration,
    }
