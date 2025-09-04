import re

BANNED = [
    r"\brockstar\b",
    r"\bninja\b",
    r"\byoung\b",
    r"\bdigital native\b"
]

def check_inclusive_language(text: str):
    warnings = []
    for pattern in BANNED:
        for m in re.finditer(pattern, text, flags=re.I):
            warnings.append({"span": m.group(0), "start": m.start(), "end": m.end(), "note": "Consider more inclusive wording"})
    return warnings
