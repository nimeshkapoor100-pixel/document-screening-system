from __future__ import annotations
import re
from datetime import datetime

NOT_DETECTED = "Not Detected"
VISA_NOT_DETECTED = "Not Detected (Watermark Noise)"
AADHAAR_REDACTED = "[Redacted Aadhaar]"

MONTH_NAME_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
}

DATE_PATTERN = re.compile(r"\b\d{2}\s*[/.\-7]\s*\d{2}\s*[/.\-7]\s*\d{4}\b")
SPACED_DATE_PATTERN = re.compile(r"\b(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})\b")
ALPHA_MONTH_PATTERN = re.compile(r"\b(\d{1,2})[\s\-_/]?([A-Za-z]{3})[\s\-_/]?(\d{4})\b")
LOOSE_DATE_PATTERN = re.compile(r"\b(\d{2})[/.\-7](\d{2})[/.\-7](\d{4,6})\b")
_PLAUSIBLE_YEAR_MIN = 1930
_PLAUSIBLE_YEAR_MAX = 2060

def _clean_date_token(raw: str) -> str:
    cleaned = re.sub(r"\s+", "", raw)
    match = re.fullmatch(r"(\d{2})([/.\-7])(\d{2})([/.\-7])(\d{4})", cleaned)
    if not match:
        return cleaned.replace("-", "/").replace(".", "/")
    return f"{match.group(1)}/{match.group(3)}/{match.group(5)}"

def _parse_date(value: str) -> datetime | None:
    cleaned = _clean_date_token(value)
    try:
        return datetime.strptime(cleaned, "%d/%m/%Y")
    except ValueError:
        try:
            return datetime.strptime(cleaned, "%m/%d/%Y")
        except ValueError:
            return None

def _parse_date_loose(dd: str, mm: str, year_digits: str) -> datetime | None:
    windows: list[str] = []
    if len(year_digits) == 4:
        windows = [year_digits]
    else:
        windows.append(year_digits[-4:])
        windows.append(year_digits[:4])
        for i in range(len(year_digits) - 3):
            window = year_digits[i : i + 4]
            if window not in windows:
                windows.append(window)

    for yyyy in windows:
        if not (_PLAUSIBLE_YEAR_MIN <= int(yyyy) <= _PLAUSIBLE_YEAR_MAX):
            continue
        for fmt, value in ((f"{dd}/{mm}/{yyyy}", "%d/%m/%Y"), (f"{mm}/{dd}/{yyyy}", "%m/%d/%Y")):
            try:
                return datetime.strptime(fmt, value)
            except ValueError:
                continue
    return None

def _collapse_digit_gaps(text: str) -> str:
    return re.sub(r"(?<=\d)[ \t]+(?=\d)", "", text)

def extract_all_dates(text: str) -> tuple[datetime | None, datetime | None]:
    parsed: list[datetime] = []
    
    # 1. Check for alphanumeric month dates (e.g. 07DEC2010, 04-DEC-2010, 27 NOV 2023)
    for d_str, m_str, y_str in ALPHA_MONTH_PATTERN.findall(text):
        m_up = m_str.upper()
        if m_up in MONTH_NAME_MAP:
            try:
                y = int(y_str)
                m = MONTH_NAME_MAP[m_up]
                d = int(d_str)
                if _PLAUSIBLE_YEAR_MIN <= y <= _PLAUSIBLE_YEAR_MAX:
                    dt = datetime(y, m, d)
                    if dt not in parsed:
                        parsed.append(dt)
            except (ValueError, OverflowError):
                pass

    # 2. Check for dates with spaces around slashes/dashes (e.g. 27/01 /2023, 26/01 /2033)
    for d_str, m_str, y_str in SPACED_DATE_PATTERN.findall(text):
        try:
            d, m, y = int(d_str), int(m_str), int(y_str)
            if _PLAUSIBLE_YEAR_MIN <= y <= _PLAUSIBLE_YEAR_MAX:
                try:
                    dt = datetime(y, m, d)
                    if dt not in parsed:
                        parsed.append(dt)
                except ValueError:
                    dt = datetime(y, d, m)
                    if dt not in parsed:
                        parsed.append(dt)
        except (ValueError, OverflowError):
            pass

    # 3. Try original text with DATE_PATTERN
    for raw in DATE_PATTERN.findall(text):
        dt = _parse_date(raw)
        if dt and dt not in parsed:
            parsed.append(dt)
            
    # 4. Try collapsed text if we need more dates
    collapsed = _collapse_digit_gaps(text)
    for raw in DATE_PATTERN.findall(collapsed):
        dt = _parse_date(raw)
        if dt and dt not in parsed:
            parsed.append(dt)
            
    if not parsed:
        for dd, mm, year_digits in LOOSE_DATE_PATTERN.findall(collapsed):
            dt = _parse_date_loose(dd, mm, year_digits)
            if dt and dt not in parsed:
                parsed.append(dt)
    if not parsed:
        return None, None
    parsed.sort()
    return parsed[0], parsed[-1]

def _recover_fused_date(token: str, field_type: str = "dob") -> datetime | None:
    # 1. Strip trailing annotations
    token = re.sub(r"\([A-Z]+\)$", "", token.strip())
    
    # 2. Extract digits and their blob run lengths/indices
    digits_list = []
    blob_lengths = []
    blob_indices = []
    
    current_blob = ""
    for ch in token:
        if ch.isdigit():
            current_blob += ch
        else:
            if current_blob:
                for i in range(len(current_blob)):
                    digits_list.append(current_blob[i])
                    blob_lengths.append(len(current_blob))
                    blob_indices.append(i)
                current_blob = ""
    if current_blob:
        for i in range(len(current_blob)):
            digits_list.append(current_blob[i])
            blob_lengths.append(len(current_blob))
            blob_indices.append(i)
            
    digits = "".join(digits_list)
    if not (6 <= len(digits) <= 10):
        return None
        
    # 3. Try last 4 digits as year
    year_str = digits[-4:]
    if not year_str.isdigit():
        return None
    year = int(year_str)
    if not (_PLAUSIBLE_YEAR_MIN <= year <= _PLAUSIBLE_YEAR_MAX):
        return None
        
    # 4. Take remaining leading digits
    leading = digits[:-4]
    if not (3 <= len(leading) <= 6):
        return None
        
    valid_candidates = []
    
    if len(leading) == 4:
        dd, mm = int(leading[:2]), int(leading[2:])
        try:
            valid_candidates.append((datetime(year, mm, dd), 0, 0))
        except ValueError:
            pass
    elif len(leading) in (5, 6):
        import itertools
        drop_count = len(leading) - 4
        indices = list(range(len(leading)))
        for drop_indices in itertools.combinations(indices, drop_count):
            candidate_leading = "".join(ch for i, ch in enumerate(leading) if i not in drop_indices)
            dd, mm = int(candidate_leading[:2]), int(candidate_leading[2:])
            try:
                dt = datetime(year, mm, dd)
                # edge_dist based on blob position
                edge_dist = 0
                for i in drop_indices:
                    blen = blob_lengths[i]
                    bidx = blob_indices[i]
                    edge_dist += min(bidx, blen - 1 - bidx)
                valid_candidates.append((dt, drop_count, edge_dist))
            except ValueError:
                pass
                
    if not valid_candidates:
        return None
        
    now = datetime.now()
    def sort_key(item):
        dt, drop_count, edge_dist = item
        if field_type == "dob":
            time_diff = dt.timestamp()
        else:
            time_diff = abs((dt - now).total_seconds())
        return (drop_count, -edge_dist, time_diff)
        
    valid_candidates.sort(key=sort_key)
    return valid_candidates[0][0]

def _fmt_date(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%d-%m-%Y")

def _or_missing(value: str | None, missing: str = NOT_DETECTED) -> str:
    return value if value else missing

def _sanitize_name(text: str) -> str:
    correction_map = str.maketrans({"8": "B", "0": "O", "1": "I", "5": "S", "6": "G"})
    return text.translate(correction_map)
