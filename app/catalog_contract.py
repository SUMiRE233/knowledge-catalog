"""Stable public contract metadata for generated and released catalogs."""

from __future__ import annotations

import hashlib
from pathlib import Path

KNOWLEDGE_TREE_SCHEMA_VERSION = "1.0.0"
GENERATOR_VERSION = "0.3.0"
RELEASE_MANIFEST_SCHEMA_VERSION = "1.0.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
