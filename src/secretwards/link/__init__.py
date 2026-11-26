"""Linkage stage: mentions -> clusters with keyed pseudonyms."""
from __future__ import annotations

from typing import Sequence

from ..config import Config
from ..contracts import Cluster, Mention
from ..security.keys import Keys
from .cluster import cluster_mentions


def link_documents(mentions: Sequence[Mention], keys: Keys, cfg: Config) -> list[Cluster]:
    return cluster_mentions(mentions, keys, cfg)
