from __future__ import annotations
import re
from datetime import datetime

from ocr.common import extract_all_dates, _collapse_digit_gaps, _fmt_date, _parse_date, DATE_PATTERN, _sanitize_name, _recover_fused_date

DL_CANDIDATE_PATTERN = re.compile(r"(?=([A-Za-z0-9\)\]\}](?:[ \t\-\)\]\}]*[A-Za-z0-9\)\]\}]){13,15}))")
DIGIT_TO_LETTER = str.maketrans({"6": "G", "0": "O", "1": "I", "8": "B"})
LETTER_TO_DIGIT = str.maketrans(
    {"O": "0", "I": "1", "S": "5", "Z": "2", "L": "1", "}": "3", "B": "8", "G": "6"}
)
DL_NAME_BLOCKLIST = {
    "UNION", "INDIA", "STATE", "LICENCE", "LICENSE", "MOTOR", "TRANSPORT",
    "DOI", "MCWG", "LMV", "TRANS", "DOB", "DRIVING", "INDIAN",
    "COV", "VALID", "VALIDITY", "FROM", "TILL", "NAME", "NANE", "AUTHORISATION", "AUTHORIZATION",
    "DRIVE", "CLASS", "VEHICLES", "THROUGHOUT", "RULES", "FORM", "DUPLICATE",
    "HOLDER", "SIGN", "LICENCING", "AUTHORITY", "ADDRESS", "(NT)", "(TR)",
    "NAGAR", "ROAD", "STREET", "MARG", "CHOWK", "SOCIETY", "COLONY",
    "APARTMENT", "VILLAGE", "TALUKA", "DISTRICT", "POST", "NEAR", "OPP",
    "PIN", "ADD", "S/O", "S/D/W", "W/O", "D/O", "FATHER", "HUSBAND",
    "ISSUED", "GOVERNMENT", "GUJARAT", "KERALA", "DEPARTMENT", "MINISTRY", "REPUBLIC",
    "DATE", "ISSUE", "FIRST", "BLOOD", "GROUP", "ORGAN", "DONOR", "SIGNATURE",
    "DATEOFBIRTH", "BLOODGROUP", "BY", "OF", "SLO", "CDOI"
}

def _repair_dl_number(candidate: str) -> str | None:
    symbol_fix = str.maketrans({")": "J", "]": "J", "}": "J"})
    cleaned = candidate.translate(symbol_fix)
    compact = re.sub(r"[^A-Za-z0-9]", "", cleaned).upper()
    if not 14 <= len(compact) <= 16:
        return None
    if len(compact) == 16:
        compact = compact[:15]
    if len(compact) != 15:
        return None
    state = "".join(ch.translate(DIGIT_TO_LETTER) if ch.isdigit() else ch for ch in compact[:2])
    if not state.isalpha():
        return None
    rest = re.sub(r"[^0-9]", "", compact[2:15].translate(LETTER_TO_DIGIT))
    if len(rest) != 13:
        return None
    return f"{state}{rest[:2]} {rest[2:]}"

def _extract_dl_number(text: str) -> str | None:
    best: tuple[int, str] | None = None
    for match in DL_CANDIDATE_PATTERN.finditer(text):
        candidate = match.group(1)
        repaired = _repair_dl_number(candidate)
        if not repaired:
            continue
        original = re.sub(r"[^A-Za-z0-9]", "", candidate).upper()
        score = sum(a == b for a, b in zip(original[:15].ljust(15), repaired.replace(" ", "")))
        if best is None or score > best[0]:
            best = (score, repaired)
    return best[1] if best else None

def _is_address_block_marker(line: str) -> bool:
    if "," in line:
        return True
    upper = line.upper()
    return any(marker in upper for marker in ("S/O", "S/D/W", "W/O", "D/O", "SLO"))

def _looks_like_address_line(line: str) -> bool:
    if _is_address_block_marker(line):
        return True
    if len(re.findall(r"\d", line)) >= 2:
        return True
    return "ADD" in line.upper() or "PIN" in line.upper()

def _extract_dl_name(text: str) -> str | None:
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # Method 1: Look for Name label
    for i, line in enumerate(lines):
        upper_line = line.upper()
        if re.search(r"\b(NA[MN]E|NANE|MAME|NOME)\b", upper_line) and "AUTHORITY" not in upper_line:
            after_label = re.sub(r"^.*?(?:NA[MN]E|NANE|MAME|NOME)\s*[:\-]*\s*", "", upper_line).strip()
            tokens = [_sanitize_name(t) for t in after_label.split() if len(t) >= 2]
            valid = [t for t in tokens if t not in DL_NAME_BLOCKLIST and not re.search(r"\d", t)]
            if valid: return " ".join(valid)
            
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if _looks_like_address_line(next_line):
                    continue
                tokens = [_sanitize_name(t) for t in next_line.upper().split() if len(t) >= 2]
                valid = [t for t in tokens if t not in DL_NAME_BLOCKLIST and not re.search(r"\d", t)]
                if valid: return " ".join(valid)

    # Method 2: Look for the line immediately preceding Date of Birth
    for i, line in enumerate(lines):
        upper_line = line.upper()
        upper_clean = upper_line.replace(".", "").replace(" ", "")
        if "BIRTH" in upper_line or "DOB" in upper_clean:
            if i > 0:
                prev_line = lines[i - 1]
                if DATE_PATTERN.search(_collapse_digit_gaps(prev_line)):
                    continue
                if _is_address_block_marker(prev_line):
                    if i > 1:
                        prev_line = lines[i - 2]
                    else:
                        continue
                
                tokens = []
                for t in prev_line.upper().split():
                    clean_t = re.sub(r"[:\-]+$", "", t)
                    tokens.append(_sanitize_name(clean_t))
                
                valid = [t for t in tokens if t not in DL_NAME_BLOCKLIST and not re.search(r"\d", t) and len(re.sub(r"[^A-Z]", "", t)) > 0]
                if valid:
                    name_str = " ".join(valid)
                    return re.sub(r"^[^A-Z]+", "", name_str).strip()

    # Method 4: 4th fallback method (Upper half of doc, 2-4 ALL-CAPS words, no digits)
    upper_half_lines = lines[:max(1, len(lines) // 2)]
    for line in upper_half_lines:
        if _is_address_block_marker(line):
            break
        if _looks_like_address_line(line):
            continue
        
        if line == line.upper() and not re.search(r"\d", line):
            words = line.split()
            valid = [t for t in words if t not in DL_NAME_BLOCKLIST and len(t) > 1]
            if 2 <= len(valid) <= 4:
                return " ".join(valid)

    # Method 3: Fallback heuristic
    best: list[str] = []
    for line in lines:
        if _is_address_block_marker(line):
            break
        if _looks_like_address_line(line):
            continue

        tokens = [_sanitize_name(t) for t in line.upper().split()]
        valid = [t for t in tokens if len(t) >= 3 and t not in DL_NAME_BLOCKLIST and not re.search(r"\d", t)]
        if len(valid) > len(best):
            best = valid
            
    if best:
        return " ".join(best)
    return None

def _extract_dl_dates(text: str) -> tuple[str | None, str | None]:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    dob = None
    expiry = None
    
    for i, line in enumerate(lines):
        upper = line.upper()
        upper_clean = upper.replace(".", "").replace(" ", "")
        if "BIRTH" in upper or "DOB" in upper_clean:
            for j in range(i, min(i + 3, len(lines))):
                matches = DATE_PATTERN.findall(lines[j])
                if not matches:
                    matches = DATE_PATTERN.findall(_collapse_digit_gaps(lines[j]))
                found = False
                for m in matches:
                    dt = _parse_date(m)
                    if dt:
                        dob = dt
                        found = True
                        break
                if found:
                    break
                # Try fused date recovery if no standard date found
                for token in lines[j].split():
                    recovered = _recover_fused_date(token, "dob")
                    if recovered:
                        dob = recovered
                        break
                if dob:
                    break
                    
        if "VALID" in upper or "EXPIRY" in upper or "TILL" in upper or "TR" in upper or "NT" in upper:
            for j in range(i, min(i + 4, len(lines))):
                matches = DATE_PATTERN.findall(lines[j])
                if not matches:
                    matches = DATE_PATTERN.findall(_collapse_digit_gaps(lines[j]))
                for m in matches:
                    dt = _parse_date(m)
                    if dt and (not expiry or dt > expiry):
                        expiry = dt
                if not matches:
                    for token in lines[j].split():
                        recovered = _recover_fused_date(token, "expiry")
                        if recovered:
                            if not expiry or recovered > expiry:
                                expiry = recovered

    all_earliest, all_latest = extract_all_dates(text)
    if not dob:
        dob = all_earliest
    
    if not expiry or (dob and expiry <= dob):
        if all_latest and dob and all_latest > dob:
            expiry = all_latest
            
    if dob and expiry and dob > expiry:
        dob, expiry = expiry, dob
        
    now = datetime.now()
    if dob and dob > now:
        if all_earliest and all_earliest <= now:
            dob = all_earliest
        else:
            dob = None
            
    if expiry and expiry <= now and all_latest and all_latest > expiry:
        expiry = all_latest
        
    return _fmt_date(dob), _fmt_date(expiry)

def _extract_driving_license(text: str) -> dict[str, str | None]:
    dob, expiry = _extract_dl_dates(text)
    name = _extract_dl_name(text)
    
    return {
        "license_number": _extract_dl_number(text),
        "name": name,
        "dob": dob,
        "expiry": expiry,
    }
