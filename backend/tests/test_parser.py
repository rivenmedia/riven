"""Test the parser module."""
import re
import PTN

string = 'Gold Rush S01 1080p AMZN WEB-DL DD+ 2.0 x264-QOQ'

def _is_unwanted_quality(string) -> bool:
    """Check if string has an 'unwanted' quality. Default to False."""
    unwanted_patterns = [
        re.compile(r"\b(?:H[DQ][ .-]*)?CAM(?:H[DQ])?(?:[ .-]*Rip)?\b", re.IGNORECASE),
        re.compile(r"\b(?:H[DQ][ .-]*)?S[ .-]*print\b", re.IGNORECASE),
        re.compile(r"\b(?:HD[ .-]*)?T(?:ELE)?S(?:YNC)?(?:Rip)?\b", re.IGNORECASE),
        re.compile(r"\b(?:HD[ .-]*)?T(?:ELE)?C(?:INE)?(?:Rip)?\b", re.IGNORECASE),
        re.compile(r"\bP(?:re)?DVD(?:Rip)?\b", re.IGNORECASE),
        re.compile(r"\b(?:DVD?|BD|BR)?[ .-]*Scr(?:eener)?\b", re.IGNORECASE),
        re.compile(r"\bVHS\b", re.IGNORECASE),
        re.compile(r"\bHD[ .-]*TV(?:Rip)?\b", re.IGNORECASE),
        re.compile(r"\bDVB[ .-]*(?:Rip)?\b", re.IGNORECASE),
        re.compile(r"\bSAT[ .-]*Rips?\b", re.IGNORECASE),
        re.compile(r"\bTVRips?\b", re.IGNORECASE),
        re.compile(r"\bR5\b", re.IGNORECASE),
        re.compile(r"\b(DivX|XviD)\b", re.IGNORECASE),
    ]
    return any(pattern.search(string) for pattern in unwanted_patterns)

data = {}
data.update({"string": string})
data.update({"is_unwanted_quality": _is_unwanted_quality(string)})
data.update(PTN.parse(string))

for k, v in data.items():
    print(f"{k}: {v}")
