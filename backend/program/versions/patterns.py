import regex

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

HDR_DOLBY_VIDEO_PATTERNS = [
    (r"\bDV\b|dolby.?vision|\bDoVi\b", "DV"),
    (r"HDR10(?:\+|plus)", "HDR10+"),
    (r"\bHDR(?:10)?\b", "HDR"),
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

# Pattern for identifying unwanted quality. We don't fetch any of this!
UNWANTED_QUALITY_PATTERNS = [
    r"\b(?:H[DQ][ .-]*)?CAM(?:H[DQ])?(?:[ .-]*Rip)?\b",
    r"\b(?:H[DQ][ .-]*)?S[ .-]*print\b",
    r"\b(?:HD[ .-]*)?T(?:ELE)?S(?:YNC)?(?:Rip)?\b",
    r"\b(?:HD[ .-]*)?T(?:ELE)?C(?:INE)?(?:Rip)?\b",
    r"\bP(?:re)?DVD(?:Rip)?\b",
    r"\b(?:DVD?|BD|BR)?[ .-]*Scr(?:eener)?\b",
    r"\bVHS\b",
    r"\bHD[ .-]*TV(?:Rip)\b",
    r"\bDVB[ .-]*(?:Rip)?\b",
    r"\bSAT[ .-]*Rips?\b",
    r"\bTVRips?\b",
    r"\bR5|R6\b",
    r"\b(DivX|XviD)\b",
    r"\b(?:Deleted[ .-]*)?Scene(?:s)?\b",
    r"\bTrailers?\b",
    r"\b((Half.)?SBS|3D)\b",
    r"\bWEB[ .-]?DL[ .-]?Rip\b",
    r"\bUm Actually|Captive Audience|Copycat Killers\b"
]

EPISODE_PATTERNS = [
    (regex.compile(r"(?:[\W\d]|^)e[ .]?[([]?(\d{1,3}(?:[ .-]*(?:[&+]|e){1,2}[ .]?\d{1,3})+)(?:\W|$)", regex.IGNORECASE), "range"),
    (regex.compile(r"(?:[\W\d]|^)ep[ .]?[([]?(\d{1,3}(?:[ .-]*(?:[&+]|ep){1,2}[ .]?\d{1,3})+)(?:\W|$)", regex.IGNORECASE), "range"),
    (regex.compile(r"(?:[\W\d]|^)\d+[xх][ .]?[([]?(\d{1,3}(?:[ .]?[xх][ .]?\d{1,3})+)(?:\W|$)", regex.IGNORECASE), "range"),
    (regex.compile(r"(?:[\W\d]|^)(?:episodes?|[Сс]ерии:?)[ .]?[([]?(\d{1,3}(?:[ .+]*[&+][ .]?\d{1,3})+)(?:\W|$)", regex.IGNORECASE), "range"),
    (regex.compile(r"[([]?(?:\D|^)(\d{1,3}[ .]?ao[ .]?\d{1,3})[)\]]?(?:\W|$)", regex.IGNORECASE), "range"),
    (regex.compile(r"(?:[\W\d]|^)(?:e|eps?|episodes?|[Сс]ерии:?|\d+[xх])[ .]*[([]?(\d{1,3}(?:-\d{1,3})+)(?:\W|$)", regex.IGNORECASE), "range"),
    (regex.compile(r"(?:\W|^)[st]\d{1,2}[. ]?[xх-]?[. ]?(?:e|x|х|ep|-|\.)[. ]?(\d{1,3})(?:[abc]|v0?[1-4]|\D|$)", regex.IGNORECASE), "array(integer)"),
    (regex.compile(r"\b[st]\d{2}(\d{2})\b", regex.IGNORECASE), "array(integer)"),
    (regex.compile(r"(?:\W|^)(\d{1,3}(?:[ .]*~[ .]*\d{1,3})+)(?:\W|$)", regex.IGNORECASE), "range"),
    (regex.compile(r"-\s(\d{1,3}[ .]*-[ .]*\d{1,3})(?!-\d)(?:\W|$)", regex.IGNORECASE), "range"),
    (regex.compile(r"s\d{1,2}\s?\((\d{1,3}[ .]*-[ .]*\d{1,3})\)", regex.IGNORECASE), "range"),
    (regex.compile(r"(?:^|\/)\d{1,2}-(\d{2})\b(?!-\d)"), "array(integer)"),
    (regex.compile(r"(?<!\d-)\b\d{1,2}-(\d{2})(?=\.\w{2,4}$)"), "array(integer)"),
    (regex.compile(r"(?<!seasons?|[Сс]езони?)\W(?:[ .([-]|^)(\d{1,3}(?:[ .]?[,&+~][ .]?\d{1,3})+)(?:[ .)\]-]|$)", regex.IGNORECASE), "range"),
    (regex.compile(r"(?<!seasons?|[Сс]езони?)\W(?:[ .([-]|^)(\d{1,3}(?:-\d{1,3})+)(?:[ .)(\]]|-\D|$)", regex.IGNORECASE), "range"),
    (regex.compile(r"\bEp(?:isode)?\W+\d{1,2}\.(\d{1,3})\b", regex.IGNORECASE), "array(integer)"),
    (regex.compile(r"(?:\b[ée]p?(?:isode)?|[Ээ]пизод|[Сс]ер(?:ии|ия|\.)?|cap(?:itulo)?|epis[oó]dio)[. ]?[-:#№]?[. ]?(\d{1,4})(?:[abc]|v0?[1-4]|\W|$)", regex.IGNORECASE), "array(integer)"),
    (regex.compile(r"\b(\d{1,3})(?:-?я)?[ ._-]*(?:ser(?:i?[iyj]a|\b)|[Сс]ер(?:ии|ия|\.)?)", regex.IGNORECASE), "array(integer)"),
    (regex.compile(r"(?:\D|^)\d{1,2}[. ]?[xх][. ]?(\d{1,3})(?:[abc]|v0?[1-4]|\D|$)"), "array(integer)"),
    (regex.compile(r"[[(]\d{1,2}\.(\d{1,3})[)\]]"), "array(integer)"),
    (regex.compile(r"\b[Ss]\d{1,2}[ .](\d{1,2})\b"), "array(integer)"),
    (regex.compile(r"-\s?\d{1,2}\.(\d{2,3})\s?-"), "array(integer)"),
    (regex.compile(r"(?<=\D|^)(\d{1,3})[. ]?(?:of|из|iz)[. ]?\d{1,3}(?=\D|$)", regex.IGNORECASE), "array(integer)"),
    (regex.compile(r"\b\d{2}[ ._-](\d{2})(?:.F)?\.\w{2,4}$"), "array(integer)"),
    (regex.compile(r"(?<!^)\[(\d{2,3})\](?!(?:\.\w{2,4})?$)"), "array(integer)"),
]

MULTI_AUDIO_COMPILED = [
    regex.compile(pattern, regex.IGNORECASE) for pattern in MULTI_AUDIO_PATTERNS
]
MULTI_SUBTITLE_COMPILED = [
    regex.compile(pattern, regex.IGNORECASE) for pattern in MULTI_SUBTITLE_PATTERNS
]
COMPLETE_SERIES_COMPILED = [
    regex.compile(pattern, regex.IGNORECASE) for pattern in COMPLETE_SERIES_PATTERNS
]
UNWANTED_QUALITY_COMPILED = [
    regex.compile(pattern, regex.IGNORECASE) for pattern in UNWANTED_QUALITY_PATTERNS
]
HDR_DOLBY_VIDEO_COMPILED = [
    (regex.compile(pattern, regex.IGNORECASE), value)
    for pattern, value in HDR_DOLBY_VIDEO_PATTERNS
]
