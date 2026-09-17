"""Evaluate the public synthetic fixture against 40 frozen assertions."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from datetime import date
from pathlib import Path

from scripts.run_public_demo import run_demo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLD = ROOT / "evaluation" / "gold" / "public_fixture_gold.jsonl"
DEFAULT_REPORT = ROOT / "evaluation" / "results" / "public_fixture_eval.json"


def load_gold(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def index_tree(tree: dict) -> dict[tuple[str, ...], dict]:
    indexed = {}

    def walk(nodes: list[dict], parents: tuple[str, ...] = ()) -> None:
        for node in nodes:
            path = (*parents, node["name"])
            indexed[path] = node
            walk(node["children"], path)

    walk(tree["children"])
    return indexed


def evaluate(tree: dict, gold: list[dict]) -> dict:
    indexed = index_tree(tree)
    results = []
    for item in gold:
        path = tuple(item["path"])
        node = indexed.get(path)
        if item["kind"] == "node":
            passed = node is not None
            actual = "present" if passed else "missing"
        else:
            actual = node.get("scope") if node else None
            passed = actual == item["expected"]
        results.append({"id": item["id"], "passed": passed, "actual": actual})
    passed = sum(item["passed"] for item in results)
    return {
        "assertion_count": len(results),
        "passed_count": passed,
        "failed_count": len(results) - passed,
        "accuracy": passed / len(results) if results else 0.0,
        "failures": [item for item in results if not item["passed"]],
    }


async def run_evaluation(gold_path: Path, report_path: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="knowledge-catalog-public-eval-") as directory:
        demo_dir = Path(directory) / "demo"
        demo = await run_demo(demo_dir)
        tree = json.loads(
            (demo_dir / "artifacts" / "knowledge_tree.json").read_text(encoding="utf-8")
        )
        metrics = evaluate(tree, load_gold(gold_path))
    report = {
        "evaluation_id": "public-synthetic-gold-v1",
        "evaluated_at": date.today().isoformat(),
        "dataset": {
            "type": "synthetic",
            "fixture": "fixtures/public/synthetic_curriculum.pdf",
            "gold": "evaluation/gold/public_fixture_gold.jsonl",
            "assertions": metrics["assertion_count"],
        },
        "execution": {
            "runs": 1,
            "semantic_executor": "deterministic_test_double",
            "pipeline": "PDF render -> parser -> range -> guard -> publish",
            "model_request_count": demo["model_request_count"],
            "image_count": demo["image_count"],
        },
        "metrics": metrics,
        "pipeline_validation": {
            "warning_count": demo["warning_count"],
            "error_count": demo["error_count"],
        },
        "claim_boundary": (
            "This measures deterministic pipeline and contract reproducibility on a synthetic "
            "fixture; it does not measure real multimodal model accuracy."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = asyncio.run(run_evaluation(args.gold, args.report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["metrics"]["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
