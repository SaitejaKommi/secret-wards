"""PII in hidden places: file and folder names, path-like metadata, JSON keys / column headers,
encoded runs (base64, hex, \\uXXXX escapes, HTML entities) and homoglyph-disguised text.

Two kinds of API:
1. `HiddenDetector` (a normal Detector, registered in default_detectors()):
   - path-like values (header says path/file/source/dir/url, or the value has a backslash, a drive prefix or a
     leading '/' with a file extension): a path component that holds a name or an id is redacted WHOLE, so the
     digits next to a name (`<First>_<Last>_<id>`) go too;
   - encoded runs: decoded, and the WHOLE run is redacted only if the decoded text contains PII. Runs that decode
     to non-text (FHIR ids, hashes) are skipped. Note: the renderer replaces the run with a placeholder, which is
     not valid base64; FHIR attachments must use `clean_encoded()` instead (re-encodes the cleaned text);
   - homoglyphs: Cyrillic/Greek look-alikes inside Latin words are folded 1:1 (offsets unchanged) and the other
     detectors run on the folded view.
2. Pure functions for the contract writer / FHIR sanitizer (Saiteja / step 4):
   - `sanitize_path(rel_path, key) -> str`: same path if no component has PII, else each PII component renamed
     (extension kept; a keyed HMAC tag keeps names unique and changes with the secret);
   - `safe_label(label, key) -> str`: a JSON key / column header unchanged unless it holds PII;
   - `clean_encoded(text, redact) -> str`: decode base64 / hex runs, apply `redact(decoded) -> str`, re-encode.
Inner detection reuses the other detectors (never this one, so no recursion) and only runs on candidate pieces.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import html
from functools import lru_cache
from typing import Callable

import regex as re

from ..contracts import PIIType, Span, Unit
from .base import Collector

_PII_TYPES = {PIIType.NAME, PIIType.PHONE, PIIType.EMAIL, PIIType.ABHA, PIIType.INSURANCE, PIIType.MRN, PIIType.ID,
              PIIType.ADDRESS, PIIType.PINCODE}

# ---------------------------------------------------------------- inner detection
_INNER = None


def _inner_detectors():
    global _INNER
    if _INNER is None:
        from .address import AddressDetector
        from .address_fields import AddressFieldDetector
        from .india_ids import IndiaIdDetector
        from .names import NameDetector
        from .rules import RuleDetector
        _INNER = [RuleDetector(), AddressDetector(), NameDetector(), IndiaIdDetector(), AddressFieldDetector()]
    return _INNER


def inner_spans(text: str, header: str = "", types=frozenset(_PII_TYPES)) -> list[Span]:
    """PII spans in `text` (offsets in `text`) found by the other detectors."""
    from . import detect_unit  # lazy: detect/__init__ imports this module
    from ..normalize.text import normalize
    if not text or not text.strip():
        return []
    u = Unit("hidden", None, header, text, normalize(text))
    spans, _ = detect_unit(u, _inner_detectors())
    return [s for s in spans if s.type in types]


# ---------------------------------------------------------------- name components (files, folders, path segments)
_SEP = re.compile(r"[_.\s]+")
# lowercase-tolerant hospital numbers as they appear in file names: ipd-2031-00812, adm004417, uhid-009153 (invented examples)
_ID_TOKEN = re.compile(r"^[A-Za-z]{1,6}(?:-[A-Za-z]{1,6})?[-/]?\d+(?:[-/]\d+)*$")


def _token_kind(tok: str) -> PIIType | None:
    from .rules import valid_phone_digits
    digits = sum(c.isdigit() for c in tok)
    if tok.isdigit():
        if valid_phone_digits(tok):
            return PIIType.PHONE
        if len(tok) == 12 and tok[0] in "23456789":
            return PIIType.ID  # Aadhaar-shaped
        if len(tok) == 14:
            return PIIType.ABHA
        return None  # counters: report_00047, rx_..._00053
    if digits >= 5 and _ID_TOKEN.match(tok):
        return PIIType.MRN
    return None


def _views(stem: str) -> list[str]:
    """Readings of a file / folder name for the name detectors: separators as spaces, hyphens as spaces, camelCase split."""
    spaced = _SEP.sub(" ", stem)
    v = [spaced, spaced.replace("-", " "), re.sub(r"(?<=\p{Ll})(?=\p{Lu})", " ", spaced.replace("-", " "))]
    return list(dict.fromkeys(v))


@lru_cache(maxsize=4096)
def component_has_pii(stem: str) -> bool:
    """A file / folder / path-segment name (without extension) holds PII? Only identifying kinds count
    (name, phone, email, ids): a city or district in a name like '<city>_branch_opd' is not a reason to rename."""
    if not stem or not any(c.isalpha() or c.isdigit() for c in stem):
        return False
    dotted = re.sub(r"(?<=[A-Za-z0-9])\.(?=\d)", "-", stem)  # 'IPD.2025.00412' -> 'IPD-2025-00412'
    if any(_token_kind(t) for x in (stem, dotted) for t in _SEP.split(x) if t):
        return True
    return any(inner_spans(v, header="", types=frozenset(_LABEL_KINDS)) for v in _views(stem))


def _tag(key: bytes, text: str, n: int = 10) -> str:
    return hmac.new(key, b"hidden-name\x00" + text.encode("utf-8"), hashlib.sha256).hexdigest()[:n]


_DOUBLE_EXT = re.compile(r"\.(?:tar|json|csv|tsv|txt|xml|ndjson|jsonl)\.(?:gz|bz2|xz|zst|zip)$", re.I)
_EXT = re.compile(r"\.(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{1,5}$")


def _split_ext(name: str) -> tuple[str, str]:
    """Only the final suffix is an extension (plus known double ones like .json.gz): 'First.Last.txt' -> 'First.Last'."""
    m = _DOUBLE_EXT.search(name) or _EXT.search(name)
    if not m or m.start() == 0:
        return name, ""
    return name[:m.start()], name[m.start():]


def sanitize_path(rel_path: str, key: bytes) -> str:
    """Rename only the components of a relative path ('a/b/c.ext') that hold PII; keep the extension.

    Deterministic for the same key; different keys give different names. Unique per original component
    (HMAC of the original), so two patients' files never collide in one directory.
    """
    parts = rel_path.replace("\\", "/").split("/")
    out = []
    for i, part in enumerate(parts):
        stem, ext = _split_ext(part) if i == len(parts) - 1 else (part, "")
        if component_has_pii(stem):
            out.append(f"redacted_{_tag(key, '/'.join(parts[:i + 1]))}{ext}")
        else:
            out.append(part)
    return "/".join(out)


_LABEL_KINDS = {PIIType.NAME, PIIType.PHONE, PIIType.EMAIL, PIIType.ABHA, PIIType.INSURANCE, PIIType.MRN, PIIType.ID}


# Form / schema words a column title is built from (beyond the lead's HEADER_WORDS): general Hindi / Hinglish
# form vocabulary so an unseen header like "Janm Tithi" or "Gaon" is not mistaken for a person's name.
_SCHEMA_WORDS = frozenset("""
janm janam tithi tarikh tareekh dinank umr umar aayu ling linga naam nam pita pati patni mata putra putri beta beti
gaon gaanv gram mohalla tehsil tahsil jila zila zilla pata ghar makan sankhya kramank panjikaran bhartee bharti
mobile phone sampark aadhar aadhaar adhar rashi rakam bimari rog nidan dawa dawai jaanch janch report vibhag ward
bed kamra chikitsak doctor dr sr serial visit visits ref refs record records type status code display value unit
units meta source path system exported generated created updated time timestamp id ids index by map list
pradhan mukhya nidan nidaan chikitsa chikitsak adhikari bhugtan sthiti sthithi kul rashi shulk upchar vibhag jaanch janch
parinaam parinam sanstha dawa dawai aushadhi rog prakar vivaran samay din mahina varsh saal sankhya praman patra beema bima
yojana kendra aspatal anubhag shreni varg kaksh bistar pravesh visarjan chhutti mulyankan tippani nirdesh matra khurak
avadhi raktchap taapman vajan lambai jaati dharm vyavsay shiksha vaivahik pehchan pahchan sampark vivran sewa seva
""".split())


def _schema_only(label: str) -> bool:
    from .lexicon import HEADER_WORDS
    words = [w for w in re.split(r"[^\p{L}\p{M}\d]+", label) if w]
    return bool(words) and all(w.lower() in HEADER_WORDS or w.lower() in _SCHEMA_WORDS or (w.isdigit() and len(w) <= 2)
                               for w in words)


@lru_cache(maxsize=4096)
def label_has_pii(label: str) -> bool:
    """A JSON key or column header that is itself personal data (a name, a phone, a record number)."""
    if not label or not label.strip():
        return False
    if any(_token_kind(t) for t in re.split(r"[_.\s]+", label) if t):
        return True
    spaced = re.sub(r"[_.]", " ", label)
    found = inner_spans(spaced, header="", types=frozenset(_LABEL_KINDS))
    if not found:
        return False
    if all(sp.type == PIIType.NAME for sp in found) and _schema_only(label):
        return False  # a name-shaped title made only of form words ("Janm Tithi")
    return True


def safe_label(label: str, key: bytes) -> str:
    """The label unchanged unless it holds PII; then a stable keyed stand-in."""
    return f"field_{_tag(key, label, 8)}" if label_has_pii(label) else label


# ---------------------------------------------------------------- encoded runs
_B64 = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])")
_HEX = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){10,}(?![0-9A-Fa-f])")  # 10 bytes: a hex-encoded mobile number
_UESC = re.compile(r"(?:\\u[0-9A-Fa-f]{4}){3,}")
_ENT = re.compile(r"(?:&(?:#\d{1,7}|#[xX][0-9A-Fa-f]{1,6}|[A-Za-z]{2,8});){3,}")


def _texty(s: str) -> bool:
    """Decoded bytes look like human text or an encoded number (not a hash, id or binary).

    Digits-only payloads count too: a phone or Aadhaar number hidden as hex / &#NN; / \\uXXXX decodes to digits.
    Random bytes (hashes, ids) almost never decode to printable text with a 6-digit run."""
    if len(s) < 6:
        return False
    printable = sum(c.isprintable() or c in "\n\r\t" for c in s)
    if printable / len(s) < 0.95:
        return False
    letters = sum(c.isalpha() for c in s)
    wordy = letters / len(s) >= 0.2 and bool(re.search(r"[\p{L}]{3,}", s))
    numbery = bool(re.search(r"\d{6,}", re.sub(r"[\s\-.()+]", "", s)))
    return wordy or numbery


def _decode_b64(tok: str) -> str | None:
    try:
        raw = base64.b64decode(tok + "=" * (-len(tok) % 4), validate=True)
        s = raw.decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    return s if _texty(s) else None


def _decode_hex(tok: str) -> str | None:
    try:
        s = bytes.fromhex(tok).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    return s if _texty(s) else None


def _decode_uesc(tok: str) -> str | None:
    try:
        s = tok.encode("ascii").decode("unicode_escape")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return None
    return s if _texty(s) else None


def _decode_ent(tok: str) -> str | None:
    s = html.unescape(tok)
    return s if s != tok and _texty(s) else None


_DECODERS = ((_B64, _decode_b64), (_HEX, _decode_hex), (_UESC, _decode_uesc), (_ENT, _decode_ent))


def encoded_runs(text: str) -> list[tuple[int, int, str]]:
    """(start, end, decoded) for every encoded run in `text` that decodes to readable text."""
    out = []
    for rx, dec in _DECODERS:
        for m in rx.finditer(text):
            s = dec(m.group())
            if s is not None and not any(a < m.end() and m.start() < b for a, b, _ in out):
                out.append((m.start(), m.end(), s))
    return out


def clean_encoded(text: str, redact: Callable[[str], str]) -> str:
    """Decode base64 / hex runs, clean the decoded text with `redact`, re-encode in the same encoding.

    For FHIR attachments and any field that must stay valid base64. Runs that do not decode to text are left alone.
    """
    out, last = [], 0
    for a, b, decoded in sorted(encoded_runs(text)):
        cleaned = redact(decoded)
        tok = text[a:b]
        if cleaned == decoded:
            continue
        if _B64.fullmatch(tok):
            new = base64.b64encode(cleaned.encode("utf-8")).decode("ascii")
            if not tok.endswith("=") and len(tok) % 4 != 0:  # keep padding when the original length was a whole number of groups:
                new = new.rstrip("=")  # the new text may be a different length and FHIR base64 needs complete groups of 4
        elif _HEX.fullmatch(tok):
            new = cleaned.encode("utf-8").hex()
            new = new.upper() if tok.isupper() else new
        else:
            new = html.escape(cleaned)  # entities / \u escapes: plain escaped text is enough
        out.append(text[last:a])
        out.append(new)
        last = b
    out.append(text[last:])
    return "".join(out)


# ---------------------------------------------------------------- homoglyphs
_FOLD = str.maketrans({
    "а": "a", "в": "B", "е": "e", "к": "k", "м": "M", "н": "H", "о": "o", "р": "p", "с": "c", "т": "T", "у": "y",
    "х": "x", "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ɡ": "g", "һ": "h", "ӏ": "l", "ո": "n",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "У": "Y",
    "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S",
    "α": "a", "ο": "o", "ρ": "p", "ν": "v", "ι": "i", "κ": "k", "τ": "t", "υ": "u",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P",
    "Τ": "T", "Υ": "Y", "Χ": "X",
})
_MIXED_WORD = re.compile(r"\b(?=[\p{L}]*\p{Latin})(?=[\p{L}]*[\p{Cyrillic}\p{Greek}])[\p{Latin}\p{Cyrillic}\p{Greek}]+\b")


def fold_homoglyphs(text: str) -> str:
    """1:1 fold of Cyrillic/Greek look-alikes, only inside words that also contain Latin letters."""
    return _MIXED_WORD.sub(lambda m: m.group().translate(_FOLD), text)


_DATE_RUN = re.compile(r"(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?:\d{4,6})?|"
                       r"(?:0[1-9]|[12]\d|3[01])(?:0[1-9]|1[0-2])(?:19|20)\d{2}")
_EXPORT_WORDS = frozenset("""backup backups archive archives export exports import data final old new copy batch run job jobs report
reports files file temp tmp snapshot dump sync upload uploads download downloads scan scans misc his emr hmis lis ris pacs
daily weekly monthly yearly auto manual migrated migration legacy prod test""".split())


def _person_folder(stem: str) -> bool:
    """A path segment like <Name>_<Initials>_<id>: a capitalised non-schema word next to a 5+ digit run.
    Used for metadata paths only (exports are often filed per patient); file names need stronger evidence."""
    from .lexicon import HEADER_WORDS
    toks = [t for t in _SEP.split(stem) if t]
    has_id = any(sum(c.isdigit() for c in t) >= 5 and not _DATE_RUN.fullmatch(t) for t in toks)
    has_cap = any(t[:1].isupper() and t.isalpha() and t.lower() not in HEADER_WORDS and t.lower() not in _SCHEMA_WORDS
                  and t.lower() not in _EXPORT_WORDS for t in toks)
    return has_id and has_cap


# ---------------------------------------------------------------- the detector
_PATH_HDR = re.compile(r"path|file|source|\bdir|folder|\burl\b|\buri\b|location|attachment\s*name", re.I)
_PATHY = re.compile(r"\\|^[A-Za-z]:[\\/]|^(?:/[^/\s]+){2,}\.[A-Za-z0-9]{1,6}$|^[a-z][a-z0-9+.-]*://")
_PATH_SPLIT = re.compile(r"[\\/]+")


class HiddenDetector:
    name = "hidden"

    def detect(self, unit: Unit) -> list[Span]:
        col = Collector(unit, self.name)
        text = unit.norm.text
        if not text.strip():
            return col.spans

        # 1. path-like values: redact whole components that hold PII
        stripped = text.strip()
        if " " not in stripped or "\\" in stripped:
            if _PATHY.search(stripped) or (unit.header and _PATH_HDR.search(unit.header) and _PATH_SPLIT.search(stripped)):
                is_url = bool(re.match(r"[a-z][a-z0-9+.-]*://", stripped, re.I))
                pos = 0
                for seg in _PATH_SPLIT.split(text):
                    a = text.index(seg, pos) if seg else pos
                    b = a + len(seg)
                    pos = b
                    stem, _ = _split_ext(seg)
                    if not stem:
                        continue
                    if is_url:
                        # canonical URLs (FHIR profiles, code systems, extension urls) are CamelCase vocabulary
                        # ("StructureDefinition/DocumentBundle"): only an id-shaped token or a <Name>_<id> folder counts
                        hit = _person_folder(stem) or any(_token_kind(t) for t in _SEP.split(stem) if t)
                    else:
                        hit = _person_folder(stem) or component_has_pii(stem)
                    if hit:
                        col.add(a, a + len(stem), PIIType.ID, 0.9)

        # 2. encoded runs whose decoded text holds PII
        if len(text) >= 18:
            for a, b, decoded in encoded_runs(text):
                found = inner_spans(decoded) or inner_spans(fold_homoglyphs(decoded))
                if found:
                    col.add(a, b, PIIType.ID, 0.95)  # ID, not NAME: the gate must not treat base64 chars as name words

        # 3. homoglyph-disguised words
        if not text.isascii():
            folded = fold_homoglyphs(text)
            if folded != text:
                for s in inner_spans(folded, unit.header):
                    # inner spans are in ORIGINAL offsets of `folded`, which equal normalized offsets of `text` (1:1 fold)
                    col.add(s.start, s.end, s.type, 0.9, s.role)
        return col.spans
