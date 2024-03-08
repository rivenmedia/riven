import re

# Pattern for checking multi-audio in a torrent's title.
MULTI_AUDIO_PATTERNS = [
    r"\bmulti(?:ple)?[ .-]*(?:lang(?:uages?)?|audio|VF2)?\b",
    r"\btri(?:ple)?[ .-]*(?:audio|dub\w*)\b",
    r"\bdual[ .-]*(?:au?$|[aá]udio|line)\b",
    r"\b(?:audio|dub(?:bed)?)[ .-]*dual\b",
    r"\b(?:DUBBED|dublado|dubbing|DUBS?)\b",
]

# Pattern for checking multi-subtitle in a torrent's title.
MULTI_SUBTITLE_PATTERNS = [
    r"\bmulti(?:ple)?[ .-]*(?:lang(?:uages?)?)?\b",
    r"\bdual\b(?![ .-]*sub)",
    r"\bengl?(?:sub[A-Z]*)?\b",
    r"\beng?sub[A-Z]*\b",
]

# Pattern for identifying a complete series.
COMPLETE_SERIES_PATTERNS = [
    r"(?:\bthe\W)?(?:\bcomplete|collection|dvd)?\b[ .]?\bbox[ .-]?set\b",
    r"(?:\bthe\W)?(?:\bcomplete|collection|dvd)?\b[ .]?\bmini[ .-]?series\b",
    r"(?:\bthe\W)?(?:\bcomplete|full|all)\b.*\b(?:series|seasons|collection|episodes|set|pack|movies)\b",
    r"\b(?:series|seasons|movies?)\b.*\b(?:complete|collection)\b",
    r"(?:\bthe\W)?\bultimate\b[ .]\bcollection\b",
    r"\bcollection\b.*\b(?:set|pack|movies)\b",
    r"\bcollection\b",
    r"duology|trilogy|quadr[oi]logy|tetralogy|pentalogy|hexalogy|heptalogy|anthology|saga",
]

# Pattern for identifying unwanted quality.
UNWANTED_QUALITY_PATTERNS = [
    r"\b(?:H[DQ][ .-]*)?CAM(?:H[DQ])?(?:[ .-]*Rip)?\b",
    r"\b(?:H[DQ][ .-]*)?S[ .-]*print\b",
    r"\b(?:HD[ .-]*)?T(?:ELE)?S(?:YNC)?(?:Rip)?\b",
    r"\b(?:HD[ .-]*)?T(?:ELE)?C(?:INE)?(?:Rip)?\b",
    r"\bP(?:re)?DVD(?:Rip)?\b",
    r"\b(?:DVD?|BD|BR)?[ .-]*Scr(?:eener)?\b",
    r"\bVHS\b",
    r"\bHD[ .-]*TV(?:Rip)?\b",
    r"\bDVB[ .-]*(?:Rip)?\b",
    r"\bSAT[ .-]*Rips?\b",
    r"\bTVRips?\b",
    r"\bR5|R6\b",
    r"\b(DivX|XviD)\b",
    r"\b(?:Deleted[ .-]*)?Scene(?:s)?\b",
    r"\bTrailers?\b",
]

MULTI_AUDIO_COMPILED = [
    re.compile(pattern, re.IGNORECASE) for pattern in MULTI_AUDIO_PATTERNS
]
MULTI_SUBTITLE_COMPILED = [
    re.compile(pattern, re.IGNORECASE) for pattern in MULTI_SUBTITLE_PATTERNS
]
COMPLETE_SERIES_COMPILED = [
    re.compile(pattern, re.IGNORECASE) for pattern in COMPLETE_SERIES_PATTERNS
]
UNWANTED_QUALITY_COMPILED = [
    re.compile(pattern, re.IGNORECASE) for pattern in UNWANTED_QUALITY_PATTERNS
]
