"""Framework labels of calculation notes: English with proposed Arabic (spec 0001 section 4.10, owner review Q7).

Purpose: one table from an English framework label to its Arabic label; a label without an entry is English only.
Units: none. Errors: none.
"""

from html import escape

# Wording proposed by spec 0001 section 4.10; the owner reviews it (spec section 11 Q7).
ARABIC: dict[str, str] = {
    "Inputs": "المدخلات",
    "Constants": "الثوابت",
    "Calculation steps": "خطوات الحساب",
    "Verdicts": "النتائج",
    "Status": "الحالة",
    "Demand": "الطلب",
    "Capacity": "المقاومة",
    "Ratio": "النسبة",
    "Clause": "البند",
    "Source": "المصدر",
    "Assumptions": "الافتراضات",
    "Subject": "العنصر",
    "Draft": "مسودة",
    "PASS": "مقبول",
    "FAIL": "غير مقبول",
    "NOT_APPLICABLE": "غير منطبق",
    "NEEDS_ENGINEER": "يحتاج إلى مهندس",
    "ERROR": "خطأ",
}

ENGLISH: dict[str, str] = {
    "PASS": "Pass",
    "FAIL": "Fail",
    "NOT_APPLICABLE": "Not applicable",
    "NEEDS_ENGINEER": "Needs engineer",
    "ERROR": "Error",
}


def arabic_span(key: str) -> str:
    """Return the `<span lang="ar" dir="rtl">` element of the Arabic label of `key`, or "" when it has none."""
    arabic = ARABIC.get(key)
    return "" if arabic is None else f'<span lang="ar" dir="rtl">{escape(arabic, quote=True)}</span>'


def label(key: str) -> str:
    """Return the HTML of a framework label: the English text, then its Arabic span when the table has one."""
    english = escape(ENGLISH.get(key, key), quote=True)
    span = arabic_span(key)
    return f"{english} {span}" if span else english
