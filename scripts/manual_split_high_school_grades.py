"""Manually regroup the reviewed high-school tree using the curriculum schedule.

This is an explicit one-off publishing operation. It does not infer curriculum
semantics and does not participate in the normal generation pipeline.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

GRADE_RANGES = (
    ("高一上", 1, 6),
    ("高一下", 7, 11),
    ("高二上", 12, 18),
    ("高二下", 19, 23),
    ("高三上", 24, 26),
    ("高三下", 27, 28),
)


def _assign_ids(node: dict[str, Any], node_id: str) -> None:
    node["id"] = node_id
    for index, child in enumerate(node["children"], start=1):
        _assign_ids(child, f"{node_id}.{index}")


def _without_ids(node: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (
            [_without_ids(child) for child in value]
            if key == "children"
            else value
        )
        for key, value in node.items()
        if key != "id"
    }


def regroup(tree: dict[str, Any]) -> dict[str, Any]:
    roots = tree.get("children")
    if not isinstance(roots, list) or len(roots) != 1:
        raise ValueError("expected exactly one existing high-school root")

    chapters = roots[0].get("children")
    if not isinstance(chapters, list) or len(chapters) != 28:
        raise ValueError("expected exactly 28 chapter nodes")

    before = [_without_ids(chapter) for chapter in chapters]
    result = copy.deepcopy(tree)
    result["children"] = []

    for grade_index, (grade_name, first, last) in enumerate(GRADE_RANGES, start=1):
        grade = {
            "id": str(grade_index),
            "name": grade_name,
            "scope": None,
            "children": copy.deepcopy(chapters[first - 1 : last]),
        }
        _assign_ids(grade, str(grade_index))
        result["children"].append(grade)

    after = [
        _without_ids(chapter)
        for grade in result["children"]
        for chapter in grade["children"]
    ]
    if before != after:
        raise AssertionError("existing chapter content changed during regrouping")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    tree = json.loads(args.source.read_text(encoding="utf-8"))
    result = regroup(tree)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
