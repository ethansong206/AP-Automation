from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple

_SUPERSCRIPT_TRANS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def to_superscript(n: int) -> str:
    return str(n).translate(_SUPERSCRIPT_TRANS)


def _parse_date(text: str) -> Optional[datetime]:
    text = (text or "").strip()
    if not text:
        return None
    fmts = ["%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%m/%d/%y"]
    for f in fmts:
        try:
            return datetime.strptime(text, f)
        except ValueError:
            pass
    return None


def _parse_money(text: str) -> Optional[float]:
    if text is None:
        return None
    s = re.sub(r"[^\d\.\-]", "", str(text))
    if s in {"", "-", ".", "-.", ".-"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _natural_key(s: str) -> Tuple:
    """Case-insensitive natural sort key."""
    return tuple(int(t) if t.isdigit() else t.lower() for t in re.findall(r'\d+|\D+', s or ""))


def _normalize_invoice_number(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', (s or "").lower())