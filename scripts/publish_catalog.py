"""Publish a reviewed knowledge tree with a versioned manifest and index."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

from app.catalog_contract import (
    KNOWLEDGE_TREE_SCHEMA_VERSION,
    RELEASE_MANIFEST_SCHEMA_VERSION,
    sha256_file,
)
from app.models import KnowledgeTree
from app.validation.output_guard import walk


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tree", type=Path)
    parser.add_argument("--logical-name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-title", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--output-root", type=Path, default=Path("releases"))
    parser.add_argument("--known-limitation", action="append", default=[])
    args = parser.parse_args()

    tree = KnowledgeTree.model_validate_json(args.tree.read_text(encoding="utf-8"))
    release_dir = args.output_root / f"v{args.version}"
    release_dir.mkdir(parents=True, exist_ok=True)
    artifact = release_dir / f"{args.logical_name}.json"
    shutil.copy2(args.tree, artifact)
    nodes = [node for node, _ in walk(tree.children)]
    manifest = {
        "manifest_schema_version": RELEASE_MANIFEST_SCHEMA_VERSION,
        "knowledge_tree_schema_version": KNOWLEDGE_TREE_SCHEMA_VERSION,
        "catalog_version": args.version,
        "logical_name": args.logical_name,
        "released_at": date.today().isoformat(),
        "artifact": artifact.name,
        "artifact_sha256": sha256_file(artifact),
        "counts": {
            "nodes": len(nodes),
            "leaves": sum(not node.children for node in nodes),
            "scoped_nodes": sum(bool(node.scope) for node in nodes),
        },
        "source": {
            "kind": "private_authoritative_pdf",
            "title": args.source_title,
            "included": False,
            "sha256": args.source_sha256.lower(),
            "generation_method": "multimodal extraction followed by human review",
        },
        "compatibility": {
            "canonical_request": args.logical_name,
            "legacy_request": f"{args.logical_name}.json",
        },
        "known_limitations": args.known_limitation,
    }
    manifest_path = release_dir / f"{args.logical_name}.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    index = {
        "index_schema_version": "1.0.0",
        "catalogs": {
            args.logical_name: {
                "latest": args.version,
                "artifact": f"v{args.version}/{artifact.name}",
                "manifest": f"v{args.version}/{manifest_path.name}",
            }
        },
    }
    (args.output_root / "catalog-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
