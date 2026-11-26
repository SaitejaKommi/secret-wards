"""A single large note must scale (roughly) linearly. It used to be quadratic: 213 KB took 17 s and a 4 MB note would hang."""
import time

from secretwards.contract.run import run_contract

PARA = "Patient Name: Omkar Bivalkar, Phone 9876509876. BP 110/70 mmHg, fever for 3 days. Tab. Dolo 650 BD x 5 days.\n"


def timed(tmp_path, repeat):
    inp = tmp_path / f"in{repeat}"
    inp.mkdir()
    (inp / "big.txt").write_text(PARA * repeat, encoding="utf-8")
    t = time.perf_counter()
    assert run_contract(inp, tmp_path / f"out{repeat}", b"perf-secret") == 0
    return time.perf_counter() - t, (tmp_path / f"out{repeat}" / "sanitized" / "big.txt").read_text(encoding="utf-8")


def test_large_note_scales_linearly(tmp_path):
    t_small, _ = timed(tmp_path, 1000)    # about 106 KB
    t_big, out = timed(tmp_path, 4000)    # about 426 KB
    assert t_big < 25, f"426 KB took {t_big:.1f}s"
    assert t_big / max(t_small, 0.05) < 9, f"4x data took {t_big / max(t_small, 0.05):.1f}x as long (quadratic would be ~16x)"
    # and it still redacts and keeps medical values everywhere in the big file
    assert "Bivalkar" not in out and "9876509876" not in out
    assert out.count("Dolo 650 BD x 5 days") == 4000 and out.count("110/70 mmHg") == 4000


def _reference_merge(spans, meds, text):
    """The original O(n^2) merge, kept here as the specification the fast version must match."""
    from secretwards.contracts import MedKind, PIIType, Span
    from secretwards.detect.merge import _NUMERIC_GUARDED, _PRIO, _TEXT_GUARDED, _overlap

    kept = []
    for s in spans:
        if s.type in _TEXT_GUARDED:
            ln = max(1, s.end - s.start)
            cov = sum(_overlap(s.start, s.end, a, b) for a, b, k in meds if k in (MedKind.DRUG, MedKind.LAB, MedKind.VITAL, MedKind.DOSE))
            if cov / ln >= 0.6 and s.score < 0.95:
                continue
        if s.type in _NUMERIC_GUARDED and s.score < 0.9:
            if any(k in (MedKind.LAB, MedKind.VITAL, MedKind.DOSE, MedKind.DURATION) and a <= s.start and s.end <= b for a, b, k in meds):
                continue
        kept.append(s)
    kept.sort(key=lambda s: (-_PRIO[s.type], -(s.end - s.start), -s.score, s.start))
    accepted = []
    for s in kept:
        pieces = [(s.start, s.end)]
        for a in accepted:
            nxt = []
            for p0, p1 in pieces:
                if _overlap(p0, p1, a.start, a.end) == 0:
                    nxt.append((p0, p1))
                    continue
                if s.type in (PIIType.NAME, PIIType.ADDRESS):
                    if p0 < a.start:
                        nxt.append((p0, a.start))
                    if p1 > a.end:
                        nxt.append((a.end, p1))
            pieces = nxt
        for p0, p1 in pieces:
            if p1 - p0 >= 2:
                accepted.append(Span(s.doc_id, s.field, p0, p1, s.type, s.detector, s.score, s.role))
    accepted.sort(key=lambda s: (s.start, s.end))
    out = []
    for s in accepted:
        if out:
            p = out[-1]
            gap = text[p.end:s.start]
            same_role = p.role == s.role or not p.role or not s.role
            joinable = (p.type == s.type == PIIType.NAME and same_role and gap.strip(" ") == "" and "\n" not in gap and len(gap) <= 2) or \
                       (p.type == s.type == PIIType.ADDRESS and len(gap) <= 3 and gap.strip(" ,.-") == "")
            if joinable:
                out[-1] = Span(p.doc_id, p.field, p.start, s.end, p.type, p.detector, max(p.score, s.score), p.role or s.role)
                continue
        out.append(s)
    return out


def test_fast_merge_equals_the_original_on_random_inputs():
    import random

    from secretwards.contracts import MedKind, PIIType, Span
    from secretwards.detect.merge import merge

    rng = random.Random(7)
    text = "x" * 400
    for _ in range(1500):
        spans = [Span("d", None, a, a + rng.randrange(1, 25), rng.choice(list(PIIType)), "t", rng.choice([0.45, 0.6, 0.85, 0.95]), rng.choice(["", "patient", "doctor"]))
                 for a in (rng.randrange(0, 380) for _ in range(rng.randrange(0, 14)))]
        meds = [(a, a + rng.randrange(1, 30), rng.choice(list(MedKind))) for a in (rng.randrange(0, 380) for _ in range(rng.randrange(0, 10)))]
        key = lambda out: [(x.start, x.end, x.type, x.score, x.role) for x in out]  # noqa: E731
        assert key(merge(spans, meds, text)) == key(_reference_merge(spans, meds, text))
