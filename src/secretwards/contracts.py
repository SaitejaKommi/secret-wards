"""Typed records shared by all pipeline stages.

Stages talk ONLY through these types. Changing them after M2 needs team approval.

Conventions
- Offsets in `Span` / `MedSpan` always refer to the ORIGINAL text of the field
  (never the normalized text). `NormText` carries the map back.
- `field is None` means the free-text body of a document (`Document.text`).
- Extra cells beyond the header of a table row are named `_extra<index>`.
- JSON leaves are named by their path, e.g. `visit.notes` or `items[0].name`.
- Nothing here may hold PII in a repr that reaches logs: `Document` and `Span`
  never print their text. Only the stage that owns raw text should hold it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional, Protocol, Sequence, runtime_checkable


class PIIType(str, Enum):
    NAME = "NAME"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    DATE = "DATE"
    ABHA = "ABHA"
    INSURANCE = "INSURANCE"
    MRN = "MRN"
    ID = "ID"  # any other identifier
    ADDRESS = "ADDRESS"
    PINCODE = "PINCODE"


ID_TYPES = frozenset({PIIType.ABHA, PIIType.INSURANCE, PIIType.MRN, PIIType.ID})


class MedKind(str, Enum):
    DRUG = "DRUG"
    DOSE = "DOSE"
    FREQ = "FREQ"
    DURATION = "DURATION"
    VITAL = "VITAL"
    LAB = "LAB"
    DIAGNOSIS = "DIAGNOSIS"
    PROCEDURE = "PROCEDURE"
    AGE = "AGE"
    LOS = "LOS"


class QReason(str, Enum):
    """Why a file or record was quarantined. Codes only, never messages."""

    UNSUPPORTED_FORMAT = "unsupported_format"
    UNREADABLE = "unreadable"
    ENCODING = "encoding"
    TOO_LARGE = "too_large"
    EMPTY = "empty"
    SUSPICIOUS_ARCHIVE = "suspicious_archive"
    LEAK_GATE = "leak_gate"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class NormText:
    """Normalized text plus the map back to the original.

    `starts[i]`/`ends[i]` give the original [start, end) of normalized char i.
    """

    text: str
    starts: tuple[int, ...]
    ends: tuple[int, ...]

    def to_orig(self, s: int, e: int) -> tuple[int, int]:
        if e <= s:
            raise ValueError("empty span")
        return self.starts[s], self.ends[e - 1]


@dataclass(frozen=True)
class Document:
    """One record: a table row, a JSON object, or a text file."""

    doc_id: str  # keyed hash, never derived from raw filenames in the clear
    hospital: str  # pseudonymized label
    source: str  # csv | json | txt | xlsx
    ordinal: int  # row/object index inside its file
    text: str  # free-text body (txt files) else ""
    fields: Mapping[str, str]  # structured cells / flattened JSON leaves

    def __repr__(self) -> str:  # never print content
        return f"Document({self.doc_id}, {self.source}#{self.ordinal})"


@dataclass(frozen=True)
class Unit:
    """One piece of text a detector looks at (a field value or the body)."""

    doc_id: str
    field: Optional[str]
    header: str  # lowercased, normalized header hint ("" for free text)
    original: str
    norm: NormText


@dataclass(frozen=True)
class Span:
    doc_id: str
    field: Optional[str]
    start: int  # offsets in ORIGINAL text of that field
    end: int
    type: PIIType
    detector: str
    score: float
    role: str = ""  # patient | relative | doctor | "" (names only)

    def __repr__(self) -> str:
        return f"Span({self.type.value},{self.start}:{self.end},{self.detector})"


@dataclass(frozen=True)
class MedSpan:
    doc_id: str
    field: Optional[str]
    start: int
    end: int
    kind: MedKind


@dataclass(frozen=True)
class Mention:
    """Linkage evidence extracted from one document. Holds raw values: memory only."""

    doc_id: str
    hospital: str
    name_tokens: tuple[str, ...] = ()  # patient name tokens as written
    rel_tokens: tuple[tuple[str, ...], ...] = ()  # father/spouse names
    phones: tuple[str, ...] = ()  # 10-digit normalized
    emails: tuple[str, ...] = ()
    abha: tuple[str, ...] = ()  # 14 digits
    insurance: tuple[str, ...] = ()
    mrn: tuple[str, ...] = ()
    dob: Optional[str] = None  # ISO date if a date of birth was identified
    ref_year: Optional[int] = None  # year of the encounter, if known
    age: Optional[int] = None
    sex: Optional[str] = None  # M | F | None
    pin: Optional[str] = None
    place_tokens: tuple[str, ...] = ()  # locality/city tokens, lowercased

    def __repr__(self) -> str:
        return f"Mention({self.doc_id})"


@dataclass(frozen=True)
class Cluster:
    pseudonym: str
    doc_ids: tuple[str, ...]
    evidence: tuple[str, ...] = ()  # reason codes, e.g. "abha", "phone+name"


@dataclass
class RedactedRecord:
    """A de-identified record, ready for export and the leak gate."""

    doc_id: str
    hospital: str
    pseudonym: str
    source: str
    ordinal: int
    text: str
    fields: dict[str, str]
    meta: dict[str, str] = field(default_factory=dict)  # age, sex, pin3, dates ...
    paths: dict[str, list] = field(default_factory=dict)  # JSON leaf paths


@dataclass(frozen=True)
class QuarantineEntry:
    ref: str  # keyed hash of file path (or doc_id for a record)
    reason: QReason
    scope: str  # "file" | "record"


@dataclass
class SourceFile:
    """A parsed input file. `layout` holds what an exporter needs to rebuild it."""

    ref: str  # keyed hash of relative path
    ordinal: int  # position in sorted input listing (PII-free handle)
    kind: str  # csv | json | txt | xlsx
    docs: list[Document]
    layout: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Interfaces for teammates. Implement these and register in pipeline.py.
# --------------------------------------------------------------------------


@runtime_checkable
class Detector(Protocol):
    """Pluggable PII detector (rules, gazetteer, CRF...). Offsets in ORIGINAL text."""

    name: str

    def detect(self, unit: Unit) -> Sequence[Span]: ...


@runtime_checkable
class Exporter(Protocol):
    """Writes de-identified records in one output format (e.g. FHIR R4)."""

    def export(self, records: Sequence[RedactedRecord], out_dir: Path) -> Sequence[str]:
        """Return the relative names of files written."""
        ...


@runtime_checkable
class Vault(Protocol):
    """Authenticated encryption for raw / intermediate data at rest."""

    def encrypt(self, data: bytes, context: bytes = b"") -> bytes: ...

    def decrypt(self, blob: bytes, context: bytes = b"") -> bytes: ...


@runtime_checkable
class RiskAttack(Protocol):
    """Re-identification attack used to measure residual risk of the output."""

    def run(self, records: Sequence[RedactedRecord]) -> Mapping[str, float]: ...
