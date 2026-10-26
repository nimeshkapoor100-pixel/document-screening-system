from __future__ import annotations
import re

from ocr.common import extract_all_dates, _fmt_date
# Will need _extract_dl_name from driving_license
from ocr.driving_license import _extract_dl_name

def _extract_permit(text: str) -> dict[str, str | None]:
    """Extract basic info from a generic Permit."""
    fields: dict[str, str | None] = {"name": None, "permit_number": None, "expiry": None}
    
    _, expiry = extract_all_dates(text)
    fields["expiry"] = _fmt_date(expiry)
    
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines:
        upper = line.upper()
        if "PERMIT" in upper and ("NO" in upper or "NUMBER" in upper):
            match = re.search(r"([A-Z0-9]{5,15})", upper.replace("PERMIT", "").replace("NO", "").replace("NUMBER", ""))
            if match:
                fields["permit_number"] = match.group(1)
                break
                
    if not fields["permit_number"]:
        match = re.search(r"\b([A-Z]{2,3}[-\s]?\d{4,8})\b", text.upper())
        if match:
            fields["permit_number"] = match.group(1).replace(" ", "").replace("-", "")
            
    fields["name"] = _extract_dl_name(text)[0] if isinstance(_extract_dl_name(text), tuple) else _extract_dl_name(text)
    
    return fields
