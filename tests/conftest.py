import json
import socket
from pathlib import Path

import pytest

from secretwards.config import Config
from secretwards.security.keys import generate_keys, load_keys
from synth.generate import generate


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any socket use during a test is a failure: the pipeline must be fully offline."""
    def boom(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    monkeypatch.setattr(socket, "create_connection", boom)


@pytest.fixture(scope="session")
def keys_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("keys")
    generate_keys(d)
    return d


@pytest.fixture(scope="session")
def cfg(keys_dir):
    c = Config()
    c.keys_dir = str(keys_dir)
    c.emit_spans = True
    return c


@pytest.fixture(scope="session")
def keys(keys_dir):
    return load_keys(keys_dir)


@pytest.fixture(scope="session")
def dataset(tmp_path_factory):
    root = generate(tmp_path_factory.mktemp("data"), "heldout", seed=11, n_patients=70)
    return root, json.loads((root / "gold.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def run_out(dataset, cfg, keys, tmp_path_factory):
    from secretwards.pipeline import run

    root, _ = dataset
    out = tmp_path_factory.mktemp("out")
    report = run(root / "in", out, cfg, keys)
    return out, report
