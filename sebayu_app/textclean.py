
# sebayu_app/textclean.py
import re

FILLERS = {
    # filler umum
    "eh","emm","em","hmm","hmmm","ehem","anu","apa ya","gitu","gitu ya","kayak","kayaknya",
    "semacam","apa namanya","istilahnya","jadi","lah","dong","deh","sih","kan","gak sih","ya",
    "ya ya","iya iya","oke deh","btw","by the way","nggak tau ya","ga tau ya","maksudnya","ibaratnya",
    "yaudah","terus","lalu","nah","loh","aduh","waduh","astaga","wkwk","hehe","haha","hadeh",
    "begitu","pokoknya","sebenarnya","intinya","menurut saya","menurut gue","kira-kira","kayak gini",
    "gimana ya","entahlah","ngerti ga","tau ga","gatau deh","aslinya","sejujurnya","pada akhirnya",
    "sebetulnya","seharusnya","toh","malah","kayak apa","maksudku","apa gitu","apa sih",
}

REPLACEMENTS = {
    # singkatan -> normalisasi
    "btw": "", "gk": "nggak", "ga": "nggak", "td": "tadi", "yg": "yang",
    "dr": "dari", "dsb": "dan sebagainya", "dll": "dan lain-lain", "sdh": "sudah", "utk": "untuk",
    "tp": "tapi", "krn": "karena", "dgn": "dengan", "dg": "dengan", "sm": "sama",
    "aja": "saja", "trs": "terus", "blm": "belum", "udh": "sudah", "jd": "jadi",
}

RE_LAUGH = re.compile(r"\b(?:wkwk+|haha+|hehe+|hihi+|kwkw+|lol|lmao|rofl)\b", re.I)
RE_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF]")

def _squash_repeats(token: str) -> str:
    return re.sub(r"(.)\1{2,}", r"\1\1", token)

def _normalize_token(tok: str) -> str:
    t = RE_LAUGH.sub("", tok)
    t = RE_EMOJI.sub("", t)
    t = t.replace("…", "...")
    t = _squash_repeats(t)
    return t

def _strip_fillers(sentence: str) -> str:
    s = sentence.strip()
    for _ in range(3):
        low = s.lower()
        for f in sorted(FILLERS, key=len, reverse=True):
            if low.startswith(f + " "):
                s = s[len(f):].lstrip(); low = s.lower()
        for f in sorted(FILLERS, key=len, reverse=True):
            if low.endswith(" " + f):
                s = s[:-len(f)].rstrip(); low = s.lower()
    return s

def _drop_lonely_connectors(s: str) -> str:
    return re.sub(r"\b(?:terus|lalu|jadi|nah)\b\s*(?:,|\.|$)", ".", s, flags=re.I)

def clean_text_id(text: str, aggressive: bool = True) -> str:
    if not text or not text.strip():
        return text
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    out = []
    for s in sentences:
        if not s.strip():
            continue
        toks = [_normalize_token(t) for t in re.split(r"\s+", s) if t]
        norm = []
        for t in toks:
            low = t.lower()
            if low in REPLACEMENTS:
                rep = REPLACEMENTS[low]
                if rep:
                    norm.extend(rep.split())
            else:
                norm.append(t)
        pruned = []
        for t in norm:
            if t.lower() in FILLERS and len(norm) <= 5:
                continue
            pruned.append(t)
        s2 = " ".join(pruned)
        s2 = _strip_fillers(s2)
        s2 = _drop_lonely_connectors(s2)
        s2 = re.sub(r"\s+,", ",", s2)
        s2 = re.sub(r"\s+\.", ".", s2)
        s2 = re.sub(r"\s+", " ", s2).strip()
        if s2:
            out.append(s2)
    cleaned = "\n".join(out)
    if aggressive:
        cleaned = "\n".join([ln for ln in cleaned.splitlines() if len(ln.strip()) >= 3])
    return cleaned