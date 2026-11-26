"""Run configuration. Everything that affects output comes from here (or the key files)."""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass
class Config:
    keys_dir: str = "keys"  # holds pseudonym.key, docid.key, date.key, enc.key
    seed: int = 1337  # reserved for any sampling; the pipeline is otherwise seed-free
    max_file_mb: int = 200
    max_unzipped_mb: int = 800  # xlsx zip-bomb guard
    # linkage
    link_threshold: float = 6.0
    block_cap: int = 60  # skip name blocks bigger than this (exact-ID blocks are exempt)
    # privacy
    date_shift_min_days: int = 30
    date_shift_max_days: int = 365
    k_target: int = 5
    age_band_width: int = 5
    age_top_code: int = 90  # ages >= this are reported as "90+"
    pin_keep_digits: int = 3
    qi_include_dx: bool = True  # False: diagnosis is not part of the k-anonymity tuple (still used for rare suppression and the attack)
    rare_dx_max_patients: int = 1  # a diagnosis seen in <= this many patients is "rare" (suppressed only if still identifying)
    # outputs
    emit_spans: bool = False  # write eval_spans.json (offsets and types only, no text)
    text_placeholder_style: str = "bracket"


def load_config(path: str | Path | None) -> Config:
    cfg = Config()
    if path is None:
        return cfg
    p = Path(path)
    raw: dict
    if p.suffix == ".json":
        raw = json.loads(p.read_text(encoding="utf-8"))
    else:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    flat: dict = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            flat.update(v)
        else:
            flat[k] = v
    known = {f.name for f in fields(Config)}
    for k, v in flat.items():
        if k not in known:
            raise ValueError("unknown config key")  # key name omitted on purpose
        setattr(cfg, k, v)
    return cfg
